"""Summarize retained sampling-study records without rerunning any operator.

Example: python scripts/summarize_sampling_study.py --input results/study --output reports/study
The output must not exist. JSON preserves contributing case IDs; CSV tables are
descriptive and do not assume that operations or released volumes are independent.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


STATUSES = ('satisfied', 'violated', 'indeterminate_boundary', 'not_available')
COMPARATORS = ('paired_QA', 'source_aware_geometry', 'legacy_full_grid', 'sampling')
MEASURES = ('roi_voxels', 'occupied_volume_mm3', 'mean', 'population_variance')
OP_TIMES = ('producer_seconds', 'witness_seconds', 'file_io_seconds', 'file_witness_seconds',
            'file_unavailable_elapsed_seconds')
VOL_TIMES = ('total_seconds', 'input_io_seconds', 'input_to_native_seconds')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(text):
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid)


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            require(bool(line.strip()), f'Blank record in {path.name}:{line_number}')
            yield decode(line)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def key(row):
    return row['dataset'], row['volume_id'], row['case']


def row_id(parts):
    # A JSON tuple avoids ambiguous separators in externally supplied IDs.
    return json.dumps(list(parts), ensure_ascii=True, separators=(',', ':'))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    observed = sorted(value for value in values if value is not None)
    require(all(finite(value) for value in observed), 'Invalid descriptive numeric value.')
    def quantile(p):
        index = (len(observed) - 1) * p
        lower = math.floor(index)
        upper = math.ceil(index)
        return observed[lower] + (observed[upper] - observed[lower]) * (index - lower)
    result = {'n': len(observed), 'missing': len(values) - len(observed)}
    result.update({name: None for name in ('min', 'q25', 'median', 'q75', 'max', 'mean')})
    if observed:
        result.update(min=observed[0], q25=quantile(.25), median=quantile(.5),
                      q75=quantile(.75), max=observed[-1], mean=statistics.fmean(observed))
    return result


def validated_inputs(directory, allow_legacy_complete=False):
    summary = decode((directory / 'run_summary.json').read_text(encoding='utf-8'))
    require(summary['schema_version'] == 'sampling-study-1.0', 'Unsupported study schema.')
    cases = list(read_jsonl(directory / 'cases.jsonl'))
    volumes = list(read_jsonl(directory / 'volumes.jsonl'))
    require(len({key(row) for row in cases}) == len(cases), 'Duplicate case row ID.')
    require(len({(row['dataset'], row['volume_id']) for row in volumes}) == len(volumes),
            'Duplicate volume row ID.')
    datasets = {item['name']: item for item in summary['datasets']}
    require(len(datasets) == len(summary['datasets']), 'Duplicate dataset name.')
    expected_volumes = set()
    for dataset, item in datasets.items():
        ids = item['attempted_ids']
        require(len(ids) == len(set(ids)), 'Duplicate planned volume ID.')
        expected_volumes.update((dataset, identifier) for identifier in ids)
    require({(row['dataset'], row['volume_id']) for row in volumes} == expected_volumes,
            'Volume records do not match the attempted-ID roster.')
    kinds = {**dict.fromkeys(summary['controls'], 'valid_control'),
             **dict.fromkeys(summary['own_wrapper_mutations'], 'own_wrapper_mutation'),
             **dict.fromkeys(summary.get('support_policy_controls', []), 'support_policy_control')}
    legacy = 'planned_case_order' not in summary
    if legacy:
        require(allow_legacy_complete, 'Pre-ledger study needs explicit --allow-legacy-complete.')
        # Only the complete archived development schema has this one support case.
        kinds['roi_truncation'] = 'support_policy_control'
        order = list(kinds)
    else:
        order = summary['planned_case_order']
        require(len(order) == len(set(order)) and set(order) == set(kinds), 'Invalid planned case roster.')
    case_map = {key(row): row for row in cases}
    expected_cases = {(dataset, identifier, name) for dataset, identifier in expected_volumes for name in order}
    require(set(case_map) <= expected_cases, 'Unplanned case record.')
    ledger = []
    for volume in volumes:
        dataset, identifier = volume['dataset'], volume['volume_id']
        if legacy:
            require(volume['status'] == 'evaluated', 'Legacy compatibility requires complete volumes.')
            require(all((dataset, identifier, name) in case_map for name in order),
                    'Legacy compatibility cannot infer unavailable or unexecuted cases.')
            items = [{'case': name, 'kind': kinds[name], 'execution_status': 'completed',
                      'sampling_status': case_map[dataset, identifier, name]['sampling']['status']} for name in order]
        else:
            items = volume['case_ledger']
            require(len(items) == len(order) and {item['case'] for item in items} == set(order),
                    'Incomplete or duplicate per-volume case ledger.')
        for item in items:
            require(item['kind'] == kinds[item['case']], 'Ledger kind disagrees with planned case kind.')
            identity = dataset, identifier, item['case']
            execution = item['execution_status']
            require(execution in ('completed', 'unavailable', 'not_reached'), 'Unknown execution status.')
            require((identity in case_map) == (execution == 'completed'), 'Case row and execution ledger disagree.')
            result = case_map.get(identity)
            if result is not None:
                require(result['kind'] == item['kind'], 'Record kind differs from ledger.')
                require(result['sampling']['status'] in STATUSES, 'Unknown sampling status.')
                require(result['sampling']['status'] == item['sampling_status'], 'Ledger sampling status differs.')
                for comparator in COMPARATORS:
                    require(result[comparator]['status'] in (*STATUSES, 'not_applicable'),
                            'Unknown comparator status.')
                selected = identifier in datasets[dataset]['file_roundtrip_ids']
                file_status = result['file_roundtrip']['status']
                require(file_status in (*STATUSES, 'not_selected'), 'Unknown file-roundtrip status.')
                require((file_status != 'not_selected') == selected, 'File-roundtrip selection differs from fixed roster.')
                require((result['mutation'] is not None) == (item['kind'] == 'own_wrapper_mutation'),
                        'Mutation data absent or attached to a control.')
                if result['mutation'] is not None:
                    require(isinstance(result['mutation']['active'], bool), 'Mutation activity must be boolean.')
                stats = result['voxel_statistics']
                for baseline, diff in (('source', 'candidate_minus_source'),
                                       ('correct_operation', 'candidate_minus_correct_operation')):
                    a, b, differences = stats['candidate'], stats[baseline], stats[diff]
                    if a is None or b is None:
                        require(differences is None, 'Drift recorded for unavailable ROI statistics.')
                    else:
                        require(all(finite(a[m]) and finite(b[m]) and finite(differences[m])
                                    and differences[m] == a[m] - b[m] for m in MEASURES),
                                'Recorded direct-statistic difference is inconsistent.')
            ledger.append({'dataset': dataset, 'volume_id': identifier, **item, 'row_id': row_id(identity)})
    if not legacy:
        for dataset, item in datasets.items():
            require(item['planned_case_counts'] == dict.fromkeys(order, len(item['attempted_ids'])),
                    'Planned per-case denominators do not match volume roster.')
            expected_kind_counts = {kind: list(kinds.values()).count(kind) * len(item['attempted_ids'])
                                    for kind in set(kinds.values())}
            require(item['planned_kind_counts'] == expected_kind_counts, 'Planned kind denominators disagree.')
    expected_counts = Counter(attempted_volumes=len(volumes), cases=len(cases))
    for volume in volumes:
        require(volume['status'] in ('evaluated', 'not_available'), 'Unknown volume execution status.')
        expected_counts['evaluated_volumes' if volume['status'] == 'evaluated' else 'unavailable_volumes'] += 1
    for row in cases:
        expected_counts[row['kind'] + ':' + row['sampling']['status']] += 1
        expected_counts['roundtrip:' + row['file_roundtrip']['status']] += 1
        if row['mutation'] is not None:
            expected_counts['mutation_active' if row['mutation']['active'] else 'mutation_inactive'] += 1
    if not legacy:
        for entry in ledger:
            expected_counts['case_execution:' + entry['execution_status']] += 1
    known_counts = {'attempted_volumes', 'evaluated_volumes', 'unavailable_volumes', 'cases',
                    'mutation_active', 'mutation_inactive'}
    known_counts.update(kind + ':' + state for kind in set(kinds.values()) for state in STATUSES)
    known_counts.update('roundtrip:' + state for state in (*STATUSES, 'not_selected'))
    if not legacy:
        known_counts.update('case_execution:' + state for state in ('completed', 'unavailable', 'not_reached'))
    for name in known_counts:
        require(summary['counts'].get(name, 0) == expected_counts[name],
                'Archived summary count differs from raw records: ' + name)
    return summary, cases, volumes, ledger, legacy


def grouped(rows):
    result = defaultdict(list)
    for row in rows:
        result[row['dataset'], row['case'], row['kind']].append(row)
    return sorted(result.items())


def summarize(directory, allow_legacy_complete=False):
    source_summary, cases, volumes, ledger, legacy = validated_inputs(directory, allow_legacy_complete)
    case_map = {key(row): row for row in cases}
    tables = {name: [] for name in ('case_counts', 'comparators', 'support_reuse', 'roundtrip',
                                   'operation_runtime', 'volume_runtime', 'direct_drift', 'case_rows',
                                   'volume_rows', 'checkpoint_rows')}
    warnings = []
    if legacy:
        warnings.append({'type': 'explicit_complete_legacy_ledger', 'count': len(ledger),
                         'detail': 'Ledger reconstructed only because all planned development cases were retained and all volumes completed.'})
    disagreement_ids = defaultdict(list)
    for group, entries in grouped(ledger):
        base = dict(zip(('dataset', 'case', 'kind'), group))
        count = Counter()
        ids_by_state = defaultdict(list)
        for entry in entries:
            count['planned'] += 1
            execution = entry['execution_status']
            state = entry.get('sampling_status') if execution == 'completed' else execution
            count['executed' if execution == 'completed' else 'execution_' + execution] += 1
            count[state] += 1
            ids_by_state[state].append(entry['row_id'])
        observed = [case_map[key(entry)] for entry in entries if entry['execution_status'] == 'completed']
        tables['case_counts'].append({**base, 'planned': count['planned'], 'executed': count['executed'],
            'satisfied': count['satisfied'], 'violated': count['violated'],
            'indeterminate': count['indeterminate_boundary'],
            'unavailable': count['unavailable'] + count['not_available'],
            'execution_unavailable': count['execution_unavailable'], 'sampling_unavailable': count['not_available'],
            'not_reached': count['not_reached'],
            'mutations_active': sum(row['mutation'] is not None and row['mutation']['active'] for row in observed),
            'mutations_inactive': sum(row['mutation'] is not None and not row['mutation']['active'] for row in observed),
            'mutation_activity_unavailable': len(entries) - len(observed) if base['kind'] == 'own_wrapper_mutation' else 0,
            'row_ids_by_status': dict(ids_by_state)})
        strata = ('all_executed', 'active', 'inactive') if base['kind'] == 'own_wrapper_mutation' else ('all_executed',)
        for stratum in strata:
            subset = [row for row in observed if stratum == 'all_executed'
                      or row['mutation']['active'] == (stratum == 'active')]
            for comparator in COMPARATORS:
                counts = Counter(row[comparator]['status'] for row in subset)
                tables['comparators'].append({**base, 'mutation_stratum': stratum, 'comparator': comparator,
                    'n': len(subset), **{state: counts[state] for state in (*STATUSES, 'not_applicable')},
                    'row_ids': [row_id(key(row)) for row in subset]})
        for component, lookup in (
                ('coverage', lambda row: (row['sampling'].get('coverage') or {}).get('status', 'not_available')),
                ('sampling_reuse', lambda row: row['sampling'].get('feature_reuse', {}).get('decision', 'not_available'))):
            values = defaultdict(list)
            for row in observed:
                values[lookup(row)].append(row_id(key(row)))
            for state, ids in sorted(values.items()):
                tables['support_reuse'].append({**base, 'component': component, 'status': state,
                                               'n': len(ids), 'executed': len(observed), 'row_ids': ids})
        roundtrip_groups = defaultdict(list)
        for row in observed:
            primary = row['sampling']
            file = row['file_roundtrip']
            file_witness = file.get('sampling', {})
            available = file['status'] in STATUSES[:3] and primary['status'] in STATUSES[:3]
            comparison = {'sampling_status_agreement': primary['status'] == file['status'] if available else None,
                'coverage_status_agreement': ((primary.get('coverage') or {}).get('status') ==
                    (file_witness.get('coverage') or {}).get('status')) if available else None,
                'reuse_decision_agreement': (primary.get('feature_reuse', {}).get('decision') ==
                    file_witness.get('feature_reuse', {}).get('decision')) if available else None,
                'component_checks_agreement': primary.get('checks') == file_witness.get('checks') if available else None}
            if file['status'] == 'not_available':
                disagreement_ids['file_boundary_unavailable'].append(row_id(key(row)))
            for component, agreement in comparison.items():
                if agreement is False:
                    disagreement_ids[component].append(row_id(key(row)))
            group_key = (primary['status'], file['status'], *comparison.values())
            roundtrip_groups[group_key].append(row_id(key(row)))
            flat = {**base, 'volume_id': row['volume_id'], 'row_id': row_id(key(row)),
                'mutation_active': None if row['mutation'] is None else row['mutation']['active'],
                'sampling_status': primary['status'], 'paired_QA': row['paired_QA']['status'],
                'source_aware_geometry': row['source_aware_geometry']['status'],
                'legacy_full_grid': row['legacy_full_grid']['status'], 'file_status': file['status'], **comparison,
                'coverage_status': (primary.get('coverage') or {}).get('status'),
                'sampling_reuse_decision': primary.get('feature_reuse', {}).get('decision')}
            for name in ('max_corner_error_mm', 'max_intensity_error', 'nominal_mismatched_intensity_voxels',
                         'nominal_mismatched_roi_voxels', 'ambiguous_intensity_voxels', 'ambiguous_roi_voxels',
                         'violating_intensity_voxels', 'violating_roi_voxels'):
                flat[name] = primary.get(name)
            for name in ('candidate_roi_voxels', 'source_roi_voxels', 'source_roi_outside_candidate_fov',
                         'source_roi_definitely_outside_candidate_fov', 'source_roi_centres_near_fov_boundary',
                         'missing_roi_voxels', 'exact_roi_preserved'):
                flat[name] = (primary.get('coverage') or {}).get(name)
            for name in ('producer_seconds', 'witness_seconds'):
                flat[name] = row.get(name)
            flat['file_io_seconds'] = file.get('io_seconds')
            flat['file_witness_seconds'] = file.get('witness_seconds')
            flat['file_unavailable_elapsed_seconds'] = file.get('elapsed_seconds')
            for baseline in ('source', 'correct_operation'):
                drift = row['voxel_statistics']['candidate_minus_' + baseline]
                for measure in MEASURES:
                    flat['drift_vs_' + baseline + '_' + measure] = None if drift is None else drift[measure]
            tables['case_rows'].append(flat)
        for values, ids in sorted(roundtrip_groups.items(), key=lambda item: str(item[0])):
            tables['roundtrip'].append({**base, **dict(zip(('in_memory_status', 'file_status',
                'sampling_status_agreement', 'coverage_status_agreement', 'reuse_decision_agreement',
                'component_checks_agreement'), values)),
                'n': len(ids), 'row_ids': ids})
        rows = [row for row in tables['case_rows'] if (row['dataset'], row['case'], row['kind']) == group]
        for measure in OP_TIMES:
            values = [row[measure] for row in rows]
            require(all(value is None or value >= 0 for value in values), 'Negative runtime.')
            tables['operation_runtime'].append({**base, 'metric': measure, **distribution(values)})
        for baseline in ('source', 'correct_operation'):
            for measure in MEASURES:
                column = 'drift_vs_' + baseline + '_' + measure
                values = [row[column] for row in rows]
                tables['direct_drift'].append({**base, 'baseline': baseline, 'metric': measure,
                    **{'signed_' + k: v for k, v in distribution(values).items()},
                    **{'absolute_' + k: v for k, v in distribution([None if v is None else abs(v) for v in values]).items()},
                    'exact_nonzero': sum(v is not None and v != 0 for v in values),
                    'row_ids': [row['row_id'] for row in rows],
                    'interpretation': 'Descriptive direct ROI statistics; exact nonzero is not a clinical or material-change threshold. '
                        + ('Controls use their own observed output as correct_operation: their zero here is by construction.'
                           if base['kind'] != 'own_wrapper_mutation' and baseline == 'correct_operation' else '')})
    for volume in volumes:
        tables['volume_rows'].append({name: volume.get(name) for name in
            ('dataset', 'volume_id', 'status', 'source_shape', 'file_roundtrip_selected',
             'failed_case', 'operation_phase', *VOL_TIMES)})
    for dataset in sorted({row['dataset'] for row in volumes}):
        for metric in VOL_TIMES:
            rows = [row for row in volumes if row['dataset'] == dataset]
            values = [row.get(metric) for row in rows]
            require(all(value is None or value >= 0 for value in values), 'Negative volume runtime.')
            tables['volume_runtime'].append({'dataset': dataset, 'metric': metric, **distribution(values),
                'volume_ids': [row['volume_id'] for row in rows],
                'includes_partial_and_unavailable_attempts': True})
    checkpoint_path = directory / 'checkpoint_demo.jsonl'
    if checkpoint_path.exists():
        checkpoint_rows = list(read_jsonl(checkpoint_path))
        require(len({key(row) for row in checkpoint_rows}) == len(checkpoint_rows), 'Duplicate checkpoint-demo row.')
        for row in checkpoint_rows:
            tables['checkpoint_rows'].append({'dataset': row['dataset'], 'volume_id': row['volume_id'],
                'case': row['case'], 'row_id': row_id(key(row)), 'kind': row['kind'],
                'endpoint_only_status': row['endpoint_only_status'], 'first_observed_failure': row['first_observed_failure'],
                'stage_statuses': {stage['stage']: stage['sampling']['status'] for stage in row['stages']},
                'scope': row['scope']})
    for component, ids in sorted(disagreement_ids.items()):
        warnings.append({'type': 'in_memory_vs_file_' + component, 'count': len(ids), 'row_ids': ids,
                         'detail': 'The primary materialized-output result is retained; the NIfTI boundary differs and is not substituted.'})
    totals = {name: sum(row[name] for row in tables['case_counts']) for name in
              ('planned', 'executed', 'satisfied', 'violated', 'indeterminate', 'unavailable',
               'execution_unavailable', 'sampling_unavailable', 'not_reached')}
    require(totals['planned'] == sum(totals[name] for name in
            ('satisfied', 'violated', 'indeterminate', 'unavailable', 'not_reached')), 'Non-partitioning totals.')
    inputs = ('run_summary.json', 'cases.jsonl', 'volumes.jsonl', 'checkpoint_demo.jsonl')
    return {'schema_version': 'sampling-summary-1.0', 'input_sha256': {
        name: sha256(directory / name) for name in inputs if (directory / name).exists()},
        'summarizer_sha256': sha256(Path(__file__)), 'source_run_metadata': source_summary,
        'totals': totals, 'warnings': warnings, 'tables': tables, 'execution_ledger': ledger,
        'scope': {'primary_boundary': 'Materialized SimpleITK image/mask outputs; file roundtrip is separate.',
            'denominators': 'Executed means a retained completed case record, including sampling unavailable. '
                'Unavailable = execution unavailable + sampling unavailable. Unreached cases remain in planned totals.',
            'comparators': 'Statuses of each recorded comparator, stratified by prespecified mutation activity. '
                'Not applicable is never a detected fault. No classifier sensitivity or clinical accuracy is inferred.',
            'reuse': 'Recorded sampling-layer decision, not universal radiomic feature equality or clinical approval.',
            'runtime': 'Recorded elapsed times, with nonexecuted/unavailable measurements missing; volume attempts include failures.',
            'drift': 'Signed candidate-minus-source and candidate-minus-correct-operation differences already recorded. '
                'They concern voxel counts, occupied volume, ROI mean and population variance, not extracted native radiomic features.',
            'statistics': 'Descriptive distributions only, linear interpolation of empirical quantiles. '
                'No confidence intervals or independence assumption across volumes or operations.'}}


def write_outputs(report, output):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'summary.json').write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n',
                                       encoding='utf-8', newline='\n')
    tables = {**report['tables'], 'execution_ledger': report['execution_ledger']}
    for name, rows in tables.items():
        columns = list(dict.fromkeys(column for row in rows for column in row))
        with (output / (name + '.csv')).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
                                 if isinstance(value, (dict, list)) else value for key, value in row.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-legacy-complete', action='store_true',
                        help='Only for complete development archives predating the explicit execution ledger.')
    args = parser.parse_args()
    require(not args.output.exists(), 'Output directory already exists; records and previous summaries are never overwritten.')
    report = summarize(args.input, args.allow_legacy_complete)
    write_outputs(report, args.output)
    print(json.dumps({'totals': report['totals'], 'warnings': report['warnings']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
