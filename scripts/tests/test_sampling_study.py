"""Small analytic checks of the study producer and its comparison boundaries."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_sampling_study as study


class SamplingStudyTests(unittest.TestCase):
    def test_native_sampling_of_known_ramp_and_header_blind_error(self):
        x, y, z = np.indices((7, 8, 9), dtype=float)
        mask = np.zeros(x.shape, dtype=np.int16)
        mask[1:6, 1:7, 1:8] = 1
        source = study.Frame(x + 10 * y + 100 * z, mask, np.diag([2., 3., 4., 1.]))
        pair = study.to_sitk(source)
        shape = (13, 22, 33)
        correct, paired = study.from_sitk(study.resample(pair, shape, (1., 1., 1.)))
        self.assertAlmostEqual(correct.data[1, 1, 1], 0.5 + 10 / 3 + 25, places=11)
        spec = study.declaration(np.diag([0.5, 1 / 3, 0.25, 1.]), shape, 'linear')
        self.assertEqual(paired['status'], 'satisfied')
        self.assertEqual(study.source_geometry(source, correct, spec)['status'], 'satisfied')
        # One RAS mm = half a source x voxel. Metadata stays exactly intended.
        wrong, wrong_paired = study.from_sitk(study.resample(pair, shape, (1., 1., 1.), displacement=(-1., 0., 0.)))
        self.assertAlmostEqual(wrong.data[1, 1, 1] - correct.data[1, 1, 1], 0.5, places=11)
        self.assertEqual(wrong_paired['status'], 'satisfied')
        self.assertEqual(study.source_geometry(source, wrong, spec)['status'], 'satisfied')
        self.assertEqual(study.sampling_witness(source, wrong, spec)['status'], 'violated')

    def test_crop_is_outside_legacy_domain_and_activity_retains_small_changes(self):
        source = study.Frame(np.arange(125., dtype=float).reshape(5, 5, 5),
                             np.ones((5, 5, 5), dtype=np.int16), np.eye(4))
        b = np.eye(4)
        b[:3, 3] = 1.
        cropped = study.Frame(source.data[1:4, 1:4, 1:4], source.mask[1:4, 1:4, 1:4], b)
        spec = study.declaration(b, (3, 3, 3))
        self.assertEqual(study.legacy(source, cropped, spec)['status'], 'not_applicable')
        result = study.sampling_witness(source, cropped, spec)
        self.assertEqual(result['status'], 'satisfied')
        self.assertEqual(result['coverage']['missing_roi_voxels'], 98)
        self.assertEqual(result['feature_reuse']['decision'], 'blocked')
        empty = study.replace(cropped, mask=np.zeros(cropped.mask.shape, dtype=np.int16))
        saved = study.roundtrip(source, empty, spec)
        self.assertEqual(saved['status'], 'violated')
        self.assertFalse(saved['sampling']['checks']['roi'])
        self.assertEqual(saved['sampling']['coverage']['candidate_roi_voxels'], 0)
        slightly_changed = study.replace(cropped, data=cropped.data + 1e-8)
        activity = study.activity(slightly_changed, cropped)
        self.assertTrue(activity['any_exact_decoded_change'])
        self.assertFalse(activity['active'])

    def test_preselected_subset_does_not_replace_unavailable_volume(self):
        # Generated tiny fixtures exercise dataset.json and private export only;
        # no clinical data or clinical paths are opened by this test.
        with TemporaryDirectory(prefix='radaccord_fixture_') as folder:
            directory = Path(folder)
            dataset = directory / 'generated_fixture'
            dataset.mkdir()
            entries = []
            for index in range(4):
                frame = study.Frame(np.arange(125., dtype=float).reshape(5, 5, 5) + index * 1000 + .25,
                    np.full((5, 5, 5), 0 if index == 1 else 1, dtype=np.int16), np.eye(4))
                image, mask = study.save_pair(frame, dataset, f'fixture_{index}')
                entries.append({'image': image.name, 'label': mask.name})
            (dataset / 'dataset.json').write_text(json.dumps({'training': entries}), encoding='utf-8')
            output, private = directory / 'records', directory / 'native_inputs'
            args = ['run_sampling_study.py', '--dataset-root', str(dataset), '--output', str(output),
                    '--native-input-output', str(private)]
            original_resample = study.resample

            def fail_partway(pair, *args, **kwargs):
                if 2000 <= pair[0][0, 0, 0] < 3000:
                    raise RuntimeError('Constructed native-operation failure for ledger test.')
                return original_resample(pair, *args, **kwargs)

            with patch.object(sys, 'argv', args), patch.object(study, 'resample', side_effect=fail_partway), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(study.main(), 2)
            summary = json.loads((output / 'run_summary.json').read_text())
            self.assertEqual(summary['counts']['attempted_volumes'], 4)
            self.assertEqual(summary['counts']['evaluated_volumes'], 2)
            self.assertEqual(summary['datasets'][0]['planned_case_counts'], dict.fromkeys(study.CASE_ORDER, 4))
            self.assertEqual(summary['counts']['cases'], 33)
            manifest = [json.loads(line) for line in (private / 'manifest.jsonl').read_text().splitlines()]
            self.assertEqual(len(manifest), 6)
            self.assertEqual({row['volume_id'] for row in manifest}, {'fixture_0_image', 'fixture_2_image'})
            self.assertTrue(all(not Path(file['path']).is_absolute() for row in manifest for file in row['files']))
            self.assertEqual({row['role'] for row in manifest}, set(summary['native_input_roles']))
            volumes = [json.loads(line) for line in (output / 'volumes.jsonl').read_text().splitlines()]
            self.assertTrue(all(len(row['case_ledger']) == 14 for row in volumes))
            self.assertTrue(all(case['execution_status'] == 'not_reached'
                                and case['reason'] == 'source_input_unavailable' for case in volumes[1]['case_ledger']))
            failed = volumes[2]
            self.assertEqual(failed['failed_case'], 'isotropic_0p8mm')
            self.assertEqual(sum(case['execution_status'] == 'completed' for case in failed['case_ledger']), 5)
            self.assertEqual(sum(case['execution_status'] == 'unavailable' for case in failed['case_ledger']), 1)
            self.assertEqual(sum(case['execution_status'] == 'not_reached' for case in failed['case_ledger']), 8)
            self.assertTrue(all(case['execution_status'] == 'completed' for case in volumes[3]['case_ledger']))


if __name__ == '__main__':
    unittest.main()
