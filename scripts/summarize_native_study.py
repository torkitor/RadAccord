"""Validate and summarize archived native pairs without executing extractors.

Uses only the standard library. Every planned slot must have an archived record
or an explicit, hash-bound interruption ledger. Pair, checkpoint and timing denominators stay separate.
All output depends solely on archived bytes; no current timestamp is emitted.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics


STATES = ('satisfied', 'violated', 'indeterminate', 'unavailable')
PAIR_STATES = STATES+('not_completed', 'interrupted_unrecorded', 'not_reached')
ENGINE_NAMES = ('mirp', 'pyradiomics')
SHA = re.compile(r'^[0-9a-f]{64}$')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8')).hexdigest()


def _json(text):
    def reject_constant(value):
        raise ValueError('Nonfinite JSON constant: '+value)
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON object key: '+key)
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_keys)


def _read(path):
    return _json(Path(path).read_text(encoding='utf-8'))


def _safe_file(root, relative):
    path = PurePosixPath(relative)
    if not isinstance(relative, str) or '\\' in relative or ':' in relative or path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe frozen relative path')
    result = root.joinpath(*path.parts).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Frozen file escapes the repository')
    return result


def _number(value, name, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(name+' must be finite and nonnegative')
    if integer and not isinstance(value, int):
        raise ValueError(name+' must be an integer')
    return value


def _feature_record(record):
    if not isinstance(record, dict) or not SHA.fullmatch(record.get('sha256', '')):
        raise ValueError('Invalid feature digest record')
    count = _number(record.get('count'), 'feature count', integer=True)
    finite = _number(record.get('nonfinite_count'), 'nonfinite count', integer=True)
    if finite > count:
        raise ValueError('Nonfinite count exceeds recorded values')


def _overall(checkpoints):
    states = [item['status'] for item in checkpoints]
    for status in ('violated', 'unavailable', 'indeterminate'):
        if status in states:
            return status
    return 'satisfied' if states and all(item == 'satisfied' for item in states) else 'unavailable'


def _reasons(checkpoint):
    reasons = []
    for field in ('reason_code', 'reason'):
        if checkpoint.get(field):
            reasons.append(str(checkpoint[field]))
    for field, value in checkpoint.get('checks', {}).items():
        if value is False:
            reasons.append(field+':violated')
        elif value is None:
            reasons.append(field+':indeterminate')
    for field in ('bounding_box_status',):
        if checkpoint.get(field) in ('violated', 'indeterminate', 'unavailable'):
            reasons.append(field+':'+checkpoint[field])
    for field in ('changed_declared_setting_keys', 'missing_declared_setting_keys'):
        if checkpoint.get(field):
            reasons.append(field+':'+','.join(checkpoint[field]))
    for field, value in checkpoint.get('exported_feature_roi_agreement', {}).items():
        if value is False:
            reasons.append(field+':violated')
    return sorted(set(reasons))


def _percentile(values, probability):
    if not values:
        return None
    location = (len(values)-1)*probability
    left = math.floor(location)
    right = math.ceil(location)
    return values[left]+(location-left)*(values[right]-values[left])


def _distribution(values, total):
    ordered = sorted(values)
    return dict(available_n=len(ordered), missing_n=total-len(ordered),
                min=ordered[0] if ordered else None, q25=_percentile(ordered, .25),
                median=_percentile(ordered, .5), q75=_percentile(ordered, .75),
                max=ordered[-1] if ordered else None,
                mean=statistics.fmean(ordered) if ordered else None)


def _groups(rows):
    groups = defaultdict(list)
    for row in rows:
        key = (row['engine'], row['source_kind'], row['modality'], row['operation'])
        groups[('engine_kind_modality_operation', *key)].append(row)
        groups[('engine', row['engine'], 'all', 'all', 'all')].append(row)
    return groups


def summarize(root, run_directories, *, plan_path=None, freeze_path=None):
    root = Path(root).resolve()
    plan_path = Path(plan_path) if plan_path else root/'protocol/native_study_plan.json'
    freeze_path = Path(freeze_path) if freeze_path else root/'protocol/native_freeze.json'
    freeze = _read(freeze_path)
    if freeze.get('schema_version') != 'native-freeze-1' or not isinstance(freeze.get('files'), dict):
        raise ValueError('Unsupported native freeze')
    for relative, expected in freeze['files'].items():
        if not isinstance(expected, str) or not SHA.fullmatch(expected) or digest(_safe_file(root, relative)) != expected:
            raise ValueError('Frozen file hash mismatch: '+relative)
    plan_hash = digest(plan_path)
    if plan_hash != freeze['files'].get('protocol/native_study_plan.json'):
        raise ValueError('Selected plan does not match native freeze')
    plan = _read(plan_path)
    if plan.get('schema_version') != 'native-plan-1' or not isinstance(plan.get('inputs'), list):
        raise ValueError('Unsupported native plan')
    expected_pairs = []
    input_map = {}
    for item in plan['inputs']:
        identity = item['id']
        if not isinstance(identity, str) or identity in input_map or not identity:
            raise ValueError('Duplicate or invalid planned input identifier')
        operations = item['operations']
        if not isinstance(operations, list) or not operations or len(set(operations)) != len(operations):
            raise ValueError('Invalid or duplicate planned operations')
        input_map[identity] = item
        expected_pairs.extend((identity, operation) for operation in operations)
    pairs, checkpoints, runs = [], [], []
    engines = set()
    for directory in sorted(map(Path, run_directories), key=lambda p: p.name):
        interruption = None
        if (directory/'run_summary.json').exists():
            if (directory/'interruption.json').exists():
                raise ValueError('A run cannot have both a final summary and an interruption ledger')
            run = _read(directory/'run_summary.json')
        else:
            interruption = _read(directory/'interruption.json')
            if interruption.get('schema_version') != 'native-interruption-1':
                raise ValueError('Unsupported interruption ledger')
            if interruption.get('freeze_sha256') != digest(freeze_path):
                raise ValueError('Interruption freeze hash mismatch')
            run = dict(interruption, schema_version='native-study-1', development=False,
                       attempted=interruption['recorded_attempts'],
                       completed=interruption['completed_records'], unchanged=interruption['unchanged_records'])
        engine = run.get('engine')
        if run.get('schema_version') != 'native-study-1' or engine not in ENGINE_NAMES or engine in engines:
            raise ValueError('Invalid or duplicate engine run')
        engines.add(engine)
        if run.get('development') is not False:
            raise ValueError('A descriptive frozen-study summary cannot relabel development results')
        records_path = directory/'cases.jsonl'
        if run.get('plan_sha256') != plan_hash:
            raise ValueError('Run-summary plan hash mismatch')
        if 'freeze_sha256' in run and run['freeze_sha256'] != digest(freeze_path):
            raise ValueError('Run-summary freeze hash mismatch')
        records_hash = digest(records_path)
        if run.get('records_sha256') != records_hash:
            raise ValueError('Run-summary records hash mismatch')
        lines = records_path.read_text(encoding='utf-8').splitlines()
        if any(not line.strip() for line in lines):
            raise ValueError('Blank archived record line')
        records = [_json(line) for line in lines]
        identities = [(row.get('input_id'), row.get('operation')) for row in records]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate archived attempt identifier')
        if interruption is None:
            if identities != expected_pairs:
                raise ValueError('Archived attempts do not exactly match the full ordered plan')
        else:
            if not 0 <= len(records) < len(expected_pairs) or identities != expected_pairs[:len(records)]:
                raise ValueError('Interrupted records are not a strict ordered prefix of the plan')
            next_pair = interruption.get('unrecorded_next_pair', {})
            if ((next_pair.get('input_id'), next_pair.get('operation')) != expected_pairs[len(records)]
                    or next_pair.get('record_present') is not False
                    or next_pair.get('planned_ordinal') != len(records)+1
                    or next_pair.get('state') != 'completion_unknown'):
                raise ValueError('Interruption next scheduled slot does not match the plan')
            remaining = interruption.get('not_reached', [])
            if ([(row.get('input_id'), row.get('operation')) for row in remaining] != expected_pairs[len(records)+1:]
                    or interruption.get('not_reached_count') != len(remaining)
                    or interruption.get('candidate_attempt_count') != len(records)+1):
                raise ValueError('Interruption remaining slots do not exactly match the plan')
        completed_count = unchanged_count = 0
        for record in records:
            item = input_map[record['input_id']]
            if record.get('engine') != engine or record.get('source_kind') != item['kind'] or record.get('modality') != item['modality']:
                raise ValueError('Record identity/domain disagrees with frozen plan')
            completed = record.get('completed')
            if not isinstance(completed, bool):
                raise ValueError('Completion must be explicitly boolean')
            _number(record.get('total_seconds'), 'total_seconds')
            pair_id = engine+'|'+record['input_id']+'|'+record['operation']
            pair = {key: record[key] for key in ('engine', 'input_id', 'source_kind', 'modality', 'operation', 'completed', 'total_seconds')}
            pair.update(pair_id=pair_id, status='not_completed', native_values_unchanged=None,
                        record_present=True,
                        numeric_digest_equal=None, baseline_seconds=None, audited_seconds=None,
                        baseline_value_count=None, observed_value_count=None,
                        baseline_nonfinite_count=None, observed_nonfinite_count=None,
                        checkpoint_count=0, relationship_acceptance=None,
                        reason=record.get('reason_code', ''),
                        raw_configuration_sha256=canonical_digest(record['config']))
            if not completed:
                if 'report' in record or 'native_values_unchanged' in record:
                    raise ValueError('An incomplete attempt contains a completed-pair result')
                pairs.append(pair)
                continue
            completed_count += 1
            unchanged = record.get('native_values_unchanged')
            if not isinstance(unchanged, bool):
                raise ValueError('Value preservation must be explicitly boolean')
            unchanged_count += unchanged
            baseline, observed = record['baseline_values'], record['observed_values']
            _feature_record(baseline)
            _feature_record(observed)
            digest_equal = baseline == observed
            if unchanged and not digest_equal:
                raise ValueError('Reported exact native-value preservation contradicts recorded numeric hashes/counts')
            report = record['report']
            if report.get('engine') != {'name': engine, 'version': run['engine_version']}:
                raise ValueError('Report engine/version disagrees with run summary')
            if report.get('declaration_timing') != 'before_native_execute':
                raise ValueError('Declaration timing differs from the frozen profile')
            checker = report['checker']
            expected_sources = {name: freeze['files'][relative] for name, relative in {
                'evidence': 'radaccord/evidence.py', 'operators': 'radaccord/operators.py',
                engine: 'radaccord/'+engine+'.py', 'physical_contracts': 'software/physical_contracts.py',
                'sampling_contracts': 'software/sampling_contracts.py'}.items()}
            if checker.get('source_sha256') != expected_sources or checker.get('implementation_sha256') != canonical_digest(expected_sources):
                raise ValueError('Observed checking implementation differs from frozen sources')
            if checker.get('numpy_version') != run.get('numpy_version'):
                raise ValueError('Run and report NumPy versions disagree')
            if engine == 'pyradiomics' and report.get('feature_values') != observed:
                raise ValueError('Observed feature digest differs between pair and adapter report')
            if engine == 'mirp' and report.get('configuration_sha256') != canonical_digest(record['config']):
                raise ValueError('MIRP source-configuration hash differs')
            local_checkpoints = report.get('checkpoints')
            if not isinstance(local_checkpoints, list):
                raise ValueError('Missing checkpoint ledger')
            for checkpoint in local_checkpoints:
                if checkpoint.get('status') not in STATES or not isinstance(checkpoint.get('checkpoint'), str):
                    raise ValueError('Unknown checkpoint state or missing name')
            if report.get('status') != _overall(local_checkpoints):
                raise ValueError('Pair status does not agree with recorded checkpoint states')
            for metric in ('baseline_seconds', 'audited_seconds'):
                _number(record.get(metric), metric)
            if record['audited_seconds'] != report.get('elapsed_seconds'):
                raise ValueError('Audited timing differs between pair and adapter report')
            pair.update(status=report['status'], native_values_unchanged=unchanged,
                        numeric_digest_equal=digest_equal, baseline_seconds=record['baseline_seconds'],
                        audited_seconds=record['audited_seconds'], baseline_value_count=baseline['count'],
                        observed_value_count=observed['count'], baseline_nonfinite_count=baseline['nonfinite_count'],
                        observed_nonfinite_count=observed['nonfinite_count'], checkpoint_count=len(local_checkpoints),
                        relationship_acceptance=report.get('relationship_acceptance'),
                        baseline_values_sha256=baseline['sha256'], observed_values_sha256=observed['sha256'],
                        resolved_configuration_sha256=report['configuration_sha256'])
            pairs.append(pair)
            for number, checkpoint in enumerate(local_checkpoints):
                coverage = checkpoint.get('coverage') or {}
                reuse = checkpoint.get('feature_reuse') or {}
                flat = {key: pair[key] for key in ('pair_id', 'engine', 'input_id', 'source_kind', 'modality', 'operation')}
                flat.update(checkpoint_index=number, checkpoint=checkpoint['checkpoint'], status=checkpoint['status'],
                            coverage_status=coverage.get('status', 'unobserved'),
                            feature_reuse_decision=reuse.get('decision', 'unobserved'),
                            reason='; '.join(_reasons(checkpoint)),
                            checkpoint_record_sha256=canonical_digest(checkpoint))
                for key in ('max_corner_error_mm', 'max_intensity_error', 'nominal_mismatched_intensity_voxels',
                            'nominal_mismatched_roi_voxels', 'ambiguous_intensity_voxels', 'ambiguous_roi_voxels',
                            'violating_intensity_voxels', 'violating_roi_voxels', 'candidate_roi_voxels'):
                    flat[key] = checkpoint.get(key)
                for key in ('position', 'intensity', 'roi'):
                    flat[key+'_check'] = checkpoint.get('checks', {}).get(key, 'unobserved')
                for key in ('source_roi_outside_candidate_fov', 'source_roi_definitely_outside_candidate_fov',
                            'source_roi_centres_near_fov_boundary'):
                    flat[key] = coverage.get(key)
                checkpoints.append(flat)
        for field, expected in [('planned', len(expected_pairs)), ('attempted', len(records)),
                                ('completed', completed_count), ('unchanged', unchanged_count)]:
            if run.get(field) != expected or isinstance(run.get(field), bool):
                raise ValueError('Run-summary count mismatch: '+field)
        if interruption is not None:
            for offset, (identity, operation) in enumerate(expected_pairs[len(records):]):
                item = input_map[identity]
                pairs.append(dict(pair_id=engine+'|'+identity+'|'+operation, engine=engine,
                                  input_id=identity, source_kind=item['kind'], modality=item['modality'], operation=operation,
                                  completed=None, record_present=False,
                                  status='interrupted_unrecorded' if offset == 0 else 'not_reached',
                                  native_values_unchanged=None, numeric_digest_equal=None,
                                  baseline_seconds=None, audited_seconds=None, total_seconds=None,
                                  baseline_value_count=None, observed_value_count=None,
                                  baseline_nonfinite_count=None, observed_nonfinite_count=None,
                                  checkpoint_count=0, relationship_acceptance=None,
                                  reason='Completion unknown; no persisted case record.' if offset == 0 else 'Not reached after the interrupted scheduled slot.'))
        runs.append({'engine': engine, 'engine_version': run['engine_version'],
                     'numpy_version': run['numpy_version'], 'planned_pairs': len(expected_pairs),
                     'recorded_attempts': len(records),
                     'candidate_attempts_including_interrupted_slot': len(records)+(interruption is not None),
                     'interrupted_without_record': int(interruption is not None),
                     'not_reached': len(expected_pairs)-len(records)-1 if interruption is not None else 0,
                     'completed_pairs': completed_count, 'exact_native_value_preservation': unchanged_count,
                     'records_sha256': records_hash,
                     'run_summary_sha256': None if interruption is not None else digest(directory/'run_summary.json'),
                     'interruption_sha256': digest(directory/'interruption.json') if interruption is not None else None})
    if not engines:
        raise ValueError('Supply at least one complete engine run')
    pair_counts, timings = [], []
    for key, members in sorted(_groups(pairs).items()):
        grouping, engine, kind, modality, operation = key
        group = dict(grouping=grouping, engine=engine, source_kind=kind, modality=modality, operation=operation)
        states = Counter(row['status'] for row in members)
        recorded = sum(row['record_present'] for row in members)
        pair_counts.append(dict(group, planned=len(members), attempted=recorded,
                                candidate_attempts_including_interrupted_slot=recorded+states['interrupted_unrecorded'],
                                completed=sum(row['completed'] is True for row in members),
                                exact_native_values=sum(row['native_values_unchanged'] is True for row in members),
                                numeric_digest_equal=sum(row['numeric_digest_equal'] is True for row in members),
                                **{state: states[state] for state in PAIR_STATES}))
        for metric in ('baseline_seconds', 'audited_seconds', 'total_seconds'):
            timings.append(dict(group, metric=metric, **_distribution(
                [row[metric] for row in members if row[metric] is not None], len(members))))
    checkpoint_counts = []
    for key, members in sorted(_groups(checkpoints).items()):
        names = sorted({row['checkpoint'] for row in members})
        for name in names:
            selected = [row for row in members if row['checkpoint'] == name]
            states = Counter(row['status'] for row in selected)
            checkpoint_counts.append(dict(zip(('grouping', 'engine', 'source_kind', 'modality', 'operation'), key),
                                     checkpoint=name, observed_checkpoints=len(selected),
                                     **{state: states[state] for state in STATES}))
    reuse_counts = []
    for engine in sorted(engines):
        selected = [row for row in checkpoints if row['engine'] == engine]
        for dimension in ('coverage_status', 'feature_reuse_decision'):
            counts = Counter(row[dimension] for row in selected)
            reuse_counts.extend(dict(engine=engine, unit='recorded_checkpoint', dimension=dimension,
                                      state=state, count=count) for state, count in sorted(counts.items()))
    summary = dict(schema_version='native-descriptive-summary-1',
                   analysis_role=freeze.get('analysis_role', 'First development evaluation; original frozen executions, alerts and interruptions retained.'),
                   provenance=dict(freeze_sha256=digest(freeze_path), frozen_files_verified=len(freeze['files']),
                                   plan_sha256=plan_hash, runs=runs,
                                   summarizer_sha256=digest(__file__)),
                   units=dict(planned_inputs=len(input_map), planned_pairs_per_engine=len(expected_pairs),
                              engines=len(engines), retained_pairs=len(pairs),
                              retained_pair_records=sum(row['record_present'] for row in pairs),
                              interrupted_without_record=sum(row['status'] == 'interrupted_unrecorded' for row in pairs),
                              not_reached=sum(row['status'] == 'not_reached' for row in pairs),
                              recorded_checkpoints=len(checkpoints)),
                   scope=dict(value_preservation='Exact producer comparison recorded per pair; matching numeric hashes are independently checked. Matching nonfinite positions do not certify finite or correct measurements.',
                              mirp_counts='MIRP numeric-column counts include numeric metadata and are not radiomic-feature counts.',
                              timing='Descriptive wall times; baseline always runs first. No counterbalancing, causal overhead estimate or clinical inference.',
                              source='Public clinical images were used previously; neither operation counts nor image IDs establish independent patients.',
                              configuration='Raw intent and resolved-configuration digests are kept separately. PyRadiomics resolved settings are bound by the frozen observer; their digest cannot be recomputed from the abbreviated raw config alone.'),
                   pair_counts=pair_counts, checkpoint_counts=checkpoint_counts,
                   coverage_and_reuse_counts=reuse_counts, timings=timings,
                   non_satisfied_checkpoints=[row for row in checkpoints if row['status'] != 'satisfied'])
    return {'summary': summary, 'pairs': pairs, 'checkpoints': checkpoints}


def _csv(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_markdown(summary):
    lines = ['# Native integration evaluation', '', summary['analysis_role'], '',
             'Every planned slot is accounted for by an original record or an explicit interruption ledger; all frozen files and archived record hashes were verified.', '',
             '| Engine | Planned pairs | Recorded attempts | Candidate attempts including interrupted slot | Completed | Exact native values preserved | Satisfied | Violated | Indeterminate | Unavailable | Recorded failure | Interrupted without record | Not reached |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in summary['pair_counts']:
        if row['grouping'] == 'engine':
            lines.append('| '+' | '.join(str(row[k]) for k in ('engine', 'planned', 'attempted', 'candidate_attempts_including_interrupted_slot', 'completed', 'exact_native_values', *PAIR_STATES))+' |')
    lines += ['', 'These are pair outcomes. The separate checkpoint table counts each recorded observation boundary.', '',
              '| Engine | Checkpoint | Observed | Satisfied | Violated | Indeterminate | Unavailable |',
              '|---|---|---:|---:|---:|---:|---:|']
    for row in summary['checkpoint_counts']:
        if row['grouping'] == 'engine':
            lines.append('| '+' | '.join(str(row[k]) for k in ('engine', 'checkpoint', 'observed_checkpoints', *STATES))+' |')
    lines += ['', '## Timing and interpretation', '',
              'Times are reported as observed seconds in timings.csv (median, quartiles, minimum, maximum and mean). Baseline extraction always preceded audited extraction; timing differences are not a causal estimate of overhead.', '',
              'Exact native-value preservation means the observer returned the producer values unchanged. It does not establish feature correctness, finiteness, clinical validity or cross-engine equality. MIRP numeric-column counts include metadata.', '',
              'All non-satisfied checkpoints and their row identifiers remain in summary.json and checkpoints.csv. Coverage and feature-reuse decisions use recorded-checkpoint denominators, separately from pair completion.', '',
              'An interrupted unrecorded slot is not a completed extraction or a measured result. Its start and completion are not established by an archived case record. Later not-reached slots contain no fabricated feature, timing or checkpoint observations. The interruption cause is undetermined.', '',
              'The sampled public clinical images appeared in the preceding study. They do not form a new independent clinical cohort.', '',
              'Freeze SHA-256: `'+summary['provenance']['freeze_sha256']+'`.',
              'Plan SHA-256: `'+summary['provenance']['plan_sha256']+'`.', '']
    return '\n'.join(lines)


def write_outputs(result, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Choose a fresh summary directory; archived derivatives are not overwritten.')
    output.mkdir(parents=True)
    summary = result['summary']
    files = {'summary.json': json.dumps(summary, sort_keys=True, indent=2, allow_nan=False)+'\n',
             'summary.md': render_markdown(summary), 'pairs.csv': _csv(result['pairs']),
             'checkpoints.csv': _csv(result['checkpoints']), 'pair_counts.csv': _csv(summary['pair_counts']),
             'checkpoint_counts.csv': _csv(summary['checkpoint_counts']),
             'coverage_and_reuse_counts.csv': _csv(summary['coverage_and_reuse_counts']),
             'timings.csv': _csv(summary['timings'])}
    for name, content in files.items():
        (output/name).write_text(content, encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--freeze', type=Path)
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    result = summarize(args.root, args.run, plan_path=args.plan, freeze_path=args.freeze)
    write_outputs(result, args.out)
    print(json.dumps(result['summary']['units'], sort_keys=True))


if __name__ == '__main__':
    main()
