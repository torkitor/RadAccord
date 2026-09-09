"""File-boundary regression checks for sampling decisions and linked checkpoints."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import nibabel as nib

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('sampling_cli', ROOT / 'radaccord_sampling.py')
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
from physical_contracts import Frame, write_frame


class SamplingCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        grid = np.indices((9, 9, 9))
        data = (3 * grid[0] + 5 * grid[1] - grid[2]).astype(float)
        mask = np.zeros(data.shape, dtype=np.int16)
        mask[1:-1, 1:-1, 1:-1] = 1
        affine = np.diag([1., 2., 3., 1.])
        self.frame = Frame(data, mask, affine)
        self.source = self.save('source', self.frame)

    def save(self, stem, frame):
        image, mask = write_frame(frame, self.root, stem)
        return {'image': image.name, 'mask': mask.name, 'label': 1}

    def contract(self, shape=(9, 9, 9), scale=1., interpolation='nearest'):
        return {'index_map': np.diag([scale, scale, scale, 1.]).tolist(),
                'candidate_shape': list(shape), 'interpolation': interpolation,
                'outside_value': 0., 'position_atol_mm': 1e-4, 'intensity_atol': 1e-4}

    def test_linked_chain_reports_first_observed_failure(self):
        shifted_affine = self.frame.affine.copy()
        shifted_affine[0, 3] += 2.
        shifted = self.save('shifted', Frame(self.frame.data, self.frame.mask, shifted_affine))
        steps = [{'source': self.source, 'candidate': self.source, 'sampling': self.contract()},
                 {'source': self.source, 'candidate': shifted, 'sampling': self.contract()}]
        report = cli.audit_plan({'schema_version': '1.0', 'steps': steps}, self.root)
        self.assertEqual(report['first_failed_checkpoint'], 2)
        self.assertEqual(report['checkpoints'][0]['decision'], 'input_roi_preserved')
        self.assertEqual(report['checkpoints'][1]['decision'], 'violated')
        self.assertEqual(report['feature_reuse'], 'blocked')
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn('shifted_image', cli.render_html(report))
        # A disconnected source is not accepted as an observed continuation.
        other = self.save('other', Frame(self.frame.data + 1, self.frame.mask, self.frame.affine))
        steps[1] = {'source': other, 'candidate': other, 'sampling': self.contract()}
        disconnected = cli.audit_plan({'schema_version': '1.0', 'steps': steps}, self.root)
        self.assertEqual(disconnected['checkpoints'][1]['decision'], 'unavailable')
        self.assertFalse(disconnected['checkpoints'][1]['linked_to_previous_checkpoint'])

    def test_correct_resampling_requires_reextraction_and_missing_file_abstains(self):
        affine = self.frame.affine @ np.diag([2., 2., 2., 1.])
        candidate = self.save('coarse', Frame(self.frame.data[::2, ::2, ::2].copy(),
                                             self.frame.mask[::2, ::2, ::2].copy(), affine))
        plan = {'schema_version': '1.0', 'steps': [{
            'source': self.source, 'candidate': candidate,
            'sampling': self.contract((5, 5, 5), 2., 'linear')}]}
        report = cli.audit_plan(plan, self.root)
        self.assertEqual(report['decision'], 'sampling_satisfied')
        self.assertEqual(report['feature_reuse'], 'requires_reextraction')
        self.assertIn('Extract features again', cli.render_html(report))
        plan['steps'][0]['candidate']['image'] = 'private_missing_patient_file.nii.gz'
        unavailable = cli.audit_plan(plan, self.root)
        self.assertEqual(unavailable['checkpoints'][0]['decision'], 'unavailable')
        self.assertEqual(unavailable['feature_reuse'], 'blocked')
        self.assertNotIn('private_missing_patient_file', json.dumps(unavailable))

    def test_correct_crop_that_removes_entire_roi_is_reported_as_support_loss(self):
        # Write empty observed masks directly; the legacy writer excludes them.
        for kind in ('image', 'mask'):
            item = nib.Nifti1Image(np.zeros((1, 1, 1), dtype=np.int16), self.frame.affine)
            item.header.set_xyzt_units('mm')
            item.set_qform(self.frame.affine, code=1)
            item.set_sform(self.frame.affine, code=1)
            nib.save(item, self.root / ('empty_' + kind + '.nii.gz'))
        plan = {'schema_version': '1.0', 'steps': [{
            'source': self.source,
            'candidate': {'image': 'empty_image.nii.gz', 'mask': 'empty_mask.nii.gz'},
            'sampling': self.contract((1, 1, 1))}]}
        report = cli.audit_plan(plan, self.root)
        self.assertEqual(report['checkpoints'][0]['decision'], 'roi_support_lost')
        self.assertEqual(report['checkpoints'][0]['sampling']['coverage']['missing_roi_voxels'], 343)
        self.assertEqual(report['feature_reuse'], 'blocked')

    def test_small_mask_rotation_exceeds_physical_pair_tolerance(self):
        candidate = self.save('rotation', self.frame)
        mask_path = self.root / candidate['mask']
        item = nib.load(mask_path)
        angle = 3e-5
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0, 0],
                             [np.sin(angle), np.cos(angle), 0, 0],
                             [0, 0, 1, 0], [0, 0, 0, 1]])
        affine = rotation @ self.frame.affine
        modified = nib.Nifti1Image(np.asanyarray(item.dataobj), affine)
        modified.header.set_xyzt_units('mm')
        modified.set_qform(affine, code=1)
        modified.set_sform(affine, code=1)
        nib.save(modified, mask_path)
        plan = {'schema_version': '1.0', 'steps': [{
            'source': self.source, 'candidate': candidate, 'sampling': self.contract()}]}
        report = cli.audit_plan(plan, self.root)
        row = report['checkpoints'][0]
        self.assertTrue(row['paired_geometry']['candidate']['same_affine'])
        self.assertGreater(row['paired_max_corner_error_mm']['candidate'], 1e-4)
        self.assertEqual(row['decision'], 'violated')
        self.assertEqual(report['feature_reuse'], 'blocked')
        plan['steps'][0]['source'] = candidate
        source_report = cli.audit_plan(plan, self.root)
        self.assertFalse(source_report['checkpoints'][0]['paired_geometry']['source']['physical_corner_agreement'])


if __name__ == '__main__':
    unittest.main()
