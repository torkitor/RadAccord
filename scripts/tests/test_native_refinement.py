"""Controller/configuration regression fixtures; no native extraction is run."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


_scripts = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_scripts))
try:
    runner = importlib.import_module('run_native_refinement')
finally:
    sys.path.remove(str(_scripts))


class NativeRefinementControllerTests(unittest.TestCase):
    def test_ct_preserves_native_bin_width_for_both_case_spellings(self):
        for modality in ('ct', 'CT'):
            config = runner.configuration('pyradiomics', 'identity', modality)
            self.assertEqual(config['setting']['binWidth'], 25.)
            self.assertNotIn('binCount', config['setting'])

    def test_mr_uses_declared_fixed_bin_number(self):
        for modality in ('mr', 'MR'):
            config = runner.configuration('pyradiomics', 'linear_1p3', modality)
            self.assertEqual(config['setting']['binCount'], 32)
            self.assertNotIn('binWidth', config['setting'])
            self.assertEqual(config['setting']['interpolator'], 'sitkLinear')

    def test_timeout_or_process_failure_does_not_drop_the_next_slot(self):
        for failure in ('timeout', 'process_exit'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                plan_path, freeze_path = root/'plan.json', root/'freeze.json'
                plan = {'inputs': [{'id': 'fixture_synthetic', 'kind': 'synthetic', 'seed': 30000,
                                    'modality': 'mr', 'operations': ['identity', 'linear_1p3']}]}
                plan_path.write_text(json.dumps(plan), encoding='utf-8')
                freeze = {'files': {'protocol/native_study_plan.json': runner.digest(plan_path)},
                          'timeout_seconds_per_pair': .01}
                freeze_path.write_text(json.dumps(freeze), encoding='utf-8')
                output, private = root/'output', root/'private'
                calls = []

                def fake_process(command, **kwargs):
                    calls.append(command)
                    if len(calls) == 1:
                        if failure == 'timeout':
                            raise subprocess.TimeoutExpired(command, .01)
                        return SimpleNamespace(returncode=9)
                    result_path = Path(command[command.index('--worker-result')+1])
                    result = {'input_id': 'fixture_synthetic', 'source_kind': 'synthetic', 'modality': 'mr',
                              'engine': 'mirp', 'operation': 'linear_1p3',
                              'config': runner.configuration('mirp', 'linear_1p3', 'mr'),
                              'completed': True, 'native_values_unchanged': True}
                    result_path.write_text(json.dumps(result), encoding='utf-8')
                    return SimpleNamespace(returncode=0)

                arguments = ['run_native_refinement', '--engine', 'mirp', '--plan', str(plan_path),
                             '--freeze', str(freeze_path), '--dataset-root', str(root),
                             '--output', str(output), '--private-log-dir', str(private)]
                with patch.object(sys, 'argv', arguments), patch.object(runner, 'verify_freeze', return_value=freeze), \
                        patch.object(runner.subprocess, 'run', side_effect=fake_process), \
                        patch.object(runner, 'version', return_value='test'), contextlib.redirect_stdout(io.StringIO()):
                    runner.main()
                rows = [json.loads(line) for line in (output/'cases.jsonl').read_text().splitlines()]
                self.assertEqual(len(calls), 2)
                self.assertEqual([row['operation'] for row in rows], ['identity', 'linear_1p3'])
                self.assertFalse(rows[0]['completed'])
                self.assertEqual(rows[0]['reason_code'], 'native_worker_timeout' if failure == 'timeout' else 'native_worker_incomplete')
                self.assertTrue(rows[1]['completed'])
                summary = json.loads((output/'run_summary.json').read_text())
                self.assertEqual((summary['planned'], summary['attempted'], summary['completed']), (2, 2, 1))
                self.assertEqual(summary['records_sha256'], runner.digest(output/'cases.jsonl'))


if __name__ == '__main__':
    unittest.main()
