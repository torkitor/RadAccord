"""Plan realization/analysis fixtures use tiny non-image bytes, never clinical data."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_prospective_plans as builder
from scripts import run_operational_benchmark as benchmark


def fixtures(root, excluded=('Task02_Heart', 1)):
    eligibility, receipt, private = [], [], {}
    for task in builder.COLLECTIONS:
        for rank in range(1, 13):
            basename = 'synthetic_'+str(rank)+'.nii.gz'
            identity = task+'_'+basename.removesuffix('.nii.gz')
            eligible = (task, rank) != excluded
            source = {'task': task, 'selection_rank': rank, 'source_basename': basename,
                      'source_eligible': eligible, 'exclusion_reasons': [] if eligible else ['synthetic_exclusion'],
                      'image_sha256': '1'*64, 'mask_sha256': '2'*64}
            crop = {'id': identity, 'task': task, 'selection_rank': rank, 'source_eligible': eligible,
                    'source_image_sha256': source['image_sha256'], 'source_mask_sha256': source['mask_sha256'],
                    'status': 'prepared_and_verified' if eligible else 'source_excluded'}
            if eligible:
                private[identity] = {}
                for kind in ('image', 'mask'):
                    path = root/(identity+'_'+kind+'.synthetic_bytes')
                    path.write_bytes((identity+'|'+kind).encode())
                    private[identity][kind] = str(path)
                    crop[kind+'_sha256'] = benchmark.digest(path)
                    crop[kind+'_verification'] = {'decoded_array_equal': True, 'decoded_dtype_equal': True,
                        'maximum_world_error_mm': 0., 'geometry_tolerance_mm': 1e-4,
                        'selected_roi_completely_retained': True}
                crop.update(label=1, context_mm=10.)
            eligibility.append(source); receipt.append(crop)
    return {'schema': 'radaccord-new-clinical-eligibility-1', 'selected_slots': 24, 'records': eligibility}, \
           {'schema_version': 'clinical-crop-receipt-1', 'records': receipt}, private


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def freeze_for(plan, path):
    files = {('software/' if name.endswith('_contracts') else 'radaccord/')+name+'.py': '9'*64
             for name in ('evidence', 'operators', 'numerics', 'mirp', 'pyradiomics', 'physical_contracts', 'sampling_contracts')}
    record = {'mode': plan['mode'], 'plan_sha256': benchmark.digest(path), 'files': files,
              'environments': {engine: {'packages': {engine: 'fixture'}} for engine in benchmark.ENGINES}}
    freeze_path = path.with_name(plan['mode']+'_freeze.json')
    write(freeze_path, record)
    return freeze_path, record


def native_record(slot, freeze, direct, audited):
    engine = slot['engine']
    sources = {name: freeze['files'][('software/' if name.endswith('_contracts') else 'radaccord/')+name+'.py']
               for name in ('evidence', 'operators', 'numerics', engine, 'physical_contracts', 'sampling_contracts')}
    return dict(slot, completed=True, native_values_unchanged=True, baseline_seconds=direct,
        audited_seconds=audited, absolute_overhead_seconds=audited-direct,
        paired_log_ratio=benchmark.math.log(audited/direct), pair_peak_memory_after={'bytes': 1000},
        warmup_comparison={'completed': True, 'native_values_unchanged': True},
        report={'status': 'satisfied', 'engine': {'name': engine, 'version': 'fixture'},
                'checker': {'source_sha256': sources, 'implementation_sha256': benchmark.config_digest(sources)},
                'checkpoints': [{'status': 'satisfied', 'coverage': {'status': 'satisfied'},
                                 'feature_reuse': {'decision': 'requires_reextraction'}}]})


class ProspectivePlanTests(unittest.TestCase):
    def test_excluded_first_rank_is_not_replaced_in_timing_or_intention_denominators(self):
        with tempfile.TemporaryDirectory() as temporary:
            eligible, receipt, manifest = fixtures(Path(temporary))
            selected, inputs = builder.selected_records(eligible, receipt, manifest)
            coverage = builder.realize_plan('coverage', selected, inputs, {})
            timing = builder.realize_plan('timing', selected, inputs, {})
            self.assertEqual((coverage['intention_to_evaluate_pairs'], coverage['native_planned_pairs']), (144, 138))
            self.assertEqual((timing['intention_to_evaluate_pairs'], timing['native_planned_pairs']), (128, 112))
            heart = [row for row in timing['inputs'] if row['collection'] == 'Task02_Heart']
            self.assertEqual([row['selection_rank'] for row in heart], [2, 3, 4])
            self.assertEqual(len(timing['selected_inputs']), 8)
            self.assertNotIn(str(Path(temporary)), json.dumps(coverage))

    def test_native_configs_are_modality_specific_without_hidden_feature_selection(self):
        mr = builder.configuration('pyradiomics', 'cubic_2', 'mr')
        ct = builder.configuration('pyradiomics', 'linear_1p5', 'ct')
        self.assertEqual(mr['setting']['binCount'], 32); self.assertNotIn('binWidth', mr['setting'])
        self.assertEqual(ct['setting']['binWidth'], 25.); self.assertNotIn('binCount', ct['setting'])
        self.assertEqual(mr['setting']['resampledPixelSpacing'], [2.]*3)
        self.assertEqual(ct['setting']['interpolator'], 'sitkLinear')
        self.assertNotIn('featureClass', ct)
        mirp = builder.configuration('mirp', 'cubic_2', 'ct')
        self.assertTrue(mirp['anti_aliasing']); self.assertEqual(mirp['base_feature_families'], ['all'])

    def test_preparation_failure_is_retained_and_extra_manifest_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            eligible, receipt, manifest = fixtures(Path(temporary), excluded=None)
            failed = receipt['records'][0]; failed['status'] = 'preparation_failed'
            failed['reason_code'] = 'synthetic_crop_failure'; manifest.pop(failed['id'])
            selected, inputs = builder.selected_records(eligible, receipt, manifest)
            self.assertEqual(selected[0]['status'], 'preparation_failed'); self.assertEqual(len(inputs), 23)
            manifest['unexpected'] = {'image': 'private', 'mask': 'private'}
            with self.assertRaises(ValueError):
                builder.selected_records(eligible, receipt, manifest)

    def test_unreadable_excluded_source_may_have_unavailable_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            eligible, receipt, manifest = fixtures(Path(temporary))
            excluded_source, excluded_crop = eligible['records'][0], receipt['records'][0]
            excluded_source.update(image_sha256=None, mask_sha256=None)
            excluded_crop.update(source_image_sha256=None, source_mask_sha256=None)
            selected, inputs = builder.selected_records(eligible, receipt, manifest)
            self.assertEqual(selected[0]['status'], 'source_excluded')
            self.assertIsNone(selected[0]['source_image_sha256'])
            self.assertEqual(len(inputs), 23)

    def test_source_and_crop_byte_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            eligible, receipt, manifest = fixtures(Path(temporary), excluded=None)
            wrong = deepcopy(receipt); wrong['records'][0]['source_image_sha256'] = 'f'*64
            with self.assertRaises(ValueError):
                builder.selected_records(eligible, wrong, manifest)
            Path(next(iter(manifest.values()))['image']).write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                builder.selected_records(eligible, receipt, manifest)

    def test_build_writes_two_bound_freezes_without_image_decoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); eligible, receipt, manifest = fixtures(root)
            environment = {engine: {'python': 'fixture', 'packages': {engine: 'fixture', 'numpy': 'fixture', 'SimpleITK': 'fixture'}}
                           for engine in benchmark.ENGINES}
            paths = {name: root/(name+'.json') for name in ('eligibility', 'receipt', 'private', 'environments', 'general')}
            for name, value in [('eligibility', eligible), ('receipt', receipt), ('private', manifest), ('environments', environment), ('general', {})]:
                write(paths[name], value)
            names = benchmark.REQUIRED_FREEZE_FILES | {'scripts/build_prospective_plans.py', 'protocol/prospective_native_validation.md'}
            for name in names:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('synthetic source fixture')
            verified_files = {name: benchmark.digest(root/name) for name in names}
            verified_files.update({name+'.json': benchmark.digest(paths[name]) for name in ('eligibility', 'environments')})
            with patch.object(builder, 'ROOT', root), patch.object(benchmark, 'ROOT', root), \
                    patch.object(builder, 'verify_general', return_value={'files': verified_files}):
                output = root/'plans'
                result = builder.build(paths['receipt'], paths['private'], paths['eligibility'], paths['general'],
                                       paths['environments'], output)
                self.assertEqual(result['coverage']['native_planned_pairs'], 138)
                coverage = builder.read_json(output/'coverage_plan.json')
                self.assertEqual(coverage['provenance']['general_freeze']['sha256'], benchmark.digest(paths['general']))
                benchmark.verify_freeze(output/'coverage_freeze.json', output/'coverage_plan.json', paths['private'])
                self.assertNotIn(str(root), (output/'coverage_plan.json').read_text())

    def test_aggregate_keeps_interruption_and_uses_volume_medians_not_pooled_repeats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); eligible, receipt, manifest = fixtures(root, excluded=None)
            selected, inputs = builder.selected_records(eligible, receipt, manifest)
            plan = builder.realize_plan('timing', selected, inputs, {})
            plan_path = root/'timing_plan.json'; write(plan_path, plan)
            freeze_path, freeze = freeze_for(plan, plan_path)
            run = root/'run'; run.mkdir()
            slots = benchmark.planned_slots(plan, 'pyradiomics')
            write(run/'run_metadata.json', {'mode': 'timing', 'engine': 'pyradiomics',
                'plan_sha256': benchmark.digest(plan_path), 'freeze_sha256': benchmark.digest(freeze_path)})
            write(run/'planned_slots.json', slots)
            first = [row for row in slots if row['collection'] == 'Task02_Heart' and row['workflow'] == 'identity_mr']
            starts, records = [], []
            for slot in first:
                rank = next(row['selection_rank'] for row in plan['inputs'] if row['id'] == slot['input_id'])
                if rank == 1 or rank == 2 and slot['repeat'] == 0:
                    starts.append(dict(slot, attempt_started_utc='synthetic'))
                    records.append(native_record(slot, freeze, 1., 2. if rank == 1 else 10.))
                elif rank == 2 and slot['repeat'] == 1:
                    starts.append(dict(slot, attempt_started_utc='synthetic'))
            (run/'attempt_starts.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in starts))
            (run/'cases.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))
            output = root/'summary.json'; result = builder.summarize([plan_path], [run], output)
            group = next(row for row in result['groups'] if row['collection'] == 'Task02_Heart' and
                         row['workflow'] == 'identity_mr' and row['engine'] == 'pyradiomics')
            self.assertEqual((group['attempted_pairs'], group['completed_pairs'], group['started_without_record_pairs']), (6, 5, 1))
            self.assertEqual(group['unstarted_pairs'], 10)
            self.assertEqual(group['volume_medians']['absolute_overhead_seconds']['median'], 5.)
            self.assertEqual(group['volume_medians']['absolute_overhead_seconds']['minimum'], 1.)
            self.assertEqual(group['volume_medians']['absolute_overhead_seconds']['maximum'], 9.)
            self.assertEqual(group['checkpoint_count'], 5)
            second = root/'summary_again.json'; builder.summarize([plan_path], [run], second)
            self.assertEqual(output.read_bytes(), second.read_bytes())
            records[0]['report']['checker']['source_sha256']['numerics'] = '0'*64
            (run/'cases.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))
            with self.assertRaises(ValueError):
                builder.summarize([plan_path], [run], root/'tampered_summary.json')


if __name__ == '__main__':
    unittest.main()
