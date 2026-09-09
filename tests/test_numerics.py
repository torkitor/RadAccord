"""Synthetic analytical rounding fixtures; no cohort-derived arrays."""
import importlib.util
import unittest
import numpy as np
from radaccord.legacy import Frame
from radaccord import operators as op
from radaccord.numerics import (verify_native_operation, _itk_tail,
                               _coefficient_envelope, _gaussian_envelope,
                               _cast_interval, _quantised_interval)


def source_frame(shape=(7, 8, 9), dtype='float32'):
    x, y, z = np.indices(shape)
    data = (110.+3*x+7*y+2*z).astype(dtype)
    return Frame(data, np.ones(shape, dtype=np.int16), np.eye(4), 1)


def specification(source, **changes):
    b = np.eye(4)
    b[:3, 3] = [.13, .23, .37]
    result = dict(index_map=b.tolist(), candidate_shape=list(source.data.shape),
                  interpolation='linear', boundary='nearest', outside_value=0.,
                  output_dtype=str(source.data.dtype), position_atol_mm=1e-4,
                  intensity_atol=1e-4, index_boundary_atol=1e-9,
                  mask_boundary='nearest')
    result.update(changes)
    return result


def native_sitk_image(frame):
    import SimpleITK as sitk
    image = sitk.GetImageFromArray(frame.data.transpose(2, 1, 0))
    lps = np.diag([-1., -1., 1.])
    m = lps@frame.affine[:3, :3]
    spacing = np.linalg.norm(m, axis=0)
    image.SetSpacing(tuple(spacing))
    image.SetOrigin(tuple(lps@frame.affine[:3, 3]))
    image.SetDirection(tuple((m/spacing).ravel()))
    return image


class NumericalEnvelopeTests(unittest.TestCase):
    def test_ct_final_rounding_follows_storage_conversion(self):
        source = source_frame((2, 2, 2))
        values = np.array([.50000001, -.50000001, 1.5, 2.5, -1.5, -2.5])
        spec = specification(source, output_quantisation='nearest_even')
        parsed = op._parse(source, spec)
        np.testing.assert_array_equal(op._cast(values, parsed), [0., 0., 2., 2., -2., -2.])
        parsed['output_dtype'] = 'float64'
        np.testing.assert_array_equal(op._cast(values, parsed), [1., -1., 2., 2., -2., -2.])

    def test_quantised_endpoint_set_crosses_positive_and_negative_half_ties(self):
        raw = np.array([-.5, .5, 1.5, 2.5])
        low, high = _cast_interval(raw, np.full(4, 1e-12), 'float64')
        low, high = _quantised_interval(low, high, 'nearest_even')
        np.testing.assert_array_equal(low, [-1., 0., 1., 2.])
        np.testing.assert_array_equal(high, [0., 1., 2., 3.])
        # A representable float32 half tie has a deterministic even result when
        # its preceding storage interval collapses to that same float32 value.
        lo32, hi32 = _cast_interval(raw, np.full(4, 1e-12), 'float32')
        lo32, hi32 = _quantised_interval(lo32, hi32, 'nearest_even')
        np.testing.assert_array_equal(lo32, [0., 0., 2., 2.])
        np.testing.assert_array_equal(hi32, lo32)

    def test_final_ct_quantisation_ambiguity_blocks_both_compatible_outputs(self):
        source = source_frame((2, 2, 2), 'float64')
        source.data[0] = 0.
        source.data[1] = 1.
        b = np.eye(4)
        b[:3, 3] = [.5, .13, .23]
        spec = specification(source, index_map=b.tolist(), candidate_shape=[1, 1, 1],
                             output_quantisation='nearest_even')
        candidate = op.expected_operation(source, spec)
        for value in (0., 1.):
            candidate.data[:] = value
            report = verify_native_operation(source, candidate, spec)
            self.assertEqual(report['status'], 'indeterminate', report)
            self.assertEqual(report['feature_reuse']['decision'], 'blocked')
            self.assertEqual(report['numerical_envelope']['intensity_atol_unchanged'], 1e-4)
        candidate.data[:] = 2.
        self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'violated')

    def test_stable_ct_rounding_still_rejects_one_hu_changes(self):
        source = source_frame(dtype='float32')
        spec = specification(source, output_quantisation='nearest_even')
        candidate = op.expected_operation(source, spec)
        first = verify_native_operation(source, candidate, spec)
        self.assertEqual(first['status'], 'satisfied', first)
        candidate.data[2, 3, 4] += 1.
        second = verify_native_operation(source, candidate, spec)
        self.assertEqual(second['status'], 'violated', second)
        self.assertEqual(first['numerical_envelope'], second['numerical_envelope'])

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'Independent SciPy comparison')
    def test_ct_antialias_and_final_quantisation_against_scipy(self):
        from scipy.ndimage import gaussian_filter, map_coordinates
        rng = np.random.default_rng(438107)
        source = source_frame((9, 10, 11), 'float32')
        source.data[:] = rng.integers(-1024, 1700, source.data.shape)
        for order in (1, 3):
            spec = specification(source, interpolation='linear' if order == 1 else 'bspline3',
                antialias_sigma=[.73, 1.14, .91], antialias_quantisation='nearest_even',
                output_quantisation='nearest_even')
            candidate = op.expected_operation(source, spec)
            axes = (2, 1, 0)
            smoothed = gaussian_filter(source.data, [spec['antialias_sigma'][a] for a in axes],
                                       axes=axes, mode='nearest', truncate=4.)
            intermediate = np.rint(smoothed)
            indices = np.indices(source.data.shape).reshape(3, -1)
            b = np.asarray(spec['index_map'])
            q = b[:3, :3] @ indices + b[:3, 3, None]
            expected = np.rint(map_coordinates(intermediate, q, order=order,
                                               mode='nearest', prefilter=True))
            candidate.data[:] = expected.reshape(source.data.shape)
            report = verify_native_operation(source, candidate, spec)
            self.assertIn(report['status'], ('satisfied', 'indeterminate'), report)
            self.assertEqual(report['violating_intensity_voxels'], 0)
            candidate.data[3, 4, 5] += 25.
            self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'violated')

    def test_undeclared_or_inapplicable_quantisation_is_not_accepted(self):
        source = source_frame()
        candidate = op.expected_operation(source, specification(source))
        for change in ({'output_quantisation': 'nearest'},
                       {'antialias_quantisation': 'nearest_even'},
                       {'output_quantisation': 'nearest_even', 'output_dtype': 'int16'}):
            result = verify_native_operation(source, candidate, specification(source, **change))
            self.assertEqual(result['status'], 'unavailable', result)

    def test_exact_float32_midpoint_blocks_both_adjacent_outputs(self):
        source = source_frame((2, 2, 2))
        lower = np.float32(262144.)
        upper = np.nextafter(lower, np.float32(np.inf))
        source.data[0] = lower
        source.data[1] = upper
        b = np.eye(4)
        b[:3, 3] = [.5, .13, .23]
        spec = specification(source, index_map=b.tolist(), candidate_shape=[1, 1, 1])
        candidate = op.expected_operation(source, spec)
        for value in (lower, upper):
            candidate.data[:] = value
            report = verify_native_operation(source, candidate, spec)
            self.assertEqual(report['status'], 'indeterminate', report)
            self.assertEqual(report['feature_reuse']['decision'], 'blocked')
            self.assertEqual(report['numerical_envelope']['intensity_atol_unchanged'], 1e-4)
            self.assertEqual(report['ambiguous_intensity_voxels'], 1)
            self.assertEqual(report['violating_intensity_voxels'], 0)
        candidate.data[:] = upper+1.
        report = verify_native_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'violated')
        self.assertEqual(report['violating_intensity_voxels'], 1)

    def test_stable_float32_and_float64_relationships(self):
        for dtype in ('float32', 'float64'):
            source = source_frame(dtype=dtype)
            spec = specification(source)
            candidate = op.expected_operation(source, spec)
            report = verify_native_operation(source, candidate, spec)
            self.assertEqual(report['status'], 'satisfied', report)
            self.assertIn('nominal_reference', report)
            self.assertFalse(report['numerical_envelope']['candidate_used_to_set_bounds'])
            candidate.data[2, 3, 4] += .5
            self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'violated')

    def test_geometry_fault_cannot_be_excused_by_numeric_uncertainty(self):
        source = source_frame()
        spec = specification(source)
        candidate = op.expected_operation(source, spec)
        candidate.affine[0, 3] += 11.
        report = verify_native_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'violated')
        self.assertFalse(report['checks']['position'])

    def test_bound_is_identical_for_nominal_and_incompatible_candidate(self):
        source = source_frame()
        spec = specification(source)
        candidate = op.expected_operation(source, spec)
        first = verify_native_operation(source, candidate, spec)
        candidate.data[2, 3, 4] += 10.
        second = verify_native_operation(source, candidate, spec)
        self.assertEqual(first['numerical_envelope'], second['numerical_envelope'])

    @unittest.skipUnless(importlib.util.find_spec('SimpleITK'), 'SimpleITK native comparison')
    def test_itk_causal_tail_and_roundoff_cover_long_line_coefficients(self):
        import SimpleITK as sitk
        source = source_frame((31, 9, 7), 'float64')
        x, y, z = np.indices(source.data.shape)
        source.data[:] = 1e6*(np.sin(x*.37)+.3*np.cos(y*.4)+.1*z)
        spec = specification(source, interpolation='bspline3', boundary='sitk')
        p = op._parse(source, spec)
        prepared = op._prepare(source, p)
        radius, tail = _coefficient_envelope(source.data, np.zeros(source.data.shape), p, prepared[2])
        native = sitk.GetArrayFromImage(sitk.BSplineDecomposition(native_sitk_image(source), 3)).transpose(2, 1, 0)
        error = np.abs(native-prepared[2])
        self.assertGreater(tail, 0.)
        self.assertTrue(np.all(error <= radius), (float(error.max()), float(radius.max())))
        # The prefilter perturbation is localized along its causal axis.
        tail_field = _itk_tail(source.data, np.zeros(source.data.shape), 0)
        self.assertGreater(float(tail_field[0].max()), float(tail_field[15].max())*1e5)

    @unittest.skipUnless(importlib.util.find_spec('SimpleITK'), 'SimpleITK native comparison')
    def test_high_dynamic_cubic_native_float32_and_float64_remain_compatible(self):
        import SimpleITK as sitk
        source = source_frame((25, 9, 8), 'float64')
        x, y, z = np.indices(source.data.shape)
        source.data[:] = 4e5+2e5*np.sin(x*.47)+1e4*y*y+12.5*z
        for dtype, pixel in [('float32', sitk.sitkFloat32), ('float64', sitk.sitkFloat64)]:
            b = np.eye(4)
            b[:3, 3] = [.17, .23, .31]
            spec = specification(source, interpolation='bspline3', boundary='sitk',
                                 index_map=b.tolist(), candidate_shape=[23, 7, 6], output_dtype=dtype)
            candidate = op.expected_operation(source, spec)
            reference = native_sitk_image(candidate)
            actual = sitk.Resample(native_sitk_image(source), reference, sitk.Transform(),
                                   sitk.sitkBSpline, 0., pixel)
            candidate.data = sitk.GetArrayFromImage(actual).transpose(2, 1, 0)
            report = verify_native_operation(source, candidate, spec)
            self.assertIn(report['status'], ('satisfied', 'indeterminate'), report)
            self.assertEqual(report['violating_intensity_voxels'], 0)
            candidate.data[0, 0, 0] += 50.
            self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'violated')

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy native comparison')
    def test_gaussian_intermediate_storage_propagated_through_linear_sampling(self):
        from scipy.ndimage import gaussian_filter, map_coordinates
        source = source_frame((9, 8, 7))
        rng = np.random.default_rng(17101)
        source.data[:] = rng.uniform(1e5, 7e5, source.data.shape).astype('float32')
        spec = specification(source, antialias_sigma=[.5, .7, .9],
                             antialias_dtype='float32', mask_antialias_sigma=[.5, .7, .9],
                             mask_threshold_after_antialias=True, mask_round_decimals=6,
                             mask_interpolation='linear')
        p = op._parse(source, spec)
        value, radius = _gaussian_envelope(source.data, p['antialias_sigma'], 'float32',
                                           p['axis_order'], 4., 'nearest')
        native_aa = gaussian_filter(source.data.transpose(2, 1, 0), [.9, .7, .5], mode='nearest').transpose(2, 1, 0)
        self.assertTrue(np.all(np.abs(native_aa.astype(float)-value.astype(float)) <= radius))
        q = np.indices(source.data.shape).reshape(3, -1)+np.array([.13, .23, .37])[:, None]
        native = map_coordinates(native_aa.transpose(2, 1, 0), q[::-1], order=1, mode='nearest')
        candidate = op.expected_operation(source, spec)
        candidate.data = native.reshape(source.data.shape)
        report = verify_native_operation(source, candidate, spec)
        self.assertIn(report['status'], ('satisfied', 'indeterminate'), report)
        self.assertEqual(report['violating_intensity_voxels'], 0)
        candidate.data[3, 3, 3] += 10.
        self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'violated')
        candidate.data = native.reshape(source.data.shape).copy()
        candidate.mask[3, 3, 3] = 0
        report = verify_native_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'violated')
        self.assertGreater(report['violating_roi_voxels'], 0)

    def test_unsupported_weighted_integer_is_unavailable_not_accepted(self):
        source = source_frame(dtype='float64')
        spec = specification(source, output_dtype='int16')
        candidate = op.expected_operation(source, spec)
        report = verify_native_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'unavailable')
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')

    def test_exact_integer_selection_retains_original_boundary_policy(self):
        source = source_frame(dtype='int16')
        spec = specification(source, index_map=np.eye(4).tolist(), interpolation='nearest')
        candidate = op.expected_operation(source, spec)
        self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'satisfied')
        spec['index_map'][0][3] = .5
        candidate = op.expected_operation(source, spec)
        self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'indeterminate')

    def test_storage_dtype_is_an_observed_contract(self):
        source = source_frame()
        spec = specification(source)
        candidate = op.expected_operation(source, spec)
        candidate.data = candidate.data.astype('float64')
        self.assertEqual(verify_native_operation(source, candidate, spec)['status'], 'violated')

    def test_nearest_still_abstains_when_coordinate_budget_is_insufficient(self):
        source = source_frame(dtype='int16')
        source.affine[:3, 3] = [1e12, -1e12, 1e12]
        spec = specification(source, interpolation='nearest')
        candidate = op.expected_operation(source, spec)
        report = verify_native_operation(source, candidate, spec)
        self.assertEqual(report['nominal_reference']['status'], 'satisfied')
        self.assertEqual(report['status'], 'unavailable')
        self.assertIn('coordinate radius', report['reason'])

    def test_subnormal_source_cannot_receive_a_normal_arithmetic_approval(self):
        source = source_frame((3, 3, 3), 'float64')
        source.data[:] = 1e-320
        spec = specification(source, intensity_atol=0.)
        candidate = op.expected_operation(source, spec)
        report = verify_native_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'unavailable')
        self.assertIn('Subnormal', report['reason'])


if __name__ == '__main__':
    unittest.main()
