"""Analytical fixtures and independent native producers; no clinical inputs."""
import unittest
import importlib.util
import numpy as np
from radaccord.legacy import Frame
from radaccord.operators import (expected_operation, expected_mask, verify_operation,
                                 _coefficients, _interpolate, _gaussian)


def fixture(seed=30000, shape=(7, 8, 9)):
    rng = np.random.default_rng(seed)
    data = rng.normal(180., 23., shape)
    mask = np.zeros(shape, dtype=np.int16)
    mask[1:-1, 2:-1, 1:-2] = 7
    angle = .31
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                         [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    affine = np.eye(4)
    affine[:3, :3] = rotation@np.diag([.8, 1.3, 2.1])
    affine[:3, 3] = [23.7, -87.4, 6.3]
    return Frame(data, mask, affine, 7)


def declaration(source, **changes):
    spec = dict(index_map=np.eye(4).tolist(), candidate_shape=list(source.data.shape),
                interpolation='bspline3', outside_value=-17., position_atol_mm=1e-4,
                intensity_atol=1e-4, index_boundary_atol=1e-9)
    spec.update(changes)
    return spec


def sitk_image(frame, mask=False):
    import SimpleITK as sitk
    out = sitk.GetImageFromArray((frame.mask if mask else frame.data).transpose(2, 1, 0))
    lps = np.diag([-1., -1., 1.])
    matrix = lps@frame.affine[:3, :3]
    spacing = np.linalg.norm(matrix, axis=0)
    out.SetSpacing(tuple(spacing))
    out.SetOrigin(tuple(lps@frame.affine[:3, 3]))
    out.SetDirection(tuple((matrix/spacing).ravel()))
    return out


class OperatorTests(unittest.TestCase):
    def test_bspline_coefficients_reconstruct_samples(self):
        for seed in range(30000, 30004):
            source = fixture(seed)
            expected = expected_operation(source, declaration(source))
            np.testing.assert_allclose(expected.data, source.data, atol=3e-12, rtol=0.)
            np.testing.assert_array_equal(expected.mask, source.mask)

    def test_constant_and_linear_analytic_fields(self):
        source = fixture()
        x, y, z = np.indices(source.data.shape)
        source.data[:] = 13.+2*x-3*y+.7*z
        q = np.array([[2.17, 3.32], [3.18, 2.31], [4.13, 3.82]])
        values, _ = _interpolate(source.data, q, 'linear', 'sitk')
        np.testing.assert_allclose(values, 13.+2*q[0]-3*q[1]+.7*q[2], rtol=0., atol=2e-14)
        source.data[:] = 61.25
        coefficients = _coefficients(source.data, 'sitk', [2, 1, 0])
        values, _ = _interpolate(source.data, q, 'bspline3', 'sitk', coefficients=coefficients)
        np.testing.assert_allclose(values, 61.25, atol=1e-12, rtol=0.)

    def test_cubic_against_sitk_at_oblique_world_points(self):
        import SimpleITK as sitk
        for seed in range(30000, 30004):
            source = fixture(seed)
            rng = np.random.default_rng(seed+1)
            q = rng.uniform(-.49, np.asarray(source.data.shape)[:, None]-.51, (3, 89))
            coefficients = _coefficients(source.data, 'sitk', [2, 1, 0])
            expected, _ = _interpolate(source.data, q, 'bspline3', 'sitk', coefficients=coefficients)
            image = sitk_image(source)
            points = source.affine[:3, :3]@q+source.affine[:3, 3, None]
            points[:2] *= -1
            actual = np.array([image.EvaluateAtPhysicalPoint(tuple(point), sitk.sitkBSpline) for point in points.T])
            np.testing.assert_allclose(actual, expected, rtol=0., atol=1e-10)

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy producer is not installed')
    def test_cubic_nearest_matches_scipy_including_edges(self):
        from scipy.ndimage import map_coordinates
        source = fixture()
        rng = np.random.default_rng(30006)
        q = rng.uniform(-3., np.asarray(source.data.shape)[:, None]+3., (3, 237))
        coefficients = _coefficients(source.data, 'nearest', [2, 1, 0])
        values, _ = _interpolate(source.data, q, 'bspline3', 'nearest', coefficients=coefficients)
        expected = map_coordinates(source.data.transpose(2, 1, 0), q[::-1], order=3, mode='nearest')
        np.testing.assert_allclose(values, expected, atol=1e-10, rtol=0.)

    def test_gaussian_impulse_matches_explicit_kernel(self):
        array = np.zeros((17, 1, 1))
        array[8, 0, 0] = 1.
        actual = _gaussian(array, [1., 0., 0.], 'float64', [2, 1, 0], 4., 'nearest')[:, 0, 0]
        kernel = np.exp(-np.arange(-4, 5, dtype=float)**2/2.)
        kernel /= kernel.sum()
        expected = np.zeros(17)
        expected[4:13] = kernel
        np.testing.assert_allclose(actual, expected, atol=0., rtol=0.)

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy producer is not installed')
    def test_gaussian_matches_scipy_dtype_axis_order_and_boundary(self):
        from scipy.ndimage import gaussian_filter
        array = fixture().data
        for dtype in ['float32', 'float64']:
            for boundary in ['nearest', 'constant']:
                actual = _gaussian(array, [.7, 1.2, 1.4], dtype, [2, 1, 0], 4., boundary)
                expected = gaussian_filter(array.transpose(2, 1, 0).astype(dtype), [1.4, 1.2, .7], mode=boundary).transpose(2, 1, 0)
                np.testing.assert_allclose(actual, expected, atol=2e-12 if dtype == 'float64' else 0., rtol=0.)

    def test_full_sitk_resample_operator_and_wrong_kernel(self):
        import SimpleITK as sitk
        source = fixture()
        b = np.eye(4)
        b[:3, :3] = np.diag([.81, .83, .87])
        b[:3, 3] = [.17, .23, .31]
        spec = declaration(source, index_map=b.tolist(), candidate_shape=[7, 8, 9])
        expected = expected_operation(source, spec)
        reference = sitk_image(expected)
        image = sitk.Resample(sitk_image(source), reference, sitk.Transform(), sitk.sitkBSpline, -17., sitk.sitkFloat64)
        mask = sitk.Resample(sitk_image(source, True), reference, sitk.Transform(), sitk.sitkNearestNeighbor, 0., sitk.sitkInt16)
        candidate = Frame(sitk.GetArrayFromImage(image).transpose(2, 1, 0), sitk.GetArrayFromImage(mask).transpose(2, 1, 0), expected.affine, 7)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'satisfied', report)
        self.assertEqual(report['feature_reuse']['decision'], 'requires_reextraction')
        wrong = dict(spec, interpolation='linear')
        self.assertEqual(verify_operation(source, candidate, wrong)['status'], 'violated')

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy producer is not installed')
    def test_mask_linear_rounding_and_intermediate_antialias_threshold(self):
        from scipy.ndimage import gaussian_filter, map_coordinates
        source = fixture()
        b = np.eye(4)
        b[:3, 3] = [.21, -.18, .27]
        spec = declaration(source, index_map=b.tolist(), boundary='nearest', output_dtype='float32',
                           antialias_sigma=[.3, .5, .8], mask_antialias_sigma=[.3, .5, .8],
                           mask_interpolation='linear', mask_boundary='constant', mask_round_decimals=6,
                           mask_threshold_after_antialias=True)
        q = b[:3, :3]@np.indices(source.data.shape).reshape(3, -1)+b[:3, 3, None]
        native_image = gaussian_filter(source.data.transpose(2, 1, 0).astype('float32'), [.8, .5, .3], mode='nearest')
        data = map_coordinates(native_image, q[::-1], order=3, mode='nearest').reshape(source.data.shape)
        native_mask = gaussian_filter((source.mask == 7).transpose(2, 1, 0).astype('float32'), [.8, .5, .3], mode='nearest')
        native_mask = np.round(native_mask, 6) >= .5
        mask = map_coordinates(native_mask.astype(float), q[::-1], order=1, mode='constant').reshape(source.data.shape)
        mask = (np.round(mask, 6) >= .5).astype(np.int16)*7
        candidate = Frame(data, mask, source.affine@b, 7)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'satisfied', report)
        np.testing.assert_array_equal(expected_mask(source, spec), mask == 7)
        bad = dict(spec, antialias_sigma=[0., 0., 0.])
        self.assertEqual(verify_operation(source, candidate, bad)['status'], 'violated')

    def test_nn_tie_indeterminate_but_strong_error_still_violates(self):
        source = fixture()
        b = np.eye(4)
        b[0, 3] = .5
        spec = declaration(source, interpolation='nearest', index_map=b.tolist())
        candidate = expected_operation(source, spec)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'indeterminate', report)
        self.assertEqual(report['strict_nominal_status'], 'satisfied')
        candidate.data[2, 2, 2] += 10000.
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'violated', report)
        self.assertGreater(report['violating_intensity_voxels'], 0)

    def test_mask_threshold_and_constant_boundary_abstain(self):
        source = fixture()
        source.mask[:] = 7
        b = np.eye(4)
        spec = declaration(source, boundary='nearest', mask_boundary='constant', mask_interpolation='linear')
        candidate = expected_operation(source, spec)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'indeterminate', report)
        self.assertGreater(report['ambiguous_roi_voxels'], 0)
        source.mask[:3] = 0
        b[0, 3] = .5
        spec.update(index_map=b.tolist(), mask_boundary='nearest')
        candidate = expected_operation(source, spec)
        self.assertEqual(verify_operation(source, candidate, spec)['status'], 'indeterminate')

    def test_shared_geometry_mutation_cannot_redefine_expected_map(self):
        source = fixture()
        spec = declaration(source)
        candidate = expected_operation(source, spec)
        candidate.affine[0, 3] += 2.
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'violated')
        self.assertFalse(report['checks']['position'])

    def test_roi_loss_distinct_from_correct_execution(self):
        source = fixture()
        spec = declaration(source, interpolation='nearest', candidate_shape=[1, 2, 3])
        candidate = expected_operation(source, spec)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'satisfied', report)
        self.assertEqual(report['coverage']['status'], 'violated')
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')
        self.assertEqual(report['candidate_roi_voxels'], 0)

    def test_supported_integer_cast_and_unsafe_overflow(self):
        import SimpleITK as sitk
        source = fixture()
        source.data[:] = -2.81
        spec = declaration(source, interpolation='nearest', output_dtype='int16')
        candidate = expected_operation(source, spec)
        native = sitk.GetArrayFromImage(sitk.Cast(sitk_image(source), sitk.sitkInt16)).transpose(2, 1, 0)
        np.testing.assert_array_equal(candidate.data, native)
        self.assertEqual(verify_operation(source, candidate, spec)['status'], 'satisfied')
        source.data[:] = 32768.
        self.assertEqual(verify_operation(source, candidate, spec)['status'], 'unavailable')

    def test_integer_cast_boundary_is_not_approved(self):
        source = fixture()
        source.data[:] = 12.
        spec = declaration(source, output_dtype='int16')
        candidate = expected_operation(source, spec)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'indeterminate', report)
        self.assertEqual(report['feature_reuse']['decision'], 'blocked')

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy producer is not installed')
    def test_scipy_integer_cast_is_distinct_and_declared(self):
        from scipy.ndimage import map_coordinates
        source = fixture()
        source.data[:] = -2.5
        spec = declaration(source, interpolation='nearest', boundary='nearest', output_dtype='int16', integer_cast='round_half_away')
        candidate = expected_operation(source, spec)
        q = np.indices(source.data.shape).reshape(3, -1)
        native = map_coordinates(source.data, q, order=0, mode='nearest', output='int16').reshape(source.data.shape)
        np.testing.assert_array_equal(candidate.data, native)
        self.assertEqual(verify_operation(source, candidate, spec)['status'], 'satisfied')
        self.assertEqual(verify_operation(source, candidate, dict(spec, integer_cast='truncate'))['status'], 'violated')

    def test_small_axes_and_empty_candidate_are_retained(self):
        source = fixture(shape=(1, 2, 3))
        source.mask[:] = 7
        spec = declaration(source)
        candidate = expected_operation(source, spec)
        np.testing.assert_allclose(candidate.data, source.data, atol=2e-12, rtol=0.)
        candidate.mask[:] = 0
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'violated')
        self.assertEqual(report['candidate_roi_voxels'], 0)

    def test_threshold_ambiguity_propagates_from_prefilter_stage(self):
        source = fixture(shape=(7, 5, 5))
        source.mask[:] = 0
        source.mask[3:, :, :] = 7
        # Select a declared threshold equal to the calculated blurred edge;
        # this fixture tests propagation, not correctness of the Gaussian.
        blurred = _gaussian(source.mask == 7, [.8, 0., 0.], 'float32', [2, 1, 0], 4., 'nearest')
        threshold = float(blurred[2, 2, 2])
        spec = declaration(source, interpolation='linear', mask_antialias_sigma=[.8, 0., 0.],
                           mask_threshold_after_antialias=True, mask_threshold=threshold)
        candidate = expected_operation(source, spec)
        report = verify_operation(source, candidate, spec)
        self.assertEqual(report['status'], 'indeterminate', report)
        self.assertGreater(report['ambiguous_roi_voxels'], 0)

    def test_unknown_profile_nonfinite_and_bad_shape(self):
        source = fixture()
        spec = declaration(source)
        candidate = expected_operation(source, spec)
        self.assertEqual(verify_operation(source, candidate, dict(spec, interpolation='lanczos'))['status'], 'unavailable')
        self.assertEqual(verify_operation(source, candidate, dict(spec, ignored_option=True))['status'], 'unavailable')
        self.assertEqual(verify_operation(source, candidate, dict(spec, candidate_shape=[2, 3, 4]))['status'], 'violated')
        candidate.data[1, 1, 1] = np.nan
        self.assertEqual(verify_operation(source, candidate, spec)['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
