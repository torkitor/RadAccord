"""Realize frozen prospective plans and summarize their first execution.

This script never decodes an image or executes a radiomics engine. It binds the
public selection/crop receipts to private filenames by hashes, preserving every
selected rank. The summarize command retains exclusions and interrupted slots.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_operational_benchmark as benchmark
from scripts.verify_prospective_freeze import verify as verify_general


COLLECTIONS = {'Task02_Heart': 'mr', 'Task06_Lung': 'ct'}
MODES = ('coverage', 'timing')
OPERATIONS = ('identity', 'linear_1p5', 'cubic_2')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def public_relative(path):
    target = Path(path).resolve()
    if ROOT not in target.parents:
        raise ValueError('Public provenance inputs must be repository files.')
    return target.relative_to(ROOT).as_posix()


def configuration(engine, operation, modality):
    if engine == 'pyradiomics':
        result = {'setting': {'binWidth': 25.} if modality == 'ct' else {'binCount': 32},
                  'imageType': {'Original': {}}}
        if operation != 'identity':
            result['setting'].update(resampledPixelSpacing=[1.5 if operation == 'linear_1p5' else 2.]*3,
                                     interpolator='sitkLinear' if operation == 'linear_1p5' else 'sitkBSpline')
        return result
    result = {'base_feature_families': ['all'], 'base_discretisation_method': 'fixed_bin_number',
              'base_discretisation_n_bins': 32}
    if operation != 'identity':
        result.update(new_spacing=1.5 if operation == 'linear_1p5' else 2.,
                      spline_order=1 if operation == 'linear_1p5' else 3, anti_aliasing=True)
    return result


def workflows(mode):
    operations = OPERATIONS if mode == 'coverage' else ('identity', 'cubic_2')
    return [{'id': operation+'_'+modality, 'modalities': [modality],
             'configs': {engine: configuration(engine, operation, modality) for engine in benchmark.ENGINES}}
            for modality in ('mr', 'ct') for operation in operations]


def selected_records(eligibility, crop_receipt, private_manifest):
    if eligibility.get('schema') != 'radaccord-new-clinical-eligibility-1' or \
            crop_receipt.get('schema_version') != 'clinical-crop-receipt-1':
        raise ValueError('Unexpected source eligibility or crop receipt schema.')
    eligible = {}
    for row in eligibility['records']:
        key = row['task'], row['selection_rank']
        if key in eligible or row['task'] not in COLLECTIONS or type(key[1]) is not int or not 1 <= key[1] <= 12:
            raise ValueError('Selected collection/rank entries are not unique or prespecified.')
        eligible[key] = row
    if eligibility.get('selected_slots') != len(eligible):
        raise ValueError('Eligibility selected-slot count differs from its records.')
    crops = {}
    for row in crop_receipt['records']:
        key = row['task'], row['selection_rank']
        if key in crops or key not in eligible:
            raise ValueError('Crop receipt contains duplicate or unselected slots.')
        crops[key] = row
    if set(crops) != set(eligible):
        raise ValueError('Crop preparation must retain every selected source, including failures.')
    records, inputs, seen_manifest = [], [], set()
    for collection, modality in COLLECTIONS.items():
        for rank in range(1, 13):
            key = collection, rank
            if key not in eligible:
                records.append({'collection': collection, 'selection_rank': rank, 'modality': modality,
                                'id': collection+'_unselected_rank_'+str(rank), 'status': 'selection_shortfall',
                                'source_eligible': False, 'exclusion_reasons': ['selected_source_unavailable']})
                continue
            source, crop = eligible[key], crops[key]
            identity = collection+'_'+source['source_basename'].removesuffix('.nii.gz')
            benchmark.identifier(identity)
            if type(source['source_eligible']) is not bool or (source['source_eligible'] and any(
                    not re.fullmatch('[0-9a-f]{64}', str(source[key])) for key in ('image_sha256', 'mask_sha256'))):
                raise ValueError('Eligible source inputs require exact public file hashes.')
            if crop['id'] != identity or crop['source_eligible'] != source['source_eligible'] or \
                    crop['source_image_sha256'] != source['image_sha256'] or \
                    crop['source_mask_sha256'] != source['mask_sha256']:
                raise ValueError('Crop provenance differs from its selected source.')
            status = crop['status']
            if status not in ('source_excluded', 'preparation_failed', 'prepared_and_verified'):
                raise ValueError('Unknown source/preparation outcome.')
            if status == 'source_excluded' and source['source_eligible'] or \
                    status != 'source_excluded' and not source['source_eligible']:
                raise ValueError('Preparation status contradicts source eligibility.')
            record = {'id': identity, 'collection': collection, 'selection_rank': rank,
                      'modality': modality, 'source_eligible': source['source_eligible'], 'status': status,
                      'source_image_sha256': source['image_sha256'], 'source_mask_sha256': source['mask_sha256'],
                      'exclusion_reasons': list(source['exclusion_reasons'])}
            if status == 'preparation_failed':
                record['preparation_reason_code'] = crop.get('reason_code', 'preparation_failed')
                benchmark.identifier(record['preparation_reason_code'])
            if status == 'prepared_and_verified':
                if identity not in private_manifest:
                    raise ValueError('A prepared input is absent from the private manifest.')
                for kind in ('image', 'mask'):
                    check = crop[kind+'_verification']
                    if not check['decoded_array_equal'] or not check['decoded_dtype_equal'] or \
                            check['maximum_world_error_mm'] > 1e-4 or check['geometry_tolerance_mm'] != 1e-4:
                        raise ValueError('The crop receipt does not establish the fixed preparation conditions.')
                    if benchmark.digest(private_manifest[identity][kind]) != crop[kind+'_sha256']:
                        raise ValueError('Private crop bytes differ from the public receipt.')
                if not crop['mask_verification']['selected_roi_completely_retained'] or crop.get('label') != 1 or \
                        crop.get('context_mm') != 10.:
                    raise ValueError('The crop omitted selected ROI support or changed the declared preparation.')
                item = {'id': identity, 'kind': 'image', 'collection': collection, 'selection_rank': rank,
                        'modality': modality, 'image_sha256': crop['image_sha256'], 'mask_sha256': crop['mask_sha256']}
                inputs.append(item); seen_manifest.add(identity)
                record.update(image_sha256=item['image_sha256'], mask_sha256=item['mask_sha256'])
            records.append(record)
    if set(private_manifest) != seen_manifest:
        raise ValueError('The private manifest contains unexpected, excluded or unselected inputs.')
    return records, inputs


def realize_plan(mode, selected, inputs, provenance):
    selected = [deepcopy(row) for row in selected if mode == 'coverage' or row['selection_rank'] <= 4]
    actual_inputs = [deepcopy(row) for row in inputs if mode == 'coverage' or row['selection_rank'] <= 4]
    plan = {'schema_version': benchmark.SCHEMA, 'mode': mode, 'repeats': 1 if mode == 'coverage' else 4,
            'warmup_pairs_per_worker': 0 if mode == 'coverage' else 1, 'native_threads': 1,
            'timeout_seconds_per_pair': 300, 'inputs': actual_inputs, 'workflows': workflows(mode),
            'selected_inputs': selected, 'provenance': provenance,
            'intention_to_evaluate_pairs': 144 if mode == 'coverage' else 128,
            'selected_volume_slots': len(selected),
            'source_eligible_volume_slots': sum(row['source_eligible'] for row in selected),
            'prepared_volume_slots': len(actual_inputs)}
    benchmark.validate_plan(plan)
    plan['native_planned_pairs'] = sum(len(benchmark.planned_slots(plan, engine)) for engine in benchmark.ENGINES)
    plan['not_native_planned_pairs'] = plan['intention_to_evaluate_pairs']-plan['native_planned_pairs']
    return plan


def build(crop_receipt, private_inputs, eligibility, general_freeze, environments, output_dir):
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError('Use a new operational-plan directory.')
    paths = {name: public_relative(path) for name, path in {
        'crop_receipt': crop_receipt, 'eligibility': eligibility,
        'general_freeze': general_freeze, 'environments': environments}.items()}
    verified = verify_general(ROOT, paths['general_freeze'])
    required_preexisting = {paths['environments'], paths['eligibility'],
                           'scripts/build_prospective_plans.py', 'protocol/prospective_native_validation.md'}
    if not required_preexisting <= verified['files'].keys():
        raise ValueError('The source/code freeze must bind environments, eligibility, builder and protocol.')
    pins = read_json(environments)
    selected, inputs = selected_records(read_json(eligibility), read_json(crop_receipt), read_json(private_inputs))
    provenance = {name: {'file': relative, 'sha256': benchmark.digest(ROOT/relative)} for name, relative in paths.items()}
    provenance['private_manifest_sha256'] = benchmark.digest(private_inputs)
    output_dir.mkdir(parents=True)
    result = {}
    for mode in MODES:
        plan_path = output_dir/(mode+'_plan.json')
        plan = realize_plan(mode, selected, inputs, provenance)
        write_json(plan_path, plan)
        freeze_path = output_dir/(mode+'_freeze.json')
        extra = set(verified['files']) | set(paths.values()) | {'scripts/build_prospective_plans.py'}
        benchmark.create_freeze(plan_path, pins, freeze_path, private_inputs=private_inputs, extra_files=extra)
        result[mode] = {'plan_sha256': benchmark.digest(plan_path), 'freeze_sha256': benchmark.digest(freeze_path),
                        'intention_to_evaluate_pairs': plan['intention_to_evaluate_pairs'],
                        'native_planned_pairs': plan['native_planned_pairs'],
                        'not_native_planned_pairs': plan['not_native_planned_pairs']}
    write_json(output_dir/'plan_realization.json', {'schema_version': 'prospective-plan-realization-1',
               'provenance': provenance, 'plans': result})
    return result


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def volume_median_summary(values):
    values = [value for value in values if value is not None]
    result = benchmark.distribution(values)
    result.update(minimum=min(values) if values else None, maximum=max(values) if values else None)
    return result


def summarize(plans, runs, output):
    """Deterministic first-execution summary; no images/native engines or retries."""
    plan_map, hashes, freezes, freeze_hashes = {}, {}, {}, {}
    for path in plans:
        plan = benchmark.validate_plan(read_json(path))
        if plan['mode'] in plan_map:
            raise ValueError('Supply exactly one plan per mode.')
        plan_map[plan['mode']] = plan; hashes[plan['mode']] = benchmark.digest(path)
        freeze_path = Path(path).with_name(plan['mode']+'_freeze.json')
        freeze = read_json(freeze_path)
        if freeze.get('plan_sha256') != hashes[plan['mode']] or freeze.get('mode') != plan['mode']:
            raise ValueError('An operational freeze does not bind its supplied plan and mode.')
        freezes[plan['mode']] = freeze; freeze_hashes[plan['mode']] = benchmark.digest(freeze_path)
    run_map, provenance = {}, []
    for directory in runs:
        directory = Path(directory)
        metadata = read_json(directory/'run_metadata.json')
        key = metadata['mode'], metadata['engine']
        if key in run_map or key[0] not in plan_map or metadata['plan_sha256'] != hashes[key[0]] or \
                metadata['freeze_sha256'] != freeze_hashes[key[0]]:
            raise ValueError('Duplicate, unplanned or differently frozen run; retries must be separate.')
        expected = benchmark.planned_slots(plan_map[key[0]], key[1])
        if read_json(directory/'planned_slots.json') != expected:
            raise ValueError('The retained planned-slot ledger differs from the frozen plan.')
        starts, records = lines(directory/'attempt_starts.jsonl'), lines(directory/'cases.jsonl')
        maps = []
        for rows in (starts, records):
            found = {}
            for row in rows:
                slot = row.get('slot')
                if type(slot) is not int or not 0 <= slot < len(expected) or slot in found or \
                        any(row.get(field) != value for field, value in expected[slot].items()):
                    raise ValueError('An attempt is duplicated or differs from its planned slot.')
                found[slot] = row
            maps.append(found)
        started, completed_records = maps
        if not completed_records.keys() <= started.keys():
            raise ValueError('A final attempt record has no retained start record.')
        files = freezes[key[0]]['files']
        expected_sources = {name: files[('software/' if name.endswith('_contracts') else 'radaccord/')+name+'.py']
                            for name in ('evidence', 'operators', 'numerics', key[1], 'physical_contracts', 'sampling_contracts')}
        for row in completed_records.values():
            if type(row.get('completed')) is not bool:
                raise ValueError('A native attempt must have an explicit completion value.')
            if row['completed']:
                report = row.get('report', {})
                if report.get('status') not in benchmark.STATES or type(row.get('native_values_unchanged')) is not bool or \
                        report.get('checker', {}).get('source_sha256') != expected_sources or \
                        report.get('checker', {}).get('implementation_sha256') != benchmark.config_digest(expected_sources):
                    raise ValueError('A completed native record lacks valid frozen implementation evidence.')
                if report.get('engine') != {'name': key[1], 'version': freezes[key[0]]['environments'][key[1]]['packages'][key[1]]}:
                    raise ValueError('A native record uses an unexpected engine version.')
                if key[0] == 'timing':
                    a, b = row.get('baseline_seconds'), row.get('audited_seconds')
                    if any(not isinstance(value, (int, float)) or not benchmark.math.isfinite(value) or value <= 0
                           for value in (a, b)) or row.get('absolute_overhead_seconds') != b-a or not benchmark.math.isclose(
                               row.get('paired_log_ratio', float('nan')), benchmark.math.log(b/a), abs_tol=1e-12, rel_tol=1e-12):
                        raise ValueError('A paired timing metric differs from its retained arm times.')
        run_map[key] = (started, completed_records)
        provenance.append({'mode': key[0], 'engine': key[1], 'plan_sha256': metadata['plan_sha256'],
            'freeze_sha256': metadata['freeze_sha256'], 'records_sha256': benchmark.digest(directory/'cases.jsonl'),
            'attempt_starts_sha256': benchmark.digest(directory/'attempt_starts.jsonl')})
    groups, per_volume = [], []
    for mode, plan in sorted(plan_map.items()):
        for engine in benchmark.ENGINES:
            started, observed = run_map.get((mode, engine), ({}, {}))
            planned = benchmark.planned_slots(plan, engine)
            for collection, modality in COLLECTIONS.items():
                selected = [row for row in plan['selected_inputs'] if row['collection'] == collection]
                for workflow in [row for row in plan['workflows'] if modality in row['modalities']]:
                    expected = [row for row in planned if row['collection'] == collection and row['workflow'] == workflow['id']]
                    rows = [observed[row['slot']] for row in expected if row['slot'] in observed]
                    complete = [row for row in rows if row.get('completed')]
                    count_started = sum(row['slot'] in started for row in expected)
                    record = {'mode': mode, 'collection': collection, 'workflow': workflow['id'], 'engine': engine,
                        'selected_volume_slots': len(selected), 'source_eligible_volume_slots': sum(row['source_eligible'] for row in selected),
                        'prepared_volume_slots': sum(row['status'] == 'prepared_and_verified' for row in selected),
                        'intention_to_evaluate_pairs': len(selected)*plan['repeats'], 'native_planned_pairs': len(expected),
                        'not_native_planned_pairs': len(selected)*plan['repeats']-len(expected),
                        'attempted_pairs': count_started, 'recorded_pairs': len(rows), 'completed_pairs': len(complete),
                        'exact_preservation_pairs': sum(row.get('native_values_unchanged', False) for row in complete),
                        'failed_recorded_pairs': sum(not row.get('completed', False) for row in rows),
                        'started_without_record_pairs': count_started-len(rows), 'unstarted_pairs': len(expected)-count_started,
                        'source_or_preparation_outcomes': dict(sorted(Counter(row['status'] for row in selected).items())),
                        'relationship_outcomes': {state: sum(row.get('report', {}).get('status') == state for row in complete)
                                                  for state in benchmark.STATES}}
                    checkpoints = [checkpoint for row in complete for checkpoint in row['report'].get('checkpoints', [])]
                    record['checkpoint_count'] = len(checkpoints)
                    record['checkpoint_outcomes'] = {state: sum(row.get('status') == state for row in checkpoints)
                                                      for state in benchmark.STATES}
                    record['reported_coverage_obligations'] = dict(sorted(Counter(
                        row['coverage'].get('status', 'unavailable') for row in checkpoints if 'coverage' in row).items()))
                    record['reported_reuse_obligations'] = dict(sorted(Counter(
                        row['feature_reuse'].get('decision', 'unavailable') for row in checkpoints if 'feature_reuse' in row).items()))
                    if mode == 'timing':
                        warmups = [row['warmup_comparison'] for row in rows if row.get('warmup_comparison', {}).get('completed')]
                        record['warmup_pairs_completed'] = len(warmups)
                        record['warmup_exact_preservation_pairs'] = sum(row['native_values_unchanged'] for row in warmups)
                    volume_stats = benchmark.summarize(rows, mode)['volume_workflow_summaries']
                    for volume in volume_stats:
                        per_volume.append({'mode': mode, 'collection': collection, 'engine': engine, **volume})
                    if mode == 'timing':
                        record['volume_medians'] = {metric: volume_median_summary(volume[metric]['median'] for volume in volume_stats)
                            for metric in ('baseline_seconds', 'audited_seconds', 'absolute_overhead_seconds', 'paired_log_ratio',
                                           'pair_lifetime_peak_bytes')}
                    groups.append(record)
    constructed = []
    for (mode, engine), (_, records) in run_map.items():
        if mode != 'coverage' and any(row.get('constructed_tasks') for row in records.values()):
            raise ValueError('Constructed tasks belong only to the coverage phase.')
    for engine in benchmark.ENGINES if 'coverage' in plan_map else ():
        mode = 'coverage'
        _, records = run_map.get((mode, engine), ({}, {}))
        for collection in COLLECTIONS:
            rows = [row for row in records.values() if row['collection'] == collection]
            task_summary = benchmark.summarize(rows, mode)['constructed_tasks']
            expected_sources = [row for row in plan_map[mode]['selected_inputs'] if row['collection'] == collection]
            constructed.append({'mode': mode, 'engine': engine, 'collection': collection,
                'intention_to_evaluate_tasks': 2*len(expected_sources),
                'prepared_source_tasks': 2*sum(row['status'] == 'prepared_and_verified' for row in expected_sources),
                **task_summary})
    result = {'schema_version': 'prospective-aggregate-1', 'plan_sha256': dict(sorted(hashes.items())),
              'run_provenance': sorted(provenance, key=lambda row: (row['mode'], row['engine'])),
              'groups': groups, 'volume_summaries': per_volume, 'constructed_tasks': constructed,
              'scope': 'Author-run computational evaluation. Volume-level medians are summarized without treating repeats as independent inputs. Missing or interrupted slots and selected exclusions remain visible. Constructed tasks and engine duplicates do not establish spontaneous error prevalence or clinical benefit.'}
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    build_parser = actions.add_parser('build')
    for argument in ('crop-receipt', 'private-inputs', 'eligibility', 'general-freeze', 'environments', 'output-dir'):
        build_parser.add_argument('--'+argument, required=True, type=Path)
    summary_parser = actions.add_parser('summarize')
    summary_parser.add_argument('--plan', type=Path, action='append', required=True)
    summary_parser.add_argument('--run', type=Path, action='append', required=True)
    summary_parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'build':
        result = build(args.crop_receipt, args.private_inputs, args.eligibility, args.general_freeze,
                       args.environments, args.output_dir)
        print(json.dumps(result, sort_keys=True))
    else:
        result = summarize(args.plan, args.run, args.output)
        print(json.dumps({'status': 'summarized', 'groups': len(result['groups'])}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'reason_code': 'prospective_plan_or_summary_failed',
                          'exception_type': type(error).__name__}))
        raise SystemExit(2)
