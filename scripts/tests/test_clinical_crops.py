"""Independent synthetic checks of the fixed clinical input preparation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nibabel as nib
import numpy as np

spec = importlib.util.spec_from_file_location('crop_preparation', Path(__file__).resolve().parents[1] / 'prepare_clinical_crops.py')
crops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crops)


class CropTests(unittest.TestCase):
    def fixture(self, directory, count=3):
        directory = Path(directory)
        rows = []
        for index in range(count):
            image = nib.Nifti1Image(np.arange(8**3, dtype='int16').reshape(8, 8, 8), np.eye(4))
            image.header.set_xyzt_units('mm')
            roi = np.zeros(image.shape, dtype='uint8')
            roi[2:5, 2:5, 2:5] = 1
            mask = nib.Nifti1Image(roi, np.eye(4))
            mask.header.set_xyzt_units('mm')
            image_path, mask_path = directory/f'image{index}.nii.gz', directory/f'mask{index}.nii.gz'
            nib.save(image, image_path); nib.save(mask, mask_path)
            rows.append({'task': 'Task99_Synthetic', 'source_basename': f'fixture_{index:03d}.nii.gz',
                         'selection_rank': index+1, 'source_eligible': True, 'exclusion_reasons': [],
                         'image': str(image_path), 'mask': str(mask_path),
                         'image_sha256': crops.digest(image_path), 'mask_sha256': crops.digest(mask_path)})
        selected = directory/'selected.jsonl'
        selected.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return rows, selected, directory/'crops', directory/'public.json', directory/'private.json'

    def test_all_slots_retained_after_case_failure_without_private_exception_text(self):
        with tempfile.TemporaryDirectory() as directory:
            rows, selected, output, receipt, manifest = self.fixture(directory)
            original = crops.nib.save

            def fail_middle(image, path):
                if 'fixture_001_image' in Path(path).name:
                    before = json.loads(receipt.read_text())
                    self.assertEqual(before['planned_source_volumes'], 3)
                    self.assertEqual(len(before['records']), 3)
                    raise OSError('private-patient-name at C:/Users/private-person/raw-image.nii')
                return original(image, path)

            with patch.object(crops.nib, 'save', fail_middle):
                result = crops.prepare(selected, output, receipt, manifest)
            self.assertEqual([row['status'] for row in result['records']],
                             ['prepared_and_verified', 'preparation_failed', 'prepared_and_verified'])
            self.assertEqual(len(json.loads(manifest.read_text())), 2)
            public = receipt.read_text()
            self.assertNotIn(directory, public)
            self.assertNotIn('private-patient-name', public)
            self.assertNotIn('C:/Users/', public)
            self.assertEqual(result['records'][1]['exception_type'], 'OSError')

    def test_changed_bound_source_stops_with_failure_and_remaining_slot_records(self):
        with tempfile.TemporaryDirectory() as directory:
            rows, selected, output, receipt, manifest = self.fixture(directory)
            rows[1]['image_sha256'] = '0'*64
            selected.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaises(crops.SourceIntegrityError):
                crops.prepare(selected, output, receipt, manifest)
            records = json.loads(receipt.read_text())['records']
            self.assertEqual([row['status'] for row in records],
                             ['prepared_and_verified', 'preparation_failed', 'not_reached'])
            self.assertEqual(records[1]['reason_code'], 'source_hash_mismatch')
            self.assertEqual(len(json.loads(manifest.read_text())), 1)

    def test_duplicate_unsafe_identity_and_raw_reason_text_rejected_before_writes(self):
        mutations = [lambda rows: rows.__setitem__(1, dict(rows[0])),
                     lambda rows: rows[0].update(task='/absolute/private'),
                     lambda rows: rows[0].update(source_basename='../escape.nii.gz'),
                     lambda rows: rows[0].update(exclusion_reasons=['C:/Users/private'])]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                rows, selected, output, receipt, manifest = self.fixture(directory)
                mutate(rows)
                selected.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaises(ValueError):
                    crops.prepare(selected, output, receipt, manifest)
                self.assertFalse(output.exists())
                self.assertFalse(receipt.exists())

    def test_declared_eligibility_does_not_bypass_units_or_paired_geometry(self):
        for change in ('metres', 'paired_origin', 'qform_sform'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                rows, selected, output, receipt, manifest = self.fixture(directory, 1)
                path = Path(rows[0]['mask'])
                mask = nib.load(path)
                if change == 'metres':
                    mask.header.set_xyzt_units('meter')
                elif change == 'paired_origin':
                    affine = mask.affine.copy(); affine[0, 3] += .01
                    mask.set_sform(affine, code=1)
                else:
                    affine = mask.affine.copy(); affine[0, 3] += .01
                    mask.set_qform(affine, code=1)
                nib.save(mask, path)
                rows[0]['mask_sha256'] = crops.digest(path)
                selected.write_text(json.dumps(rows[0])+'\n')
                result = crops.prepare(selected, output, receipt, manifest)
                self.assertEqual(result['records'][0]['status'], 'preparation_failed')
                self.assertFalse(json.loads(manifest.read_text()))

    def test_source_exclusions_are_retained_without_source_access(self):
        with tempfile.TemporaryDirectory() as directory:
            rows, selected, output, receipt, manifest = self.fixture(directory, 1)
            reasons = ['image:units_not_mm', 'mask:foreground_fewer_than_8_voxels']
            rows[0].update(source_eligible=False, exclusion_reasons=reasons, image='absent', mask='absent')
            selected.write_text(json.dumps(rows[0])+'\n')
            result = crops.prepare(selected, output, receipt, manifest)
            self.assertEqual(result['planned_source_volumes'], 1)
            self.assertEqual(result['source_eligible_volumes'], 0)
            self.assertEqual(result['records'][0]['status'], 'source_excluded')
            self.assertEqual(result['records'][0]['exclusion_reasons'], reasons)

    def test_missing_source_hash_requires_exclusion_and_explicit_reason(self):
        for eligible, reasons, allowed in [(False, ['image:missing_file'], True),
                                           (False, [], False),
                                           (True, ['image:missing_file'], False)]:
            with self.subTest(eligible=eligible, reasons=reasons), tempfile.TemporaryDirectory() as directory:
                rows, selected, output, receipt, manifest = self.fixture(directory, 1)
                rows[0].update(source_eligible=eligible, exclusion_reasons=reasons,
                               image_sha256=None, image='absent')
                selected.write_text(json.dumps(rows[0])+'\n')
                if allowed:
                    result = crops.prepare(selected, output, receipt, manifest)
                    self.assertEqual(result['records'][0]['status'], 'source_excluded')
                    self.assertIsNone(result['records'][0]['source_image_sha256'])
                    self.assertFalse(json.loads(manifest.read_text()))
                else:
                    with self.assertRaises(ValueError):
                        crops.prepare(selected, output, receipt, manifest)
                    self.assertFalse(output.exists())

    def test_private_manifest_cannot_overwrite_public_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            _, selected, output, receipt, _ = self.fixture(directory, 1)
            with self.assertRaisesRegex(ValueError, 'distinct destinations'):
                crops.prepare(selected, output, receipt, receipt)
            self.assertFalse(output.exists())
            self.assertFalse(receipt.exists())

    def test_private_preparation_paths_are_refused_inside_public_repository(self):
        for field in ('selected', 'output', 'manifest'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                _, selected, output, receipt, manifest = self.fixture(directory, 1)
                public = Path(directory)/'public_repository'
                public.mkdir()
                arguments = {'selected': selected, 'output': output, 'manifest': manifest}
                arguments[field] = public/'private_material'
                with patch.object(crops, 'REPOSITORY', public), self.assertRaisesRegex(ValueError, 'outside the repository'):
                    crops.prepare(arguments['selected'], arguments['output'], receipt, arguments['manifest'])
                self.assertFalse(receipt.exists())

    def test_invalid_crop_bounds_are_not_silently_truncated(self):
        image = nib.Nifti1Image(np.ones((5, 5, 5), dtype='float32'), np.eye(4))
        for lower, upper in [([.5, 0, 0], [3, 3, 3]), ([-1, 0, 0], [3, 3, 3]),
                             ([0, 0, 0], [6, 3, 3]), ([2, 0, 0], [2, 3, 3])]:
            with self.subTest(lower=lower, upper=upper), self.assertRaises(ValueError):
                crops.crop_object(image, lower, upper)

    def test_context_uses_physical_spacing_and_retains_boundary_roi(self):
        mask = np.zeros((40, 50, 30), dtype='uint8')
        mask[0:4, 20:25, 12:15] = 1
        lower, upper = crops.crop_bounds(mask, [2., 1., 4.])
        np.testing.assert_array_equal(lower, [0, 10, 9])
        np.testing.assert_array_equal(upper, [9, 35, 18])
        self.assertEqual(np.count_nonzero(mask[0:9, 10:35, 9:18]), 60)

    def test_oblique_serialized_crop_preserves_values_dtype_and_world_coordinates(self):
        angle = .31
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        affine = np.eye(4)
        affine[:3, :3] = rotation @ np.diag([1.1, 1.3, 2.5])
        affine[:3, 3] = [-123., 52., 8.]
        values = np.arange(20 * 21 * 22, dtype='int16').reshape(20, 21, 22) - 1000
        source = nib.Nifti1Image(values, affine)
        lower, upper = np.array([3, 4, 5]), np.array([15, 16, 18])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.nii.gz'
            nib.save(crops.crop_object(source, lower, upper), path)
            report = crops.verify_crop(source, nib.load(path), lower, upper)
        self.assertTrue(report['decoded_array_equal'])
        self.assertLess(report['maximum_world_error_mm'], 1e-4)

    def test_missing_roi_and_changed_intensity_or_geometry_rejected(self):
        with self.assertRaises(ValueError):
            crops.crop_bounds(np.zeros((5, 5, 5)), [1, 1, 1])
        source = nib.Nifti1Image(np.ones((5, 5, 5), dtype='float32'), np.eye(4))
        wrong_values = nib.Nifti1Image(np.zeros((3, 3, 3), dtype='float32'), np.eye(4))
        with self.assertRaises(ValueError):
            crops.verify_crop(source, wrong_values, [0, 0, 0], [3, 3, 3])
        wrong_origin = np.eye(4); wrong_origin[0, 3] = 1
        wrong_geometry = nib.Nifti1Image(np.ones((3, 3, 3), dtype='float32'), wrong_origin)
        with self.assertRaises(ValueError):
            crops.verify_crop(source, wrong_geometry, [0, 0, 0], [3, 3, 3])

    def test_roi_loss_is_rejected_even_when_remaining_values_match(self):
        source = nib.Nifti1Image(np.ones((5, 5, 5), dtype='uint8'), np.eye(4))
        output = crops.crop_object(source, [0, 0, 0], [3, 3, 3])
        with self.assertRaises(ValueError):
            crops.verify_crop(source, output, [0, 0, 0], [3, 3, 3], label=1)


if __name__ == '__main__':
    unittest.main()
