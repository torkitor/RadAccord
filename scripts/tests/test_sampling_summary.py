"""Summary regressions using retained synthetic records and temporary derivatives."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import summarize_sampling_study as subject

ARCHIVE = ROOT / 'results' / 'sampling_reserved'


def fixture():
    metadata = json.loads((ARCHIVE / 'run_summary.json').read_text())
    identifier = metadata['datasets'][0]['attempted_ids'][0]
    rows = [json.loads(line) for line in (ARCHIVE / 'cases.jsonl').read_text().splitlines()
            if json.loads(line)['volume_id'] == identifier]
    volume = next(json.loads(line) for line in (ARCHIVE / 'volumes.jsonl').read_text().splitlines()
                  if json.loads(line)['volume_id'] == identifier)
    order = [row['case'] for row in rows]
    metadata['planned_case_order'] = order
    metadata['support_policy_controls'] = ['roi_truncation']
    metadata['datasets'][0].update(attempted_ids=[identifier], file_roundtrip_ids=[identifier],
        planned_case_counts=dict.fromkeys(order, 1),
        planned_kind_counts=dict(Counter(row['kind'] for row in rows)))
    volume['case_ledger'] = [{'case': row['case'], 'kind': row['kind'], 'execution_status': 'completed',
                            'sampling_status': row['sampling']['status']} for row in rows]
    return metadata, rows, volume


def write(directory, metadata, rows, volume):
    metadata = deepcopy(metadata)
    counts = Counter(attempted_volumes=1, cases=len(rows))
    counts['evaluated_volumes' if volume['status'] == 'evaluated' else 'unavailable_volumes'] += 1
    for row in rows:
        counts[row['kind'] + ':' + row['sampling']['status']] += 1
        counts['roundtrip:' + row['file_roundtrip']['status']] += 1
        if row['mutation'] is not None:
            counts['mutation_active' if row['mutation']['active'] else 'mutation_inactive'] += 1
    for item in volume['case_ledger']:
        counts['case_execution:' + item['execution_status']] += 1
    metadata['counts'] = dict(counts)
    (directory / 'run_summary.json').write_text(json.dumps(metadata), encoding='utf-8')
    (directory / 'cases.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    (directory / 'volumes.jsonl').write_text(json.dumps(volume) + '\n', encoding='utf-8')


class SummaryTests(unittest.TestCase):
    def test_complete_reserved_denominators_and_raw_status_agreement(self):
        before = {path.name: subject.sha256(path) for path in ARCHIVE.iterdir() if path.is_file()}
        result = subject.summarize(ARCHIVE)
        self.assertEqual(result['totals'], {'planned': 448, 'executed': 448, 'satisfied': 258,
            'violated': 190, 'indeterminate': 0, 'unavailable': 0, 'execution_unavailable': 0,
            'sampling_unavailable': 0, 'not_reached': 0})
        rows = result['tables']['case_counts']
        self.assertEqual(sum(row['satisfied'] for row in rows if row['kind'] == 'valid_control'), 224)
        self.assertEqual(sum(row['mutations_active'] for row in rows), 190)
        self.assertTrue(all(row['sampling_status_agreement'] for row in result['tables']['roundtrip']))
        self.assertEqual(sum(row['n'] for row in result['tables']['roundtrip']), 448)
        self.assertEqual(before, {path.name: subject.sha256(path) for path in ARCHIVE.iterdir() if path.is_file()})

    def test_legacy_needs_explicit_permission(self):
        metadata, rows, volume = fixture()
        metadata.pop('planned_case_order')
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows, volume)
            with self.assertRaisesRegex(ValueError, 'allow-legacy-complete'):
                subject.summarize(path)
            self.assertEqual(subject.summarize(path, True)['totals']['planned'], 14)

    def test_missing_record_cannot_be_silently_excluded(self):
        metadata, rows, volume = fixture()
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows[:-1], volume)
            with self.assertRaisesRegex(ValueError, 'execution ledger disagree'):
                subject.summarize(path)

    def test_duplicate_record_rejected(self):
        metadata, rows, volume = fixture()
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows + rows[:1], volume)
            with self.assertRaisesRegex(ValueError, 'Duplicate case'):
                subject.summarize(path)

    def test_partial_ledger_partitions_all_planned_cases(self):
        metadata, rows, volume = fixture()
        volume['status'] = 'not_available'
        for index, item in enumerate(volume['case_ledger']):
            if index >= 5:
                item['execution_status'] = 'unavailable' if index == 5 else 'not_reached'
                item.pop('sampling_status')
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows[:5], volume)
            result = subject.summarize(path)
            self.assertEqual(result['totals']['planned'], 14)
            self.assertEqual(result['totals']['executed'], 5)
            self.assertEqual(result['totals']['execution_unavailable'], 1)
            self.assertEqual(result['totals']['not_reached'], 8)
            self.assertEqual(len(result['execution_ledger']), 14)

    def test_sampling_unavailable_not_conflated_with_execution_unavailable(self):
        metadata, rows, volume = fixture()
        rows[0]['sampling'] = {'status': 'not_available'}
        volume['case_ledger'][0]['sampling_status'] = 'not_available'
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows, volume)
            result = subject.summarize(path)
            self.assertEqual(result['totals']['executed'], 14)
            self.assertEqual(result['totals']['sampling_unavailable'], 1)
            self.assertEqual(result['totals']['execution_unavailable'], 0)

    def test_indeterminate_is_not_satisfied(self):
        metadata, rows, volume = fixture()
        rows[0]['sampling']['status'] = 'indeterminate_boundary'
        volume['case_ledger'][0]['sampling_status'] = 'indeterminate_boundary'
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows, volume)
            result = subject.summarize(path)
            self.assertEqual(result['totals']['indeterminate'], 1)
            self.assertEqual(result['totals']['satisfied'], 7)

    def test_boundary_disagreement_is_visible_and_primary_unchanged(self):
        metadata, rows, volume = fixture()
        rows[0]['file_roundtrip']['candidate_paired']['same_affine'] = False
        rows[0]['file_roundtrip']['status'] = 'violated'
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows, volume)
            result = subject.summarize(path)
            self.assertEqual(result['totals']['satisfied'], 8)
            warning = next(row for row in result['warnings'] if row['type'].endswith('sampling_status_agreement'))
            self.assertEqual(warning['count'], 1)
            self.assertEqual(warning['row_ids'], [subject.row_id(subject.key(rows[0]))])

    def test_direct_statistic_numeric_tampering_rejected(self):
        metadata, rows, volume = fixture()
        rows[0]['voxel_statistics']['candidate_minus_source']['mean'] += .1
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows, volume)
            with self.assertRaisesRegex(ValueError, 'difference is inconsistent'):
                subject.summarize(path)

    def test_archived_summary_numeric_tampering_rejected(self):
        metadata, rows, volume = fixture()
        with TemporaryDirectory() as folder:
            path = Path(folder)
            write(path, metadata, rows, volume)
            item = json.loads((path / 'run_summary.json').read_text())
            item['counts']['valid_control:satisfied'] += 1
            (path / 'run_summary.json').write_text(json.dumps(item))
            with self.assertRaisesRegex(ValueError, 'summary count differs'):
                subject.summarize(path)


if __name__ == '__main__':
    unittest.main()
