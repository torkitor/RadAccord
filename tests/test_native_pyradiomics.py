"""Integration checks against unchanged PyRadiomics 3.0.1.

Run in the pinned native environment: python -m unittest discover -s tests
-p test_native_pyradiomics.py. These are development tests, not held-out data.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import numpy as np

try:
    import SimpleITK as sitk
    from radiomics import featureextractor
except ImportError:
    featureextractor = None

from radaccord.evidence import feature_digest, frame_from_sitk
from radaccord.pyradiomics import audit_pyradiomics, declare_pyradiomics


def inputs(dtype=np.float32):
    xyz = np.indices((13, 15, 11), dtype=float)
    data = (100 + 7*np.sin(.4*xyz[0]) + xyz[1]*xyz[2]/13).astype(dtype)
    mask = (((xyz[0]-6)/4)**2+((xyz[1]-7)/5)**2+((xyz[2]-5)/3)**2 < 1).astype('uint8')
    image = sitk.GetImageFromArray(data.transpose(2, 1, 0))
    roi = sitk.GetImageFromArray(mask.transpose(2, 1, 0))
    image.SetSpacing((.9, 1.3, 2.1)); image.SetOrigin((-31.2, 15.4, 26.1))
    theta = .2
    image.SetDirection((np.cos(theta), -np.sin(theta), 0., np.sin(theta), np.cos(theta), 0., 0., 0., 1.))
    roi.CopyInformation(image)
    return image, roi


def config(**settings):
    return {'setting': {'binWidth': 5., **settings}, 'imageType': {'Original': {}},
            'featureClass': {'shape': ['VoxelVolume', 'MeshVolume'],
                             'firstorder': ['Mean', 'Variance', 'Entropy'],
                             'glcm': ['Contrast', 'JointEntropy']}}


@unittest.skipIf(featureextractor is None, 'Install the pinned pyradiomics extra.')
class NativePyRadiomicsTests(unittest.TestCase):
    def assert_unchanged(self, parameters, dtype=np.float32):
        image, mask = inputs(dtype)
        original = featureextractor.RadiomicsFeatureExtractor(deepcopy(parameters)).execute(image, mask)
        native = {k: v for k, v in original.items() if not k.startswith('diagnostics_')}
        result = audit_pyradiomics(image, mask, config=parameters)
        self.assertEqual(feature_digest(native), feature_digest(result['features']))
        for key in native:
            np.testing.assert_array_equal(native[key], result['features'][key])
        self.assertGreater(len(native), 5)
        return result

    def test_no_resampling_keeps_every_feature_and_observes_boundaries(self):
        result = self.assert_unchanged(config())
        self.assertEqual(result['report']['status'], 'satisfied', result['report'])
        self.assertEqual([c['checkpoint'] for c in result['report']['checkpoints']],
                         ['loaded_input', 'shape_dispatch', 'feature_input:original'])

    def test_default_bspline_native_resampling(self):
        result = self.assert_unchanged(config(resampledPixelSpacing=[1.1, 1.1, 1.1]))
        self.assertEqual(result['report']['declarations']['loaded_input']['interpolation'], 'bspline3')
        self.assertEqual(result['report']['status'], 'satisfied', result['report'])

    def test_nearest_and_linear_with_padding_and_precrop(self):
        for interpolator in ('sitkNearestNeighbor', 'sitkLinear'):
            with self.subTest(interpolator=interpolator):
                result = self.assert_unchanged(config(resampledPixelSpacing=[1.1]*3,
                                                     interpolator=interpolator, padDistance=2))
                self.assertEqual(result['report']['status'], 'satisfied', result['report'])
        result = self.assert_unchanged(config(preCrop=True, padDistance=1))
        self.assertEqual(result['report']['status'], 'satisfied', result['report'])

    def test_preserved_integer_sampling(self):
        result = self.assert_unchanged(config(resampledPixelSpacing=[1.1]*3), np.int16)
        # Integer cast-boundary diagnostics can differ across native platforms.
        # Weighted integer sampling remains outside the admitted envelope;
        # retain nominal evidence without requiring one platform's cast outcome.
        self.assertEqual(result['report']['status'], 'unavailable', result['report'])
        self.assertEqual(len(result['report']['checkpoints']), 3)
        for checkpoint in result['report']['checkpoints']:
            with self.subTest(checkpoint=checkpoint['checkpoint']):
                self.assertEqual(checkpoint['status'], 'unavailable')
                self.assertIsNone(checkpoint['checks']['numerical_profile'])
                self.assertEqual(checkpoint['reason'],
                                 'Weighted integer output is outside the floating-point envelope')
                self.assertEqual(checkpoint['feature_reuse']['decision'], 'blocked')
                nominal = checkpoint['nominal_reference']
                self.assertIsInstance(nominal, dict)
                self.assertIn(nominal['status'], ('satisfied', 'violated', 'indeterminate'))
                self.assertIn('strict_nominal_status', nominal)

    def test_normalization_abstains_without_changing_requested_values(self):
        result = self.assert_unchanged(config(normalize=True, normalizeScale=100))
        self.assertEqual(result['report']['status'], 'unavailable')

    def test_filtered_image_is_observed_and_explicitly_unavailable(self):
        parameters = config()
        parameters['imageType']['Square'] = {}
        result = self.assert_unchanged(parameters)
        self.assertEqual(result['report']['status'], 'unavailable')
        self.assertIn('feature_input:square', [c['checkpoint'] for c in result['report']['checkpoints']])

    def test_configuration_and_source_are_bound_separately(self):
        first = audit_pyradiomics(*inputs(), config=config())['report']
        second = audit_pyradiomics(*inputs(), config=config(binWidth=10))['report']
        self.assertEqual(first['source']['frame_sha256'], second['source']['frame_sha256'])
        self.assertNotEqual(first['configuration_sha256'], second['configuration_sha256'])
        self.assertEqual(first['declaration_timing'], 'before_native_execute')
        json.dumps(first, allow_nan=False)

    def test_observed_corruption_is_detected_without_learning_grid_from_it(self):
        original = featureextractor.RadiomicsFeatureExtractor.loadImage
        def corrupt(*args, **kwargs):
            image, mask = original(*args, **kwargs)
            shifted_image, shifted_mask = sitk.Image(image), sitk.Image(mask)
            shifted_origin = tuple(np.asarray(image.GetOrigin()) + [1.7, -.4, 0])
            shifted_image.SetOrigin(shifted_origin); shifted_mask.SetOrigin(shifted_origin)
            return shifted_image, shifted_mask
        with patch.object(featureextractor.RadiomicsFeatureExtractor, 'loadImage', side_effect=corrupt):
            result = audit_pyradiomics(*inputs(), config=config())
        self.assertEqual(result['report']['status'], 'violated', result['report'])

    def test_expected_geometry_has_no_candidate_argument(self):
        image, mask = inputs()
        source = frame_from_sitk(image, mask)
        settings = featureextractor.RadiomicsFeatureExtractor(config(resampledPixelSpacing=[1.1]*3)).settings
        declared = declare_pyradiomics(source, settings)
        np.testing.assert_allclose(np.diag(declared['index_map'])[:3], [1.1/.9, 1.1/1.3, 1.1/2.1])

    def test_distinct_source_grids_abstain_instead_of_false_violation(self):
        image, mask = inputs(np.float64)
        image = image * 1000.
        mask.SetOrigin(tuple(np.asarray(image.GetOrigin()) + [5e-5, 0, 0]))
        parameters = config(resampledPixelSpacing=[1.17, 1.19, 1.23], interpolator='sitkLinear')
        native = featureextractor.RadiomicsFeatureExtractor(parameters).execute(image, mask)
        result = audit_pyradiomics(image, mask, config=parameters)
        self.assertEqual(result['report']['status'], 'unavailable')
        for key, value in result['features'].items():
            np.testing.assert_array_equal(value, native[key])

    def test_missing_runtime_setting_does_not_receive_a_pass(self):
        from radiomics import imageoperations
        original = imageoperations.getOriginalImage
        def remove_setting(image, mask, **kwargs):
            for values, name, settings in original(image, mask, **kwargs):
                settings = dict(settings)
                settings.pop('binWidth')
                yield values, name, settings
        with patch.object(imageoperations, 'getOriginalImage', side_effect=remove_setting):
            result = audit_pyradiomics(*inputs(), config=config())
        self.assertEqual(result['report']['status'], 'unavailable')
        checkpoint = result['report']['checkpoints'][-1]
        self.assertIn('binWidth', checkpoint['missing_declared_setting_keys'])


if __name__ == '__main__':
    unittest.main()
