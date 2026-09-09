"""Development-only checks: analytic fixtures and independent SimpleITK sampling.

The only seeded fixtures used here are 30000..30011. No reserved study is read.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
import SimpleITK as sitk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from physical_contracts import Frame, phantom
import sampling_contracts as sampling


def declaration(b, shape, interpolation='nearest', outside=-50., **extra):
    return dict(index_map=np.asarray(b).tolist(), candidate_shape=list(shape),
                interpolation=interpolation, outside_value=outside,
                position_atol_mm=1e-4, intensity_atol=1e-4, **extra)


def simple_source():
    x, y, z = np.indices((5, 5, 5), dtype=float)
    mask = np.zeros((5, 5, 5), np.int16)
    mask[1:4, 1:4, 1:4] = 1
    return Frame(100. + 3*x - 2*y + .25*z, mask, np.eye(4)).validate()


def to_sitk(frame, mask=False):
    array = frame.mask if mask else frame.data
    image = sitk.GetImageFromArray(array.transpose(2, 1, 0))
    spacing = np.linalg.norm(frame.affine[:3, :3], axis=0)
    ras_to_lps = np.diag([-1., -1., 1.])
    image.SetSpacing(spacing.tolist())
    image.SetOrigin((ras_to_lps @ frame.affine[:3, 3]).tolist())
    image.SetDirection((ras_to_lps @ (frame.affine[:3, :3]/spacing)).ravel().tolist())
    return image


def sitk_candidate(source, b, shape, interpolation):
    affine = source.affine @ b
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    ras_to_lps = np.diag([-1., -1., 1.])
    origin = (ras_to_lps @ affine[:3, 3]).tolist()
    direction = (ras_to_lps @ (affine[:3, :3]/spacing)).ravel().tolist()
    arrays = []
    for mask in (False, True):
        method = sitk.sitkNearestNeighbor if mask or interpolation == 'nearest' else sitk.sitkLinear
        candidate = sitk.Resample(to_sitk(source, mask), list(shape), sitk.Transform(3, sitk.sitkIdentity),
                                  method, origin, spacing.tolist(), direction, 0. if mask else -50.,
                                  sitk.sitkInt16 if mask else sitk.sitkFloat64)
        arrays.append(sitk.GetArrayFromImage(candidate).transpose(2, 1, 0))
    return Frame(arrays[0], arrays[1], affine, source.label).validate()


class SamplingContractTests(unittest.TestCase):
    def test_analytic_affine_field_at_fractional_coordinates(self):
        source = simple_source()
        source = replace(source, mask=np.ones(source.data.shape, np.int16))
        b = np.diag([.75, .8, .5, 1.]); b[:3, 3] = [.25, .25, .25]
        shape = (4, 4, 5)
        u, v, w = np.indices(shape, dtype=float)
        # Closed-form field evaluation, independent of the interpolator code.
        expected = 100. + 3*(.75*u+.25) - 2*(.8*v+.25) + .25*(.5*w+.25)
        candidate = Frame(expected, np.ones(shape, np.int16), b).validate()
        result = sampling.sampling_witness(source, candidate, declaration(b, shape, 'linear'))
        self.assertEqual(result['status'], 'satisfied')
        self.assertLess(result['max_intensity_error'], 1e-12)
        # This analytic fixture intentionally samples only a subset of a full-ROI
        # source: correct interpolation must not hide the coverage loss.
        self.assertGreater(result['coverage']['source_roi_outside_candidate_fov'], 0)
        self.assertEqual(result['feature_reuse']['decision'], 'blocked')

    def test_half_voxel_edges_and_nearest_ties_against_fixed_answers(self):
        source = Frame(np.array([10., 20., 30.]).reshape(3, 1, 1),
                       np.ones((3, 1, 1), np.int16), np.eye(4)).validate()
        b = np.diag([.5, 1., 1., 1.]); b[0, 3] = -.5
        shape = (7, 1, 1)
        mask = np.array([1, 1, 1, 1, 1, 1, 0], np.int16).reshape(shape)
        for method, values in [('nearest', [10, 10, 20, 20, 30, 30, -50]),
                               ('linear', [10, 10, 15, 20, 25, 30, -50])]:
            with self.subTest(method=method):
                candidate = Frame(np.array(values, dtype=float).reshape(shape), mask, b).validate()
                native = sitk_candidate(source, b, shape, method)
                np.testing.assert_array_equal(native.data, candidate.data)
                np.testing.assert_array_equal(native.mask, candidate.mask)
                result = sampling.sampling_witness(source, candidate, declaration(b, shape, method))
                self.assertEqual(result['status'], 'indeterminate_boundary')
                self.assertEqual(result['strict_nominal_status'], 'satisfied')
                self.assertEqual(result['ambiguous_roi_voxels'], 2)
                self.assertEqual(result['ambiguous_intensity_voxels'], 4 if method == 'nearest' else 2)
                self.assertEqual(result['feature_reuse']['decision'], 'blocked')
                self.assertEqual(result['candidate_voxels_outside_source_support'], 1)

    def test_just_outside_lower_edge_is_fill_not_clamped(self):
        source = Frame(np.array([10., 20., 30.]).reshape(3, 1, 1),
                       np.ones((3, 1, 1), np.int16), np.eye(4)).validate()
        b = np.diag([.5, 1., 1., 1.]); b[0, 3] = -.50000001
        candidate = Frame(np.array([-50., 10.]).reshape(2, 1, 1),
                          np.array([0, 1], np.int16).reshape(2, 1, 1), b).validate()
        for method in ('nearest', 'linear'):
            result = sampling.sampling_witness(source, candidate, declaration(b, (2, 1, 1), method))
            self.assertEqual(result['status'], 'satisfied')

    def test_independent_simpleitk_on_twelve_development_phantoms(self):
        b = np.diag([1.03, .97, .91, 1.]); b[:3, 3] = [.13, .23, .37]
        for seed in range(30000, 30012):
            source = phantom(seed)
            shape = tuple(n-2 for n in source.data.shape)
            for method in ('nearest', 'linear'):
                with self.subTest(seed=seed, method=method):
                    observed = sitk_candidate(source, b, shape, method)
                    report = sampling.sampling_witness(source, observed, declaration(b, shape, method))
                    self.assertEqual(report['status'], 'satisfied', report)
                    self.assertLess(report['max_intensity_error'], 1e-9)
                    self.assertEqual(report['mismatched_roi_voxels'], 0)

    def test_correct_crop_preserves_roi_and_losing_crop_blocks_reuse(self):
        source = simple_source()
        for first_x, missing in ((1, 0), (2, 9)):
            b = np.eye(4); b[:3, 3] = [first_x, 1, 1]
            candidate = Frame(source.data[first_x:4, 1:4, 1:4].copy(),
                              source.mask[first_x:4, 1:4, 1:4].copy(), b).validate()
            report = sampling.sampling_witness(source, candidate, declaration(b, candidate.data.shape))
            self.assertEqual(report['status'], 'satisfied')
            self.assertEqual(report['coverage']['missing_roi_voxels'], missing)
            self.assertEqual(report['coverage']['exact_roi_preserved'], missing == 0)
            self.assertEqual(report['feature_reuse']['decision'], 'blocked' if missing else 'input_roi_preserved')

    def test_padding_fill_is_explicit_and_roi_correspondence_is_exact(self):
        source = simple_source()
        b = np.eye(4); b[:3, 3] = -1
        candidate = Frame(np.pad(source.data, 1, constant_values=-50),
                          np.pad(source.mask, 1), b).validate()
        report = sampling.sampling_witness(source, candidate, declaration(b, (7, 7, 7)))
        self.assertEqual(report['status'], 'satisfied')
        self.assertEqual(report['candidate_voxels_outside_source_support'], 7**3-5**3)
        self.assertEqual(report['coverage']['missing_roi_voxels'], 0)
        self.assertEqual(report['feature_reuse']['decision'], 'input_roi_preserved')
        bad = candidate.data.copy(); bad[0, 0, 0] = 0
        report = sampling.sampling_witness(source, replace(candidate, data=bad), declaration(b, (7, 7, 7)))
        self.assertFalse(report['checks']['intensity'])

    def test_resampling_roi_count_change_is_not_a_coverage_failure(self):
        source = simple_source()
        b = np.diag([2., 2., 2., 1.])
        candidate = Frame(source.data[::2, ::2, ::2].copy(), source.mask[::2, ::2, ::2].copy(), b).validate()
        self.assertEqual(int(np.count_nonzero(candidate.mask)), 1)
        self.assertEqual(int(np.count_nonzero(source.mask)), 27)
        report = sampling.sampling_witness(source, candidate, declaration(b, (3, 3, 3)))
        self.assertEqual(report['status'], 'satisfied')
        self.assertEqual(report['coverage']['source_roi_outside_candidate_fov'], 0)
        self.assertIsNone(report['coverage']['missing_roi_voxels'])
        self.assertIsNone(report['coverage']['exact_roi_preserved'])
        self.assertEqual(report['feature_reuse']['decision'], 'requires_reextraction')

    def test_shared_geometry_error_cannot_be_absorbed_into_index_map(self):
        source = simple_source(); wrong = source.affine.copy(); wrong[0, 3] += .2
        report = sampling.sampling_witness(source, replace(source, affine=wrong), declaration(np.eye(4), source.data.shape))
        self.assertFalse(report['checks']['position'])
        self.assertTrue(report['checks']['intensity'])
        self.assertTrue(report['checks']['roi'])
        self.assertAlmostEqual(report['max_corner_error_mm'], .2)
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')

    def test_intensity_tolerance_boundary_and_single_interior_change(self):
        source = simple_source()
        for error, expected in ((.5e-4, 'satisfied'), (2e-4, 'violated')):
            data = source.data.copy(); data[2, 2, 2] += error
            report = sampling.sampling_witness(source, replace(source, data=data), declaration(np.eye(4), source.data.shape))
            self.assertEqual(report['status'], expected)
            self.assertAlmostEqual(report['max_intensity_error'], error)

    def test_equal_roi_count_does_not_hide_changed_membership(self):
        source = simple_source(); mask = source.mask.copy()
        mask[1, 1, 1] = 0; mask[0, 0, 0] = 1
        self.assertEqual(mask.sum(), source.mask.sum())
        report = sampling.sampling_witness(source, replace(source, mask=mask), declaration(np.eye(4), source.data.shape))
        self.assertEqual(report['status'], 'violated')
        self.assertEqual(report['mismatched_roi_voxels'], 2)

    def test_calibration_and_world_change_require_new_measurements(self):
        source = simple_source()
        world = np.diag([2., 2., 2., 1.])
        candidate = replace(source, data=1.5*source.data+7, affine=world@source.affine)
        spec = declaration(np.eye(4), source.data.shape, world_map=world.tolist(), intensity_gain=1.5, intensity_offset=7)
        report = sampling.sampling_witness(source, candidate, spec)
        self.assertEqual(report['status'], 'satisfied')
        self.assertEqual(report['feature_reuse']['decision'], 'requires_reextraction')
        report = sampling.sampling_witness(source, source, declaration(np.eye(4), source.data.shape, 'linear'))
        self.assertEqual(report['status'], 'satisfied')
        self.assertEqual(report['feature_reuse']['decision'], 'requires_reextraction')

    def test_chunked_and_default_results_are_identical_and_inputs_unchanged(self):
        source = simple_source(); spec = declaration(np.eye(4), source.data.shape)
        before = tuple(a.tobytes() for a in (source.data, source.mask, source.affine))
        regular = sampling.sampling_witness(source, source, spec)
        with patch.object(sampling, '_BLOCK_VOXELS', 7):
            chunked = sampling.sampling_witness(source, source, spec)
        self.assertEqual(regular, chunked)
        self.assertEqual(before, tuple(a.tobytes() for a in (source.data, source.mask, source.affine)))

    def test_shape_mismatch_is_a_violation(self):
        source = simple_source()
        report = sampling.sampling_witness(source, source, declaration(np.eye(4), (4, 5, 5)))
        self.assertEqual(report['status'], 'violated')
        self.assertFalse(report['checks']['candidate_shape'])
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')

    def test_noncontiguous_mask_coverage_uses_actual_source_indices(self):
        source = simple_source()
        mask = np.zeros((5, 5, 5), np.int16); mask[1:4, 1:3, 2:4] = 1
        source = replace(source, data=source.data.transpose(2, 0, 1), mask=mask.transpose(2, 0, 1))
        self.assertFalse(source.mask.flags.c_contiguous)
        candidate = replace(source, data=source.data[:3].copy(), mask=source.mask[:3].copy())
        spec = declaration(np.eye(4), candidate.data.shape)
        with patch.object(sampling, '_BLOCK_VOXELS', 7):
            report = sampling.sampling_witness(source, candidate, spec)
        self.assertEqual(report['status'], 'satisfied')
        self.assertEqual(report['coverage']['source_roi_voxels'], 12)
        self.assertEqual(report['coverage']['missing_roi_voxels'], 6)

    def test_unsupported_declarations_are_rejected(self):
        source = simple_source(); valid = declaration(np.eye(4), source.data.shape)
        shear = np.eye(4); shear[0, 1] = .25
        invalid = [dict(valid, interpolation='bspline'), dict(valid, mask_outside=1),
                   dict(valid, index_boundary_atol=.25),
                   dict(valid, intensity_atol=-1), dict(valid, position_atol_mm=float('nan')),
                   dict(valid, outside_value=float('inf')), dict(valid, intensity_gain=-1),
                   dict(valid, candidate_shape=[True, 5, 5]), dict(valid, candidate_shape=[5., 5, 5]),
                   dict(valid, index_map=np.zeros((4, 4)).tolist()), dict(valid, index_map=shear.tolist())]
        missing = dict(valid); del missing['outside_value']; invalid.append(missing)
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises((ValueError, TypeError)):
                sampling.sampling_witness(source, source, spec)

    def test_boundary_alternative_is_indeterminate_but_not_an_interval_acceptance(self):
        source = Frame(np.array([10., 20., 30.]).reshape(3, 1, 1),
                       np.ones((3, 1, 1), np.int16), np.eye(4))
        b = np.eye(4); b[0, 3] = .5
        spec = declaration(b, (2, 1, 1))
        for first, status in ((10., 'indeterminate_boundary'), (20., 'indeterminate_boundary'),
                              (15., 'violated'), (99., 'violated')):
            candidate = Frame(np.array([first, 30.]).reshape(2, 1, 1), np.ones((2, 1, 1), np.int16), b)
            result = sampling.sampling_witness(source, candidate, spec)
            self.assertEqual(result['status'], status)
            self.assertEqual(result['feature_reuse']['decision'], 'blocked')
            if status == 'violated':
                self.assertFalse(result['checks']['intensity'])
                self.assertGreater(result['violating_intensity_voxels'], 0)

    def test_identical_boundary_neighbors_do_not_create_sampling_indeterminacy(self):
        source = Frame(np.full((3, 1, 1), 10.), np.ones((3, 1, 1), np.int16), np.eye(4))
        b = np.eye(4); b[0, 3] = .5
        candidate = Frame(np.full((2, 1, 1), 10.), np.ones((2, 1, 1), np.int16), b)
        result = sampling.sampling_witness(source, candidate, declaration(b, (2, 1, 1)))
        self.assertEqual(result['status'], 'satisfied')
        self.assertEqual(result['ambiguous_intensity_voxels'], 0)
        self.assertEqual(result['ambiguous_roi_voxels'], 0)
        self.assertEqual(result['coverage']['status'], 'indeterminate_boundary')
        self.assertEqual(result['coverage']['source_roi_centres_near_fov_boundary'], 2)

    def test_geometry_or_determinate_roi_fault_still_violates_with_other_ambiguity(self):
        source = Frame(np.array([10., 20., 30.]).reshape(3, 1, 1),
                       np.ones((3, 1, 1), np.int16), np.eye(4))
        b = np.diag([.5, 1., 1., 1.]); b[0, 3] = -.5
        data = np.array([10., 10., 20., 20., 30., 30., -50.]).reshape(7, 1, 1)
        mask = np.array([1, 1, 1, 1, 1, 1, 0], np.int16).reshape(7, 1, 1)
        moved = b.copy(); moved[1, 3] = .1
        result = sampling.sampling_witness(source, Frame(data, mask, moved), declaration(b, data.shape))
        self.assertEqual(result['status'], 'violated')
        self.assertFalse(result['checks']['position'])
        mask[1, 0, 0] = 0  # q=0 is not an NN boundary.
        result = sampling.sampling_witness(source, Frame(data, mask, b), declaration(b, data.shape))
        self.assertEqual(result['status'], 'violated')
        self.assertFalse(result['checks']['roi'])
        self.assertIsNone(result['checks']['intensity'])

    def test_oblique_exact_half_grid_is_retained_as_indeterminate(self):
        source = phantom(30000); b = np.diag([.5, .5, .5, 1.])
        shape = tuple(2*n-1 for n in source.data.shape)
        for method in ('nearest', 'linear'):
            candidate = sitk_candidate(source, b, shape, method)
            report = sampling.sampling_witness(source, candidate, declaration(b, shape, method))
            self.assertEqual(report['status'], 'indeterminate_boundary')
            self.assertEqual(report['strict_nominal_status'], 'violated')
            self.assertGreater(report['nominal_mismatched_roi_voxels'], 0)
            self.assertGreater(report['ambiguous_roi_voxels'], 0)
            self.assertEqual(report['violating_roi_voxels'], 0)
            self.assertEqual(report['violating_intensity_voxels'], 0)

    def test_empty_candidate_roi_is_reported_without_bypassing_domain_validation(self):
        source = simple_source()
        empty = replace(source, mask=np.zeros(source.mask.shape, np.int16))
        before = empty.mask.tobytes()
        report = sampling.sampling_witness(source, empty, declaration(np.eye(4), source.data.shape))
        self.assertEqual(report['status'], 'violated')
        self.assertEqual(report['coverage']['expected_candidate_roi_voxels'], 27)
        self.assertEqual(report['coverage']['candidate_roi_voxels'], 0)
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')
        self.assertEqual(before, empty.mask.tobytes())
        with self.assertRaises(ValueError):
            sampling.sampling_witness(source, replace(empty, mask=np.full(source.mask.shape, .25)),
                                      declaration(np.eye(4), source.data.shape))

    def test_correct_sampling_can_remove_roi_without_geometric_fov_loss(self):
        source = simple_source(); b = np.diag([4., 4., 4., 1.])
        candidate = Frame(source.data[::4, ::4, ::4].copy(), np.zeros((2, 2, 2), np.int16), b)
        report = sampling.sampling_witness(source, candidate, declaration(b, (2, 2, 2)))
        self.assertEqual(report['status'], 'satisfied')
        self.assertEqual(report['coverage']['source_roi_outside_candidate_fov'], 0)
        self.assertEqual(report['coverage']['expected_candidate_roi_voxels'], 0)
        self.assertEqual(report['coverage']['candidate_roi_voxels'], 0)
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')


if __name__ == '__main__':
    unittest.main()
