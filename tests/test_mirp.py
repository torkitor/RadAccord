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


def ct_inputs(dtype=np.float64):
    image, mask = example_inputs(modality='ct')
    z, y, x = np.indices(image.image_dimension)
    # Negative HU, half-to-even values, and values below -1000. These are
    # synthetic intensities, deliberately independent of any study image.
    data = -1500.5 + 29*z + 13*y + 2*x + (x % 2)*.25
    image.set_voxel_grid(data.astype(dtype))
    return image, mask


@unittest.skipUnless(find_spec('mirp'), 'The optional MIRP dependency is not installed.')
class NativeMirpTests(unittest.TestCase):
    def unchanged(self, image, mask, config):
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        native = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask),
            **config, export_features=True, export_images=True, write_features=False,
            write_images=False, image_export_format='native')[0][0]
        result = audit_mirp(deepcopy(image), deepcopy(mask), config=config)
        pd.testing.assert_frame_equal(result['features'], native, check_exact=True)
        return result

    def test_ct_identity_rounding_and_no_clipping_preserve_native_features(self):
        from radaccord.evidence import frame_record
        from radaccord.mirp import _frame
        for dtype in (np.float32, np.float64, np.int16, np.int32):
            with self.subTest(dtype=np.dtype(dtype).name):
                image, mask = ct_inputs(dtype)
                expected = _frame(image, mask.roi)
                expected.data[:] = np.round(expected.data)
                result = self.unchanged(image, mask, {'base_feature_families': ['statistical']})
                report = result['report']
                self.assertEqual(report['status'], 'satisfied', report)
                self.assertTrue(report['relationship_acceptance'])
                self.assertEqual(report['source']['image_sha256'], frame_record(expected)['image_sha256'])
                self.assertLess(float(result['features']['stat_min'].iloc[0]), -1000.)
                self.assertEqual([x['checkpoint'] for x in report['checkpoints']],
                                 ['original_feature_input', 'original_image_export_after_extraction'])
                self.assertTrue(all(x['max_intensity_error'] == 0. for x in report['checkpoints']))

    def test_ct_nearest_without_antialiasing_preserves_native_features(self):
        for dtype in (np.float32, np.float64, np.int16, np.int32):
            with self.subTest(dtype=np.dtype(dtype).name):
                image, mask = ct_inputs(dtype)
                result = self.unchanged(image, mask, {'base_feature_families': ['statistical'],
                    'new_spacing': 1.3, 'spline_order': 0, 'roi_spline_order': 0,
                    'anti_aliasing': False})
                self.assertEqual(result['report']['status'], 'satisfied', result['report'])
                self.assertTrue(result['report']['relationship_acceptance'])
                declaration = result['report']['declarations']['original_feature_input']
                self.assertEqual(declaration['intensity_atol'], 0.)
                self.assertEqual(declaration['output_dtype'], np.dtype(dtype).name)

    def test_ct_native_rounding_has_distinct_intermediate_and_final_stages(self):
        from mirp._images.ct_image import CTImage
        original = CTImage.update_image_data
        for dtype in (np.float32, np.float64, np.int16):
            for antialias in (False, True):
                with self.subTest(dtype=np.dtype(dtype).name, antialias=antialias):
                    image, _ = ct_inputs(dtype)
                    image = image.promote()
                    image.update_separate_slices(False)
                    records = []

                    def record_rounding(instance):
                        before = instance.image_data.copy()
                        original(instance)
                        records.append((before, instance.image_data.copy()))

                    with patch.object(CTImage, 'update_image_data', record_rounding):
                        image.interpolate(interpolate=True, new_spacing=(1.3, 1.3, 1.3),
                            translation=(0., 0., 0.), rotation=0., spline_order=1,
                            anti_aliasing=antialias, anti_aliasing_smoothing_beta=.98)
                    self.assertEqual(len(records), 2 if antialias else 1)
                    for before, after in records:
                        np.testing.assert_array_equal(after, np.round(before))
                        self.assertEqual(after.dtype, before.dtype)
                        self.assertEqual(before.dtype, np.dtype('float32') if antialias else dtype)
                    if antialias:
                        self.assertGreater(np.count_nonzero(records[0][0] != records[0][1]), 0)

    def test_dispatch_observer_detects_input_fault_hidden_by_clean_export(self):
        from mirp._workflows.standardWorkflow import StandardWorkflow
        original = StandardWorkflow.standard_extraction

        def altered(workflow, **kwargs):
            compute = workflow._compute_radiomics_features

            def changed_argument(image, mask):
                altered_image = deepcopy(image)
                altered_image.set_voxel_grid(image.get_voxel_grid()+1.)
                yield from compute(image=altered_image, mask=mask)

            workflow._compute_radiomics_features = changed_argument
            try:
                return original(workflow, **kwargs)
            finally:
                workflow._compute_radiomics_features = compute

        cases = [(example_inputs(), {'base_feature_families': ['statistical']}),
                 (ct_inputs(), {'base_feature_families': ['statistical'], 'new_spacing': 1.3})]
        for inputs, config in cases:
            with self.subTest(modality=inputs[0].modality):
                with patch.object(StandardWorkflow, 'standard_extraction', altered):
                    result = self.unchanged(*inputs, config)
                before, after = result['report']['checkpoints']
                self.assertEqual(before['status'], 'violated')
                self.assertIn(after['status'], ('satisfied', 'indeterminate'))
                self.assertFalse(result['report']['relationship_acceptance'])

    def test_observer_preserves_multifamily_native_dispatch_and_cache_execution(self):
        result = self.unchanged(*ct_inputs(np.float32), {
            'base_feature_families': ['morphological', 'statistical', 'glcm', 'glrlm'],
            'base_discretisation_method': 'fixed_bin_size', 'base_discretisation_bin_width': 25.,
            'new_spacing': 1.3})
        report = result['report']
        self.assertGreater(report['feature_tables'][0]['columns'], 60)
        self.assertEqual(len(report['checkpoints']), 2)
        self.assertIn(report['status'], ('satisfied', 'indeterminate'), report)

    def test_observer_cleanup_and_native_exception_propagation(self):
        from mirp._workflows.standardWorkflow import StandardWorkflow
        from radaccord.mirp import audit_mirp
        original = StandardWorkflow.standard_extraction
        workflows = []

        def track(workflow, **kwargs):
            workflows.append(workflow)
            return original(workflow, **kwargs)

        with patch.object(StandardWorkflow, 'standard_extraction', track), \
                patch.object(StandardWorkflow, '_compute_radiomics_features',
                             side_effect=RuntimeError('synthetic native failure')) as method:
            with self.assertRaisesRegex(RuntimeError, 'synthetic native failure'):
                audit_mirp(*example_inputs(), config={'base_feature_families': ['statistical']})
            self.assertIs(StandardWorkflow._compute_radiomics_features, method)
            self.assertEqual(len(workflows), 1)
            self.assertNotIn('_compute_radiomics_features', vars(workflows[0]))

    def test_nondefault_scheduler_has_no_claimed_dispatch_observation(self):
        result = self.unchanged(*example_inputs(), {'base_feature_families': ['statistical'],
                                                   'parallel_backend': 'none', 'num_cpus': 1})
        self.assertEqual(result['report']['status'], 'unavailable')
        self.assertEqual(result['report']['checkpoints'][0]['reason_code'],
                         'sequential_observer_not_available')
        self.assertFalse(result['report']['relationship_acceptance'])

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
                                 'original_feature_dispatch_and_export_with_source_centre_coverage')

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

    def test_weighted_ct_integer_without_antialiasing_remains_unavailable(self):
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        image, mask = ct_inputs(np.int16)
        config = {'base_feature_families': ['statistical'], 'new_spacing': 1.3,
                  'anti_aliasing': False}
        native = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask),
            **config, export_features=True, export_images=True, write_features=False,
            write_images=False, image_export_format='native')[0][0]
        result = audit_mirp(image, mask, config=config)
        pd.testing.assert_frame_equal(result['features'], native, check_exact=True)
        self.assertEqual(result['report']['status'], 'unavailable')
        self.assertFalse(result['report']['relationship_acceptance'])

    def test_weighted_ct_float_and_antialiased_integer_keep_native_outputs(self):
        for dtype in (np.float32, np.float64, np.int16, np.int32):
            for antialias in (False, True):
                if not antialias and np.dtype(dtype).kind == 'i':
                    continue
                for order in (1, 3):
                    with self.subTest(dtype=np.dtype(dtype).name, antialias=antialias, order=order):
                        result = self.unchanged(*ct_inputs(dtype), {
                            'base_feature_families': ['statistical'], 'new_spacing': 1.3,
                            'spline_order': order, 'anti_aliasing': antialias})
                        report = result['report']
                        self.assertIn(report['status'], ('satisfied', 'indeterminate'), report)
                        declaration = report['declarations']['original_feature_input']
                        self.assertEqual(declaration['output_dtype'], 'float32' if antialias
                                         else np.dtype(dtype).name)
                        self.assertEqual(declaration['output_quantisation'], 'nearest_even')
                        self.assertEqual(declaration['antialias_quantisation'],
                                         'nearest_even' if antialias else None)
                        for check in report['checkpoints']:
                            self.assertEqual(check['violating_intensity_voxels'], 0)
                            self.assertEqual(check['violating_roi_voxels'], 0)
                            if check['status'] == 'indeterminate':
                                self.assertEqual(check['feature_reuse']['decision'], 'blocked')
                        if report['status'] == 'indeterminate':
                            self.assertFalse(report['relationship_acceptance'])

    def test_altered_export_cannot_redeclare_expected_geometry(self):
        from mirp._workflows.standardWorkflow import StandardWorkflow
        from radaccord.mirp import audit_mirp
        image, mask = example_inputs()
        config = {'base_feature_families': ['statistical'], 'new_spacing': 1.3}

        original = StandardWorkflow.standard_extraction

        def altered(workflow, **kwargs):
            result = original(workflow, **kwargs)
            exported_image = result[1][0]
            exported_mask = result[2][0]
            for item in (exported_image, exported_mask.roi, exported_mask.roi_intensity,
                         exported_mask.roi_morphology):
                item.image_origin = tuple(np.asarray(item.image_origin) + [0., 0., 11.])
            return result

        with patch.object(StandardWorkflow, 'standard_extraction', altered):
            result = audit_mirp(image, mask, config=config)
        self.assertEqual(result['report']['status'], 'violated', result['report'])
        self.assertFalse(result['report']['relationship_acceptance'])
        self.assertEqual(result['report']['checkpoints'][0]['status'], 'satisfied')
        self.assertEqual(result['report']['checkpoints'][1]['status'], 'violated')
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
