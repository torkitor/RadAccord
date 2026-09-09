"""Small fabricated ledgers test integrity and denominators, not native results."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.summarize_native_study import canonical_digest, digest, summarize, write_outputs


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+'\n', encoding='utf-8')


class NativeSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        plan = {'schema_version': 'native-plan-1', 'inputs': [
            {'id': 's1', 'kind': 'synthetic', 'modality': 'mr', 'operations': ['identity', 'cubic_1p3']},
            {'id': 'c1', 'kind': 'public', 'modality': 'ct', 'operations': ['identity']}]}
        write_json(self.root/'protocol/native_study_plan.json', plan)
        self.frozen_paths = ['radaccord/evidence.py', 'radaccord/operators.py', 'radaccord/mirp.py',
                             'radaccord/pyradiomics.py', 'software/physical_contracts.py', 'software/sampling_contracts.py']
        for relative in self.frozen_paths:
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# Fabricated integrity fixture '+relative+'\n', encoding='utf-8')
        self.freeze = {relative: digest(self.root/relative) for relative in self.frozen_paths+['protocol/native_study_plan.json']}
        write_json(self.root/'protocol/native_freeze.json', {'schema_version': 'native-freeze-1', 'files': self.freeze})
        self.records = {}
        for engine in ['mirp', 'pyradiomics']:
            rows = []
            sources = {name: self.freeze[relative] for name, relative in {
                'evidence': 'radaccord/evidence.py', 'operators': 'radaccord/operators.py', engine: 'radaccord/'+engine+'.py',
                'physical_contracts': 'software/physical_contracts.py', 'sampling_contracts': 'software/sampling_contracts.py'}.items()}
            for item in plan['inputs']:
                for operation in item['operations']:
                    unavailable = engine == 'mirp' and item['modality'] == 'ct'
                    checkpoint = {'checkpoint': 'test_boundary', 'status': 'unavailable' if unavailable else 'satisfied'}
                    if unavailable:
                        checkpoint['reason_code'] = 'unsupported_modality'
                    else:
                        checkpoint.update(checks={'position': True, 'intensity': True, 'roi': True},
                                          coverage={'status': 'satisfied'}, feature_reuse={'decision': 'requires_reextraction'})
                    features = {'sha256': canonical_digest({'f': 1.}), 'count': 1, 'nonfinite_count': 0}
                    report = {'engine': {'name': engine, 'version': 'test'}, 'declaration_timing': 'before_native_execute',
                              'configuration_sha256': canonical_digest({}), 'status': checkpoint['status'],
                              'checkpoints': [checkpoint], 'elapsed_seconds': 2.,
                              'checker': {'numpy_version': 'test', 'source_sha256': sources,
                                          'implementation_sha256': canonical_digest(sources)}}
                    if engine == 'pyradiomics':
                        report['feature_values'] = features
                    rows.append({'engine': engine, 'input_id': item['id'], 'source_kind': item['kind'],
                                 'modality': item['modality'], 'operation': operation, 'completed': True,
                                 'config': {}, 'native_values_unchanged': True, 'baseline_values': features,
                                 'observed_values': features, 'baseline_seconds': 1., 'audited_seconds': 2.,
                                 'total_seconds': 3.1, 'report': report})
            self.records[engine] = rows
            self.save_engine(engine)

    def save_engine(self, engine):
        directory = self.root/'results'/engine
        directory.mkdir(parents=True, exist_ok=True)
        rows = self.records[engine]
        (directory/'cases.jsonl').write_text(''.join(json.dumps(row, sort_keys=True)+'\n' for row in rows), encoding='utf-8')
        run = {'schema_version': 'native-study-1', 'engine': engine, 'engine_version': 'test', 'numpy_version': 'test',
               'development': False, 'plan_sha256': self.freeze['protocol/native_study_plan.json'],
               'records_sha256': digest(directory/'cases.jsonl'), 'planned': 3, 'attempted': len(rows),
               'completed': sum(row['completed'] for row in rows),
               'unchanged': sum(row.get('native_values_unchanged', False) for row in rows)}
        write_json(directory/'run_summary.json', run)

    def summary(self):
        return summarize(self.root, [self.root/'results/mirp', self.root/'results/pyradiomics'])

    def test_balanced_plan_pair_and_checkpoint_denominators(self):
        result = self.summary()
        self.assertEqual(result['summary']['units'], dict(planned_inputs=2, planned_pairs_per_engine=3,
                                                          engines=2, retained_pairs=6, retained_pair_records=6,
                                                          interrupted_without_record=0, not_reached=0, recorded_checkpoints=6))
        totals = {row['engine']: row for row in result['summary']['pair_counts'] if row['grouping'] == 'engine'}
        self.assertEqual(totals['mirp']['unavailable'], 1)
        self.assertEqual(totals['mirp']['exact_native_values'], 3)
        self.assertEqual(totals['pyradiomics']['satisfied'], 3)
        self.assertEqual(len(result['summary']['non_satisfied_checkpoints']), 1)

    def test_record_tamper_is_rejected_before_summary(self):
        path = self.root/'results/mirp/cases.jsonl'
        path.write_text(path.read_text().replace('3.1', '3.2', 1))
        with self.assertRaisesRegex(ValueError, 'records hash mismatch'):
            self.summary()

    def test_plan_and_frozen_implementation_tampering_are_rejected(self):
        plan = self.root/'protocol/native_study_plan.json'
        original = plan.read_bytes()
        plan.write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError, 'Frozen file hash mismatch'):
            self.summary()
        plan.write_bytes(original)
        module = self.root/'radaccord/operators.py'
        module.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Frozen file hash mismatch'):
            self.summary()

    def test_omitted_and_duplicate_attempts_cannot_balance_themselves(self):
        original = deepcopy(self.records['mirp'])
        self.records['mirp'] = original[:-1]
        self.save_engine('mirp')
        with self.assertRaisesRegex(ValueError, 'full ordered plan'):
            self.summary()
        self.records['mirp'] = original+[deepcopy(original[0])]
        self.save_engine('mirp')
        with self.assertRaisesRegex(ValueError, 'Duplicate archived attempt'):
            self.summary()

    def test_failed_attempt_retained_separately_from_unavailable_observation(self):
        row = self.records['pyradiomics'][-1]
        self.records['pyradiomics'][-1] = {key: row[key] for key in ('engine', 'input_id', 'source_kind',
            'modality', 'operation', 'config', 'total_seconds')}
        self.records['pyradiomics'][-1].update(completed=False, exception_type='ValueError', reason_code='native_study_attempt_failed')
        self.save_engine('pyradiomics')
        result = self.summary()
        totals = {row['engine']: row for row in result['summary']['pair_counts'] if row['grouping'] == 'engine'}
        self.assertEqual(totals['pyradiomics']['not_completed'], 1)
        self.assertEqual(totals['pyradiomics']['unavailable'], 0)
        self.assertEqual(totals['pyradiomics']['attempted'], 3)
        self.assertEqual(result['summary']['units']['recorded_checkpoints'], 5)

    def test_false_preservation_claim_fails_even_with_updated_record_hash(self):
        row = self.records['mirp'][0]
        row['observed_values'] = dict(row['observed_values'], sha256='a'*64)
        self.save_engine('mirp')
        with self.assertRaisesRegex(ValueError, 'contradicts recorded numeric'):
            self.summary()

    def test_outputs_are_deterministic_and_refuse_overwrite(self):
        first, second = self.root/'out1', self.root/'out2'
        write_outputs(self.summary(), first)
        write_outputs(self.summary(), second)
        self.assertEqual(len(list(first.iterdir())), 8)
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()},
                         {p.name: p.read_bytes() for p in second.iterdir()})
        with self.assertRaises(FileExistsError):
            write_outputs(self.summary(), first)

    def test_hash_bound_interruption_accounts_for_every_unobserved_slot(self):
        self.records['pyradiomics'] = self.records['pyradiomics'][:1]
        self.save_engine('pyradiomics')
        directory = self.root/'results/pyradiomics'
        summary_path = directory/'run_summary.json'
        # This removal concerns only this test's temporary fabricated ledger.
        summary_path.unlink()
        interruption = dict(schema_version='native-interruption-1', engine='pyradiomics', engine_version='test',
                            numpy_version='test', freeze_sha256=digest(self.root/'protocol/native_freeze.json'),
                            plan_sha256=self.freeze['protocol/native_study_plan.json'], records_sha256=digest(directory/'cases.jsonl'),
                            planned=3, recorded_attempts=1, completed_records=1, unchanged_records=1,
                            candidate_attempt_count=2, not_reached_count=1,
                            unrecorded_next_pair=dict(input_id='s1', operation='cubic_1p3', planned_ordinal=2,
                                                      record_present=False, state='completion_unknown'),
                            not_reached=[dict(input_id='c1', operation='identity')])
        write_json(directory/'interruption.json', interruption)
        result = self.summary()
        totals = {row['engine']: row for row in result['summary']['pair_counts'] if row['grouping'] == 'engine'}
        self.assertEqual(totals['pyradiomics']['planned'], 3)
        self.assertEqual(totals['pyradiomics']['attempted'], 1)
        self.assertEqual(totals['pyradiomics']['candidate_attempts_including_interrupted_slot'], 2)
        self.assertEqual(totals['pyradiomics']['interrupted_unrecorded'], 1)
        self.assertEqual(totals['pyradiomics']['not_reached'], 1)
        self.assertEqual(result['summary']['units']['recorded_checkpoints'], 4)
        missing = [row for row in result['pairs'] if not row['record_present']]
        self.assertTrue(all(row['completed'] is None and row['total_seconds'] is None for row in missing))
        interruption['not_reached'][0]['input_id'] = 's1'
        write_json(directory/'interruption.json', interruption)
        with self.assertRaisesRegex(ValueError, 'remaining slots'):
            self.summary()


if __name__ == '__main__':
    unittest.main()
