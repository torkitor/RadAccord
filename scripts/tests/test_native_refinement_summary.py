"""Integrity tests for the six-source rc2 analysis compatibility correction."""
import json
import unittest

from scripts.tests import test_native_summary as fixtures
from scripts.summarize_native_refinement import canonical_digest, digest, summarize


class NativeRefinementSummaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeSummaryTests('test_balanced_plan_pair_and_checkpoint_denominators')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        module = self.root/'radaccord/numerics.py'
        module.write_text('# Fabricated numerical-source integrity fixture\n', encoding='utf-8')
        self.fixture.freeze['radaccord/numerics.py'] = digest(module)
        self.freeze_path = self.root/'protocol/native_refinement_freeze.json'
        fixtures.write_json(self.freeze_path, {'schema_version': 'native-freeze-1', 'phase': 'native-refinement-2',
                                               'candidate': '1.2.0rc2', 'files': self.fixture.freeze})
        for engine, rows in self.fixture.records.items():
            for row in rows:
                checker = row['report']['checker']
                checker['source_sha256']['numerics'] = self.fixture.freeze['radaccord/numerics.py']
                checker['implementation_sha256'] = canonical_digest(checker['source_sha256'])
            self.fixture.save_engine(engine)

    def summary(self):
        return summarize(self.root, [self.root/'results/mirp', self.root/'results/pyradiomics'])

    def test_six_source_profiles_preserve_full_plan_balance(self):
        result = self.summary()
        self.assertEqual(result['summary']['units']['retained_pair_records'], 6)
        self.assertEqual(result['summary']['units']['recorded_checkpoints'], 6)
        for row in result['summary']['pair_counts']:
            if row['grouping'] == 'engine':
                self.assertEqual((row['planned'], row['completed'], row['exact_native_values']), (3, 3, 3))

    def test_changed_or_omitted_numerics_hash_is_rejected_even_after_rebinding_records(self):
        checker = self.fixture.records['mirp'][0]['report']['checker']
        checker['source_sha256']['numerics'] = 'f'*64
        checker['implementation_sha256'] = canonical_digest(checker['source_sha256'])
        self.fixture.save_engine('mirp')
        with self.assertRaisesRegex(ValueError, 'checking implementation differs'):
            self.summary()
        checker['source_sha256'].pop('numerics')
        checker['implementation_sha256'] = canonical_digest(checker['source_sha256'])
        self.fixture.save_engine('mirp')
        with self.assertRaisesRegex(ValueError, 'checking implementation differs'):
            self.summary()

    def test_record_tampering_and_wrong_phase_are_rejected(self):
        record_path = self.root/'results/mirp/cases.jsonl'
        original = record_path.read_bytes()
        record_path.write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError, 'records hash mismatch'):
            self.summary()
        record_path.write_bytes(original)
        freeze = json.loads(self.freeze_path.read_text())
        freeze['phase'] = 'calibration'
        fixtures.write_json(self.freeze_path, freeze)
        with self.assertRaisesRegex(ValueError, 'rc2 only'):
            self.summary()


if __name__ == '__main__':
    unittest.main()
