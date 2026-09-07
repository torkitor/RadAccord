"""Independent development verification. Seeds are deliberately limited to 0..11.

SimpleITK transports/reads physical images independently of the NumPy/NiBabel
implementation. Tests do not import fault generators or held-out manifests.
"""
from dataclasses import replace
from itertools import product
from pathlib import Path
import sys
import tempfile
import unittest

import nibabel as nib
import numpy as np
import SimpleITK as sitk

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import physical_contracts as pc


class PhysicalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.development = {seed: pc.phantom(seed) for seed in range(12)}
        cls.workspace = Path(tempfile.gettempdir()).resolve()
        cls.scratch = tempfile.TemporaryDirectory(prefix="contract_dev_", dir=cls.workspace)
        cls.directory = Path(cls.scratch.name).resolve()
        if not cls.directory.is_relative_to(cls.workspace):
            raise RuntimeError("Test scratch directory escaped the authorised work directory")

    @classmethod
    def tearDownClass(cls):
        if not cls.directory.resolve().is_relative_to(cls.workspace):
            raise RuntimeError("Refusing cleanup outside the authorised work directory")
        cls.scratch.cleanup()

    def assert_physical_equal(self, frame, image):
        self.assertEqual(tuple(frame.data.shape), tuple(image.GetSize()))
        indices = list(product(*[(0, n - 1) for n in frame.data.shape]))
        indices.append(tuple(n // 2 for n in frame.data.shape))
        for index in indices:
            expected_lps = image.TransformIndexToPhysicalPoint(tuple(int(i) for i in index))
            declared_ras = (frame.affine @ np.r_[index, 1.0])[:3]
            observed_ras = np.asarray(expected_lps) * [-1, -1, 1]
            self.assertLessEqual(float(np.linalg.norm(declared_ras - observed_ras)), pc.POSITION_ATOL_MM)

    def test_orbit_is_all_48_and_non_aliasing(self):
        cases = pc.orbit()
        self.assertEqual(len(cases), 48)
        self.assertEqual(len(set(cases)), 48)
        for perm, signs in cases:
            self.assertEqual(set(perm), {0, 1, 2})
            self.assertEqual(len(signs), 3)
            self.assertTrue(all(s in (-1, 1) for s in signs))
        source = self.development[0]
        transformed, _ = pc.reindex(source)
        transformed.data.flat[0] += 99
        transformed.mask.flat[0] = 7
        transformed.affine[0, 3] += 99
        self.assertNotEqual(transformed.data.flat[0], source.data.flat[0])
        self.assertNotEqual(transformed.mask.flat[0], source.mask.flat[0])
        self.assertNotEqual(transformed.affine[0, 3], source.affine[0, 3])

    def test_complete_development_orbit_against_simpleitk_and_inverses(self):
        checked = 0
        for seed, source in self.development.items():
            ip, mp = pc.write_frame(source, self.directory, "source")
            itk_image, itk_mask = sitk.ReadImage(str(ip)), sitk.ReadImage(str(mp))
            for perm, signs in pc.orbit():
                with self.subTest(seed=seed, perm=perm, signs=signs):
                    transformed, spec = pc.transform(source, "reindex", perm=perm, signs=signs)
                    expected_image = sitk.Flip(sitk.PermuteAxes(itk_image, list(perm)), [s < 0 for s in signs], False)
                    expected_mask = sitk.Flip(sitk.PermuteAxes(itk_mask, list(perm)), [s < 0 for s in signs], False)
                    np.testing.assert_array_equal(transformed.data, sitk.GetArrayFromImage(expected_image).transpose(2, 1, 0))
                    np.testing.assert_array_equal(transformed.mask, sitk.GetArrayFromImage(expected_mask).transpose(2, 1, 0))
                    self.assert_physical_equal(transformed, expected_image)
                    inverse_perm = tuple(int(x) for x in np.argsort(perm))
                    inverse_signs = tuple(signs[j] for j in inverse_perm)
                    recovered, _ = pc.reindex(transformed, inverse_perm, inverse_signs)
                    np.testing.assert_array_equal(recovered.data, source.data)
                    np.testing.assert_array_equal(recovered.mask, source.mask)
                    np.testing.assert_allclose(recovered.affine, source.affine, rtol=0, atol=1e-12)
                    # Read transformed files through an independent native reader.
                    tp, tm = pc.write_frame(transformed, self.directory, "transformed")
                    reread = sitk.ReadImage(str(tp))
                    np.testing.assert_array_equal(sitk.GetArrayFromImage(reread), sitk.GetArrayFromImage(expected_image))
                    self.assert_physical_equal(transformed, reread)
                    decoded, geometry = pc.read_frame(tp, tm)
                    self.assertTrue(all(geometry.values()))
                    self.assertEqual(pc.transport_witness(source, decoded, spec)["status"], "satisfied")
                    checked += 1
        self.assertEqual(checked, 576)

    def test_encoding_header_calibration_and_relabelling_with_independent_reader(self):
        for seed, source in self.development.items():
            for slope, intercept in ((2.0, 10.0), (0.5, -20.0)):
                with self.subTest(seed=seed, slope=slope, intercept=intercept):
                    encoded, spec = pc.transform(source, "encoding", slope=slope, intercept=intercept)
                    relabelled, _ = pc.transform(encoded, "label", label=7)
                    ip, mp = pc.write_frame(relabelled, self.directory, "calibrated")
                    itk_image = sitk.ReadImage(str(ip))
                    np.testing.assert_array_equal(sitk.GetArrayFromImage(itk_image).transpose(2, 1, 0), source.data)
                    np.testing.assert_array_equal(sitk.GetArrayFromImage(sitk.ReadImage(str(mp))).transpose(2, 1, 0) == 7,
                                                  source.mask == source.label)
                    self.assert_physical_equal(relabelled, itk_image)
                    observed, geometry = pc.read_frame(ip, mp, label=7)
                    self.assertTrue(all(geometry.values()))
                    self.assertEqual(pc.transport_witness(source, observed, spec)["status"], "satisfied")

    def test_true_spatial_and_intensity_changes_have_the_declared_laws(self):
        for seed, source in self.development.items():
            baseline = pc.analytic_anchors(source)
            for scale in (0.5, 2.0):
                out, spec = pc.transform(source, "scale", scale=scale)
                self.assertEqual(pc.transport_witness(source, out, spec)["status"], "satisfied")
                self.assertAlmostEqual(pc.analytic_anchors(out)["voxel_volume"] / baseline["voxel_volume"], scale ** 3, places=12)
                ip, _ = pc.write_frame(out, self.directory, "scale")
                self.assert_physical_equal(out, sitk.ReadImage(str(ip)))
            for gain, offset in ((2.0, 13.0), (0.5, 25.0)):
                out, spec = pc.transform(source, "intensity", gain=gain, offset=offset)
                measured = pc.analytic_anchors(out)
                self.assertEqual(pc.transport_witness(source, out, spec)["status"], "satisfied")
                self.assertAlmostEqual(measured["mean"], gain * baseline["mean"] + offset, places=10)
                self.assertAlmostEqual(measured["variance"], gain ** 2 * baseline["variance"], places=10)
                expected_energy = gain ** 2 * baseline["energy"] + 2 * gain * offset * baseline["n_voxels"] * baseline["mean"] + offset ** 2 * baseline["n_voxels"]
                self.assertLess(abs(measured["energy"] - expected_energy) / expected_energy, 1e-12)

    def test_witness_detects_interior_changes_not_just_corner_values_or_moments(self):
        source = self.development[0]
        _, spec = pc.transform(source, "encoding", slope=1.0, intercept=0.0)
        changed_data = source.data.copy()
        interior = tuple(n // 2 for n in source.data.shape)
        changed_data[interior] += 1
        result = pc.transport_witness(source, replace(source, data=changed_data), spec)
        self.assertEqual(result["status"], "violated")
        self.assertFalse(result["checks"]["intensity"])
        changed_mask = source.mask.copy()
        selected = tuple(np.argwhere(source.mask == source.label)[0])
        background = tuple(np.argwhere(source.mask != source.label)[0])
        changed_mask[selected], changed_mask[background] = 0, source.label
        result = pc.transport_witness(source, replace(source, mask=changed_mask), spec)
        self.assertEqual(result["status"], "violated")
        self.assertFalse(result["checks"]["roi"])

    def test_position_and_intensity_tolerance_boundaries(self):
        source = self.development[0]
        _, spec = pc.transform(source, "encoding", slope=1.0, intercept=0.0)
        for factor, expected in ((0.5, "satisfied"), (2.0, "violated")):
            affine = source.affine.copy()
            affine[0, 3] += factor * pc.POSITION_ATOL_MM
            self.assertEqual(pc.transport_witness(source, replace(source, affine=affine), spec)["status"], expected)
            data = source.data.copy()
            data.flat[0] += factor * pc.INTENSITY_ATOL
            self.assertEqual(pc.transport_witness(source, replace(source, data=data), spec)["status"], expected)

    def test_native_pair_geometry_mismatch_is_returned_separately(self):
        source = self.development[0]
        ip, mp = pc.write_frame(source, self.directory, "mismatch")
        mask = nib.load(mp)
        bad_affine = mask.affine.copy()
        bad_affine[0, 3] += 3
        moved = nib.Nifti1Image(np.asanyarray(mask.dataobj), bad_affine, header=mask.header.copy())
        moved.set_qform(bad_affine, code=1)
        moved.set_sform(bad_affine, code=1)
        nib.save(moved, mp)
        _, geometry = pc.read_frame(ip, mp)
        self.assertTrue(geometry["same_shape"])
        self.assertFalse(geometry["same_affine"])

    def test_rejects_non_mm_units_and_discordant_qform_sform(self):
        for units in ("meter", "micron", "unknown"):
            ip, mp = pc.write_frame(self.development[0], self.directory, "units")
            for path in (ip, mp):
                nii = nib.load(path)
                nii.header.set_xyzt_units(units)
                nib.save(nii, path)
            with self.subTest(units=units), self.assertRaises(ValueError):
                pc.read_frame(ip, mp)
        ip, mp = pc.write_frame(self.development[0], self.directory, "qform")
        nii = nib.load(ip)
        wrong = nii.affine.copy()
        wrong[0, 3] += 10
        nii.set_qform(wrong, code=1)
        nib.save(nii, ip)
        with self.assertRaises(ValueError):
            pc.read_frame(ip, mp)

    def test_rejects_unsupported_domains_before_lossy_write(self):
        source = self.development[0]
        shear = source.affine.copy()
        shear[:3, 0] += 0.2 * shear[:3, 1]
        bad_data = source.data.copy()
        bad_data.flat[0] = np.nan
        candidates = {
            "complex_image": replace(source, data=source.data.astype(complex) + 1j),
            "nonfinite_image": replace(source, data=bad_data),
            "fractional_mask": replace(source, mask=np.where(source.mask == 0, 0.5, source.mask)),
            "nonfinite_mask": replace(source, mask=np.where(source.mask == 0, np.nan, source.mask)),
            "label_zero": replace(source, label=0),
            "sheared_affine": replace(source, affine=shear),
        }
        for name, candidate in candidates.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                candidate.validate()
        for signs in ((1, 1), (1, 1, 1, 1)):
            with self.subTest(signs=signs), self.assertRaises(ValueError):
                pc.reindex(source, signs=signs)

    def test_integer_input_energy_uses_non_overflowing_accumulation(self):
        frame = pc.Frame(np.full((5, 5, 5), 100, np.uint16), np.ones((5, 5, 5), np.int16), np.eye(4)).validate()
        self.assertEqual(pc.analytic_anchors(frame)["energy"], 1_250_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
