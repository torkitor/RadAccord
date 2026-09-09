"""Small native MIRP tests: independently declared grids and untouched features."""
from copy import deepcopy
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


def example_inputs(modality='mr', oblique=True):
    from mirp._images.generic_image import GenericImage
    from mirp._masks.base_mask import BaseMask
    z, y, x = np.indices((9, 11, 13), dtype=float)
    image_data = 10 + .37*z + .13*y*y + 2*np.sin(.7*x) + .09*z*y
    roi = ((z-4)**2/10 + (y-5)**2/18 + (x-6)**2/21 < 1)
    roi[3:6, 6:8, 7:9] = False
    angle = .27 if oblique else 0.
    c, s = np.cos(angle), np.sin(angle)
    orientation = np.array([[1., 0., 0.], [0., c, -s], [0., s, c]])
    metadata = dict(image_origin=(3., 4., 5.), image_orientation=orientation,
                    image_spacing=(1.5, 1.1, .9), image_dimensions=image_data.shape,
                    sample_name='private-subject-name', image_modality=modality)
    image = GenericImage(image_data=image_data, **metadata)
    mask = BaseMask(roi_name='private-roi-name', image_data=roi, **metadata)
    return image, mask


def integer_inputs(dtype=np.uint8):
    from mirp._images.generic_image import GenericImage
    from mirp._masks.base_mask import BaseMask
    data = np.arange(125).reshape(5, 5, 5).astype(dtype)
    if data.dtype.kind == 'i':
        data -= 64
    roi = np.zeros(data.shape, dtype=bool)
    roi[1:4, 1:4, 1:4] = True
    geometry = dict(image_origin=(0., 0., 0.), image_orientation=np.eye(3),
                    image_spacing=(1., 1., 1.), image_dimensions=data.shape,
                    image_modality='mr', sample_name='synthetic_integer_ivh')
    return (GenericImage(image_data=data, **geometry),
            BaseMask(roi_name='synthetic_roi', image_data=roi, **geometry))


@unittest.skipUnless(find_spec('mirp'), 'The optional MIRP dependency is not installed.')
class NativeMirpTests(unittest.TestCase):
    def test_grid_declared_before_output_and_native_table_unchanged(self):
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        image, mask = example_inputs()
        config = {'base_feature_families': ['statistical'], 'new_spacing': 1.3}
        native = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask),
            **config, export_features=True, export_images=True, write_features=False,
            write_images=False, image_export_format='native')[0][0]
        result = audit_mirp(image, mask, config=config)
        pd.testing.assert_frame_equal(result['features'], native, check_exact=True)
        declaration = result['report']['declarations']['original_image_export']
        # Analytic sizes from original ZYX=(9,11,13), spacings=(1.5,1.1,.9).
        self.assertEqual(declaration['candidate_shape'], [9, 10, 11])
        np.testing.assert_allclose(np.diag(declaration['index_map'])[:3],
                                   [1.3/.9, 1.3/1.1, 1.3/1.5], rtol=0, atol=1e-15)
        self.assertEqual(result['report']['status'], 'satisfied', result['report'])
        self.assertTrue(result['report']['relationship_acceptance'])
        text = json.dumps(result['report'], allow_nan=False)
        self.assertNotIn('private-subject-name', text)
        self.assertNotIn('private-roi-name', text)

    def test_identity_export_and_mask_registration_skip(self):
        from radaccord.mirp import audit_mirp
        image, mask = example_inputs()
        result = audit_mirp(image, mask, config={'base_feature_families': ['statistical']})
        self.assertEqual(result['report']['status'], 'satisfied', result['report'])
        declaration = result['report']['declarations']['original_image_export']
        np.testing.assert_array_equal(declaration['index_map'], np.eye(4))
        self.assertTrue(declaration['mask_skip'])
        self.assertIsNone(declaration['antialias_sigma'])

    def test_integer_identity_ivh_keeps_native_features_and_bounded_scope(self):
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        # uint8 IVH exposed a pandas 3.0.2 incompatibility in the rc1 environment.
        # The other integer types exercise the explicitly admitted identity set.
        for dtype in (np.uint8, np.uint16, np.int16, np.int32):
            with self.subTest(dtype=np.dtype(dtype).name):
                image, mask = integer_inputs(dtype)
                config = {'base_feature_families': ['ivh']}
                native = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask),
                    **config, export_features=True, export_images=True, write_features=False,
                    write_images=False, image_export_format='native')[0][0]
                result = audit_mirp(image, mask, config=config)
                pd.testing.assert_frame_equal(result['features'], native, check_exact=True)
                report = result['report']
                self.assertEqual(report['status'], 'satisfied', report)
                self.assertTrue(report['relationship_acceptance'])
                declaration = report['declarations']['original_image_export']
                self.assertEqual(declaration['output_dtype'], np.dtype(dtype).name)
                self.assertEqual(report['source']['source_dtype'], np.dtype(dtype).name)
                self.assertEqual(declaration['interpolation'], 'nearest')
                self.assertEqual(declaration['intensity_atol'], 0.)
                np.testing.assert_array_equal(declaration['index_map'], np.eye(4))
                self.assertTrue(declaration['mask_skip'])
                self.assertIsNone(declaration['antialias_sigma'])
                self.assertEqual(report['checkpoints'][0]['max_intensity_error'], 0.)
                self.assertIn('feature_formulae', report['unverified_obligations'])
                self.assertIn('feature_value_validity', report['unverified_obligations'])
                self.assertEqual(report['acceptance_scope'],
                                 'post_extraction_original_input_and_source_centre_coverage')

    def test_integer_nonidentity_and_uncovered_storage_abstain_without_changing_features(self):
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        cases = [(np.uint8, {'new_spacing': .8, 'anti_aliasing': aa}) for aa in (False, True)]
        cases.append((np.uint64, {}))
        for dtype, processing in cases:
            with self.subTest(dtype=np.dtype(dtype).name, processing=processing):
                image, mask = integer_inputs(dtype)
                config = {'base_feature_families': ['statistical'], **processing}
                native = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask),
                    **config, export_features=True, export_images=True, write_features=False,
                    write_images=False, image_export_format='native')[0][0]
                result = audit_mirp(image, mask, config=config)
                pd.testing.assert_frame_equal(result['features'], native, check_exact=True)
                self.assertEqual(result['report']['status'], 'unavailable')
                self.assertFalse(result['report']['relationship_acceptance'])
                self.assertFalse(result['report']['declarations'])

    def test_unsupported_ct_executes_without_changing_native_features(self):
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        image, mask = example_inputs(modality='ct')
        config = {'base_feature_families': ['statistical'], 'new_spacing': 1.3}
        native = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask),
            **config, export_features=True, export_images=True, write_features=False,
            write_images=False, image_export_format='native')[0][0]
        result = audit_mirp(image, mask, config=config)
        pd.testing.assert_frame_equal(result['features'], native, check_exact=True)
        self.assertEqual(result['report']['status'], 'unavailable')
        self.assertFalse(result['report']['relationship_acceptance'])

    def test_altered_export_cannot_redeclare_expected_geometry(self):
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        image, mask = example_inputs()
        config = {'base_feature_families': ['statistical'], 'new_spacing': 1.3}

        def altered(**kwargs):
            result = extract_features_and_images(**kwargs)
            exported_image = result[0][1][0]
            exported_mask = result[0][2][0]
            for item in (exported_image, exported_mask.roi, exported_mask.roi_intensity,
                         exported_mask.roi_morphology):
                item.image_origin = tuple(np.asarray(item.image_origin) + [0., 0., 11.])
            return result

        with patch('mirp.extract_features_and_images', side_effect=altered):
            result = audit_mirp(image, mask, config=config)
        self.assertEqual(result['report']['status'], 'violated', result['report'])
        self.assertFalse(result['report']['relationship_acceptance'])
        expected = result['report']['declarations']['original_image_export']['index_map']
        # Source X index origin remains determined by source dimensions/spacing.
        self.assertAlmostEqual(expected[0][3], .5*(13-1)-.5*(9-1)*1.3/.9)

    def test_nifti_selected_label_and_private_paths_not_exported(self):
        import SimpleITK as sitk
        from radaccord.mirp import audit_mirp
        native_image, native_mask = example_inputs(oblique=False)
        image = sitk.GetImageFromArray(native_image.get_voxel_grid())
        image.SetSpacing(tuple(native_image.image_spacing[::-1]))
        mask = sitk.GetImageFromArray(native_mask.roi.get_voxel_grid().astype(np.uint8)*2)
        mask.CopyInformation(image)
        with tempfile.TemporaryDirectory() as directory:
            image_path = str(Path(directory)/'private-person-image.nii.gz')
            mask_path = str(Path(directory)/'private-person-mask.nii.gz')
            sitk.WriteImage(image, image_path); sitk.WriteImage(mask, mask_path)
            result = audit_mirp(image_path, mask_path, label=2, config={
                'image_modality': 'mr', 'new_spacing': 1.3,
                'base_feature_families': ['statistical']})
            self.assertEqual(result['report']['status'], 'satisfied', result['report'])
            self.assertEqual(result['report']['source']['selected_voxels'],
                             int(np.count_nonzero(native_mask.roi.get_voxel_grid())))
            text = json.dumps(result['report'], allow_nan=False)
            self.assertNotIn('private-person', text)
            self.assertNotIn(directory, text)

    def test_close_but_distinct_source_grids_abstain(self):
        from radaccord.mirp import audit_mirp
        image, mask = example_inputs()
        mask.roi.image_origin = tuple(np.asarray(mask.roi.image_origin)+[5e-5, 0., 0.])
        result = audit_mirp(image, mask, config={
            'base_feature_families': ['statistical'], 'new_spacing': 1.3})
        self.assertEqual(result['report']['status'], 'unavailable')
        self.assertFalse(result['report']['relationship_acceptance'])


if __name__ == '__main__':
    unittest.main()
