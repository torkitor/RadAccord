"""Synthetic/controller checks only; these tests never open clinical images."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_operational_benchmark as runner


def plan():
    return {'schema_version': runner.SCHEMA, 'mode': 'timing', 'repeats': 4, 'warmup_pairs_per_worker': 1,
            'native_threads': 1, 'timeout_seconds_per_pair': 300,
            'inputs': [{'id': 'synthetic_fixture', 'kind': 'synthetic', 'seed': 987654, 'modality': 'mr'}],
            'workflows': [{'id': 'identity', 'modalities': ['mr'], 'configs': {
                'pyradiomics': {'setting': {'binCount': 16}, 'imageType': {'Original': {}},
                               'featureClass': {'firstorder': ['Mean']}},
                'mirp': {'base_feature_families': ['statistics']}}}]}


def pair():
    data = np.arange(9*10*11, dtype=float).reshape(9, 10, 11)/13
    labels = np.zeros_like(data, dtype='uint8'); labels[2:-2, 2:-2, 2:-2] = 1
    images = runner.sitk.GetImageFromArray(data), runner.sitk.GetImageFromArray(labels)
    for image in images:
        image.SetSpacing((1.1, 1.3, 1.7)); image.SetOrigin((17., 23., -9.))
    return images


class OperationalBenchmarkTests(unittest.TestCase):
    def test_coverage_has_one_pair_without_warmup_or_overhead_statistics(self):
        value = plan(); value.update(mode='coverage', repeats=1, warmup_pairs_per_worker=0)
        runner.validate_plan(value)
        self.assertEqual(len(runner.planned_slots(value, 'pyradiomics')), 1)
        calls = []
        def callback(arm):
            def run(inputs):
                calls.append(arm)
                return {'one': 3.}, {'status': 'satisfied'} if arm == 'B' else None
            return run
        with patch.object(runner, 'native_callbacks', return_value=(lambda: None, {arm: callback(arm) for arm in 'AB'})), \
                patch.object(runner, 'peak_memory', return_value={'bytes': 10, 'available': True}):
            result = runner.measure_pair('pyradiomics', None, 'mr', 'fixture', {}, 'BA', mode='coverage')
        self.assertEqual(calls, ['B', 'A'])
        self.assertEqual(result['warmup'], {})
        self.assertTrue(result['completed']); self.assertTrue(result['native_values_unchanged'])
        self.assertNotIn('absolute_overhead_seconds', result)
        self.assertNotIn('seconds', result['extractions']['A'])
        row = dict(runner.planned_slots(value, 'pyradiomics')[0], **result)
        summary = runner.summarize([row], mode='coverage')
        self.assertEqual(summary['mode'], 'coverage')
        self.assertNotIn('paired_log_ratio', summary['volume_workflow_summaries'][0])
        with self.assertRaises(ValueError):
            runner.summarize([row], mode='timing')
        for invalid in ({'repeats': 2}, {'warmup_pairs_per_worker': 1}):
            wrong = deepcopy(value); wrong.update(invalid)
            with self.assertRaises(ValueError):
                runner.validate_plan(wrong)

    def test_plan_is_counterbalanced_per_input_and_workflow(self):
        value = runner.validate_plan(plan())
        for engine in runner.ENGINES:
            slots = runner.planned_slots(value, engine)
            self.assertEqual([row['slot'] for row in slots], list(range(4)))
            self.assertEqual(sum(row['order'] == 'AB' for row in slots), 2)
            self.assertEqual(sum(row['order'] == 'BA' for row in slots), 2)
            self.assertEqual(slots, runner.planned_slots(deepcopy(value), engine))
        for repeats in (1, 3, True, 2.5):
            invalid = plan(); invalid['repeats'] = repeats
            with self.assertRaises(ValueError):
                runner.validate_plan(invalid)

    def test_public_plan_rejects_private_paths_and_duplicate_ids(self):
        for private in ('C:\\private\\settings.yaml', '/private/settings', 'private@example.invalid'):
            invalid = plan(); invalid['workflows'][0]['configs']['mirp']['settings'] = private
            with self.assertRaises(ValueError):
                runner.validate_plan(invalid)
        invalid = plan(); invalid['inputs'][0]['image'] = 'private.nii.gz'
        with self.assertRaises(ValueError):
            runner.validate_plan(invalid)
        invalid = plan(); invalid['inputs'].append(deepcopy(invalid['inputs'][0]))
        with self.assertRaises(ValueError):
            runner.validate_plan(invalid)

    def test_warmup_is_separate_and_measured_order_is_respected(self):
        for order in ('AB', 'BA'):
            calls, prepared = [], []
            def prepare():
                value = object(); prepared.append(value); return value
            def callback(arm):
                def run(value):
                    calls.append(arm)
                    return {'one': np.float64(3.)}, {'status': 'satisfied'} if arm == 'B' else None
                return run
            with patch.object(runner, 'native_callbacks', return_value=(prepare, {arm: callback(arm) for arm in 'AB'})), \
                    patch.object(runner, 'peak_memory', return_value={'bytes': 10, 'available': True}):
                result = runner.measure_pair('pyradiomics', None, 'mr', 'fixture', {}, order)
            self.assertEqual(''.join(calls), order[::-1]+order)
            self.assertEqual(len({id(value) for value in prepared}), 4)
            self.assertTrue(result['completed'])
            self.assertTrue(result['native_values_unchanged'])
            self.assertTrue(result['warmup_comparison']['native_values_unchanged'])
            self.assertEqual(set(result['warmup']), {'A', 'B'})
            self.assertEqual(set(result['measured']), {'A', 'B'})
            self.assertAlmostEqual(result['absolute_overhead_seconds'],
                                   result['audited_seconds']-result['baseline_seconds'])

    def test_warmup_value_mismatch_is_retained_without_replacing_measured_pair(self):
        calls = {'A': 0, 'B': 0}
        def callback(arm):
            def run(inputs):
                calls[arm] += 1
                value = 9. if arm == 'B' and calls[arm] == 1 else 3.
                return {'one': value}, {'status': 'satisfied'} if arm == 'B' else None
            return run
        with patch.object(runner, 'native_callbacks', return_value=(lambda: None, {arm: callback(arm) for arm in 'AB'})), \
                patch.object(runner, 'peak_memory', return_value={'bytes': 10, 'available': True}):
            result = runner.measure_pair('pyradiomics', None, 'mr', 'fixture', {}, 'AB')
        self.assertTrue(result['completed']); self.assertTrue(result['native_values_unchanged'])
        self.assertFalse(result['warmup_comparison']['native_values_unchanged'])
        self.assertEqual(result['warmup_comparison']['comparison_details']['affected_keys'], 1)
        self.assertEqual(result['comparison_details']['affected_keys'], 0)

    def test_worker_constructed_tasks_are_coverage_only(self):
        for mode in ('coverage', 'timing'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                value = plan()
                if mode == 'coverage':
                    value.update(mode=mode, repeats=1, warmup_pairs_per_worker=0)
                args = SimpleNamespace(engine='pyradiomics', private_inputs=None,
                                       worker_result=Path(temporary)/'result.json')
                slot = runner.planned_slots(value, args.engine)[0]
                with patch.object(runner, 'load_pair', return_value=None), \
                        patch.object(runner, 'measure_pair', return_value={'completed': True}), \
                        patch.object(runner, 'constructed_correction_tasks', return_value=[]) as tasks:
                    runner.worker(args, value, slot)
                self.assertEqual(tasks.call_count, 1 if mode == 'coverage' else 0)

    def test_failed_warmup_does_not_fabricate_measured_pair(self):
        def failure(inputs):
            raise RuntimeError('C:\\private\\sensitive_input.nii.gz')
        with patch.object(runner, 'native_callbacks', return_value=(lambda: None, {'A': failure, 'B': failure})), \
                patch.object(runner, 'peak_memory', return_value={'bytes': 10, 'available': True}):
            result = runner.measure_pair('pyradiomics', None, 'mr', 'fixture', {}, 'AB')
        self.assertFalse(result['completed'])
        self.assertEqual(result['reason_code'], 'warmup_incomplete')
        self.assertEqual(result['measured'], {})
        self.assertNotIn('private', json.dumps(result))

    def test_constructed_fault_and_correction_compare_same_sources(self):
        records = runner.constructed_correction_tasks(pair())
        self.assertEqual(len(records), 2)
        for row in records:
            self.assertEqual(row['valid_control']['radaccord']['status'], 'satisfied')
            self.assertEqual(row['fault']['paired_geometry']['status'], 'satisfied')
            self.assertTrue(row['fault']['activity']['active'])
            self.assertEqual(row['fault']['radaccord']['status'], 'violated')
            self.assertTrue(row['restored_declared_relationship'])
            self.assertEqual(row['source']['frame_sha256'], row['correction']['candidate']['frame_sha256'])
        self.assertEqual(records[0]['fault']['source_aware_geometry']['status'], 'violated')
        self.assertEqual(records[1]['fault']['source_aware_geometry']['status'], 'satisfied')

    def test_summary_uses_paired_metrics_and_separates_volumes(self):
        rows = []
        for input_id, values in [('first', [(1., 2.), (10., 11.)]), ('second', [(2., 8.)])]:
            for index, (direct, audited) in enumerate(values):
                rows.append({'input_id': input_id, 'workflow': 'identity', 'order': 'AB' if index % 2 else 'BA',
                             'completed': True, 'native_values_unchanged': True, 'baseline_seconds': direct,
                             'audited_seconds': audited, 'absolute_overhead_seconds': audited-direct,
                             'paired_log_ratio': np.log(audited/direct), 'report': {'status': 'satisfied'},
                             'pair_peak_memory_after': {'bytes': 12345}})
        result = runner.summarize(rows)
        self.assertEqual(result['completed'], 3)
        self.assertEqual(len(result['volume_workflow_summaries']), 2)
        first = result['volume_workflow_summaries'][0]
        self.assertEqual(first['absolute_overhead_seconds']['median'], 1.)
        self.assertAlmostEqual(first['paired_log_ratio']['median'], (np.log(2.)+np.log(1.1))/2)
        self.assertEqual(first['pair_lifetime_peak_bytes']['median'], 12345)

    def test_controller_retains_timeout_and_process_failure_before_next_success(self):
        for failure in ('timeout', 'exit'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); value = plan(); value['repeats'] = 2
                plan_path, freeze_path = root/'plan.json', root/'freeze.json'
                plan_path.write_text(json.dumps(value)); freeze_path.write_text('{}')
                args = SimpleNamespace(engine='pyradiomics', plan=plan_path, freeze=freeze_path,
                    private_inputs=None, output=root/'public', private_log_dir=root/'private')
                slots = runner.planned_slots(value, args.engine); calls = []
                def process(command, **kwargs):
                    calls.append(command)
                    if len(calls) == 1:
                        if failure == 'timeout':
                            raise subprocess.TimeoutExpired(command, .01)
                        return SimpleNamespace(returncode=17)
                    result = dict(slots[1], completed=True, native_values_unchanged=True)
                    Path(command[command.index('--worker-result')+1]).write_text(json.dumps(result))
                    return SimpleNamespace(returncode=0)
                output = io.StringIO()
                with patch.object(runner.subprocess, 'run', side_effect=process), \
                        patch.object(runner, 'version', return_value='fixture'), contextlib.redirect_stdout(output):
                    summary = runner.run_controller(args, value, {})
                rows = [json.loads(line) for line in (args.output/'cases.jsonl').read_text().splitlines()]
                self.assertEqual(len(rows), 2)
                self.assertFalse(rows[0]['completed']); self.assertTrue(rows[1]['completed'])
                self.assertEqual(rows[0]['reason_code'], 'worker_timeout' if failure == 'timeout' else 'worker_incomplete')
                self.assertEqual(summary['records_sha256'], runner.digest(args.output/'cases.jsonl'))
                self.assertNotIn(str(root), output.getvalue())

    def test_frozen_source_and_environment_identity_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'source.py'; source.write_text('fixture')
            plan_path = root/'plan.json'; plan_path.write_text('{}')
            freeze_path = root/'freeze.json'
            freeze = {'schema_version': runner.SCHEMA, 'plan_sha256': runner.digest(plan_path),
                      'files': {'source.py': runner.digest(source)}}
            freeze_path.write_text(json.dumps(freeze))
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'REQUIRED_FREEZE_FILES', {'source.py'}):
                runner.verify_freeze(freeze_path, plan_path)
                source.write_text('changed')
                with self.assertRaises(ValueError):
                    runner.verify_freeze(freeze_path, plan_path)
        with self.assertRaises(ValueError):
            runner.verify_environment({}, 'mirp')
        freeze = {'environments': {'mirp': {'python': runner.platform.python_version(),
            'packages': {'mirp': 'x', 'numpy': 'x', 'SimpleITK': 'x'}}}}
        with patch.object(runner, 'version', return_value='x'):
            runner.verify_environment(freeze, 'mirp')
        with patch.object(runner, 'version', return_value='y'), self.assertRaises(ValueError):
            runner.verify_environment(freeze, 'mirp')

    def test_create_freeze_binds_explicit_mode_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'source.py'; source.write_text('synthetic fixture')
            plan_path = root/'plan.json'; plan_path.write_text(json.dumps(plan()))
            output = root/'freeze.json'
            environments = {engine: {'python': runner.platform.python_version(),
                                    'packages': {engine: 'fixture', 'numpy': 'fixture', 'SimpleITK': 'fixture'}}
                            for engine in runner.ENGINES}
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'REQUIRED_FREEZE_FILES', {'source.py'}):
                freeze = runner.create_freeze(plan_path, environments, output)
                self.assertEqual(freeze['mode'], 'timing')
                self.assertEqual(freeze['plan_sha256'], runner.digest(plan_path))
                runner.verify_freeze(output, plan_path)
                with self.assertRaises(ValueError):
                    runner.create_freeze(plan_path, environments, output)

    def test_peak_memory_records_actual_process_measurement(self):
        result = runner.peak_memory()
        self.assertTrue(result['available'])
        self.assertGreater(result['bytes'], 0)
        self.assertIn(result['method'], ('windows_peak_working_set', 'resource_ru_maxrss'))


if __name__ == '__main__':
    unittest.main()
