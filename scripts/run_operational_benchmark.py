"""Frozen, counterbalanced native timing and constructed correction benchmark.

Public output contains study identifiers, hashes and derived records only. Inputs
are loaded once per worker. Timing mode warms both arms before a measured pair;
coverage mode runs one un-warmed pair without estimating overhead. This is a
controlled development/validation experiment, not an
external-user study or a measurement of spontaneous error prevalence.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

for _variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                  'NUMEXPR_NUM_THREADS', 'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'):
    os.environ[_variable] = '1'

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from run_native_study import digest, json_value, mirp_objects, pair_synthetic, sitk
from radaccord.evidence import config_digest, feature_digest, frame_record
import numpy as np

sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(1)
SCHEMA = 'operational-benchmark-1'
ENGINES = ('pyradiomics', 'mirp')
STATES = ('satisfied', 'violated', 'indeterminate', 'unavailable')
REQUIRED_FREEZE_FILES = {
    'scripts/run_operational_benchmark.py', 'scripts/run_native_study.py',
    'scripts/run_sampling_study.py', 'protocol/operational_benchmark.md',
    'scripts/tests/test_operational_benchmark.py', 'pyproject.toml', 'radaccord/__init__.py',
    'radaccord/evidence.py', 'radaccord/legacy.py', 'radaccord/operators.py',
    'radaccord/numerics.py', 'radaccord/pyradiomics.py', 'radaccord/mirp.py',
    'software/physical_contracts.py', 'software/sampling_contracts.py',
}


def emit(handle, record):
    handle.write(json.dumps(json_value(record), sort_keys=True, allow_nan=False)+'\n')
    handle.flush()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('Use short public study identifiers, without paths or contacts.')
    return value


def validate_plan(plan):
    if plan.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported operational benchmark plan.')
    mode, repeats = plan.get('mode'), plan.get('repeats')
    if mode not in ('coverage', 'timing'):
        raise ValueError('Specify coverage or timing mode explicitly.')
    if type(repeats) is not int or (mode == 'coverage' and repeats != 1) or \
            (mode == 'timing' and (repeats < 2 or repeats % 2)):
        raise ValueError('Coverage requires one pair; timing requires an even number of repeats, at least two.')
    warmup = 1 if mode == 'timing' else 0
    if type(plan.get('warmup_pairs_per_worker')) is not int or plan['warmup_pairs_per_worker'] != warmup or \
            type(plan.get('native_threads')) is not int or plan['native_threads'] != 1:
        raise ValueError('Mode-specific warmup count and one native thread are required.')
    timeout = plan.get('timeout_seconds_per_pair')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout < 86400:
        raise ValueError('Supply a finite positive per-pair timeout below one day.')
    if (not plan.get('inputs') and not plan.get('selected_inputs')) or not plan.get('workflows'):
        raise ValueError('Specify inputs and native configurations before execution.')
    input_ids, workflow_ids = set(), set()
    for item in plan['inputs']:
        identity = identifier(item['id'])
        if identity in input_ids or item.get('modality') not in ('mr', 'ct', 'generic'):
            raise ValueError('Input identifiers must be unique and modalities explicit.')
        input_ids.add(identity)
        if item.get('kind') == 'synthetic':
            if isinstance(item.get('seed'), bool) or not isinstance(item.get('seed'), int):
                raise ValueError('A synthetic input requires an integer seed.')
            allowed = {'id', 'kind', 'modality', 'seed', 'collection', 'selection_rank'}
        elif item.get('kind') == 'image':
            if any(not re.fullmatch('[0-9a-f]{64}', str(item.get(key, '')))
                   for key in ('image_sha256', 'mask_sha256')):
                raise ValueError('Image inputs require frozen file hashes.')
            allowed = {'id', 'kind', 'modality', 'image_sha256', 'mask_sha256', 'collection', 'selection_rank'}
        else:
            raise ValueError('Unsupported input kind.')
        if set(item)-allowed:
            raise ValueError('Public input entries contain unsupported fields.')
        if 'collection' in item:
            identifier(item['collection'])
        if 'selection_rank' in item and (type(item['selection_rank']) is not int or item['selection_rank'] < 1):
            raise ValueError('Selection ranks must be positive integers.')
    for workflow in plan['workflows']:
        identity = identifier(workflow['id'])
        if identity in workflow_ids or set(workflow)-{'id', 'modalities', 'configs'}:
            raise ValueError('Workflow identifiers must be unique; fields are explicit.')
        workflow_ids.add(identity)
        if not workflow.get('modalities') or set(workflow['modalities'])-{'mr', 'ct', 'generic'}:
            raise ValueError('Workflow modalities must be specified.')
        if not workflow.get('configs') or set(workflow['configs'])-set(ENGINES):
            raise ValueError('Specify explicit native engine configurations.')
        for config in workflow['configs'].values():
            if not isinstance(config, dict):
                raise ValueError('A native configuration must be a dictionary.')
            encoded = json.dumps(config, allow_nan=False)
            if re.search(r'\\\\|[A-Za-z]:|file:|@|/', encoded):
                raise ValueError('Public configuration must not contain paths or contacts.')
    return plan


def planned_slots(plan, engine):
    """Deterministic order; timing repeats are exactly balanced within input/config."""
    slots = []
    for item in plan['inputs']:
        for workflow in plan['workflows']:
            if engine not in workflow['configs'] or item['modality'] not in workflow['modalities']:
                continue
            offset = int(hashlib.sha256((item['id']+'|'+workflow['id']).encode()).hexdigest(), 16) % 2
            for repeat in range(plan['repeats']):
                slots.append({'slot': len(slots), 'mode': plan['mode'], 'input_id': item['id'], 'source_kind': item['kind'],
                              'modality': item['modality'], 'engine': engine, 'workflow': workflow['id'],
                              'collection': item.get('collection', 'unspecified'),
                              'repeat': repeat, 'order': 'AB' if (repeat+offset) % 2 == 0 else 'BA',
                              'config_sha256': config_digest(workflow['configs'][engine])})
    return slots


def create_freeze(plan_path, environments, output_path, private_inputs=None, extra_files=()):
    """Write a new internal freeze; do not execute native extraction or decode images."""
    plan_path, output_path = Path(plan_path), Path(output_path)
    plan = validate_plan(json.loads(plan_path.read_text(encoding='utf-8')))
    engines = {engine for workflow in plan['workflows'] for engine in workflow['configs']}
    if output_path.exists() or not engines <= environments.keys():
        raise ValueError('Use a new freeze filename and specify every native environment.')
    for engine in engines:
        environment = environments[engine]
        if not environment.get('python') or not {engine, 'numpy', 'SimpleITK'} <= environment.get('packages', {}).keys():
            raise ValueError('A native environment specification is incomplete.')
    if any(item['kind'] == 'image' for item in plan['inputs']) and private_inputs is None:
        raise ValueError('Image inputs require a private manifest before freezing.')
    paths = REQUIRED_FREEZE_FILES | set(extra_files)
    hashes = {}
    for relative in sorted(paths):
        target = (ROOT/relative).resolve()
        if ROOT not in target.parents or not target.is_file():
            raise ValueError('Freeze entries must be existing repository files.')
        hashes[relative] = digest(target)
    freeze = {'schema_version': SCHEMA, 'mode': plan['mode'],
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'analysis_role': 'prospectively_frozen_author_run_controlled_benchmark',
              'plan_sha256': digest(plan_path), 'environments': environments, 'files': hashes}
    if private_inputs is not None:
        freeze['private_inputs_sha256'] = digest(private_inputs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(freeze, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    return freeze


def verify_freeze(path, plan_path, private_inputs=None):
    freeze = json.loads(path.read_text(encoding='utf-8'))
    if freeze.get('schema_version') != SCHEMA or digest(plan_path) != freeze.get('plan_sha256'):
        raise ValueError('The operational plan is not bound to this freeze.')
    if not REQUIRED_FREEZE_FILES <= freeze.get('files', {}).keys():
        raise ValueError('The freeze omits required benchmark or checking sources.')
    for relative, expected in freeze['files'].items():
        target = (ROOT/relative).resolve()
        if ROOT not in target.parents or not target.is_file() or digest(target) != expected:
            raise ValueError('A required frozen source differs.')
    if private_inputs is not None and digest(private_inputs) != freeze.get('private_inputs_sha256'):
        raise ValueError('The private input manifest differs from the frozen manifest.')
    return freeze


def verify_environment(freeze, engine):
    environment = freeze.get('environments', {}).get(engine)
    if not environment or environment.get('python') != platform.python_version():
        raise ValueError('The Python environment differs from the frozen plan.')
    packages = environment.get('packages', {})
    if not {engine, 'numpy', 'SimpleITK'} <= packages.keys():
        raise ValueError('The freeze omits required native package versions.')
    if any(version(package) != expected for package, expected in packages.items()):
        raise ValueError('An installed package differs from its frozen version.')


def peak_memory():
    """Lifetime process high-water mark, never falsely attributed to one arm."""
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in (
                            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                            'PagefileUsage', 'PeakPagefileUsage')]]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return {'bytes': None, 'method': 'windows_peak_working_set', 'available': False}
        return {'bytes': int(counters.PeakWorkingSetSize), 'method': 'windows_peak_working_set', 'available': True}
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'bytes': int(value*(1 if sys.platform == 'darwin' else 1024)),
            'method': 'resource_ru_maxrss', 'available': True}


def load_pair(item, private_inputs):
    if item['kind'] == 'synthetic':
        return pair_synthetic(item['seed'])
    if private_inputs is None:
        raise ValueError('A private input manifest is required for image inputs.')
    locations = json.loads(private_inputs.read_text(encoding='utf-8'))[item['id']]
    paths = [Path(locations[key]) for key in ('image', 'mask')]
    if [digest(path) for path in paths] != [item['image_sha256'], item['mask_sha256']]:
        raise ValueError('Source input hashes differ from the frozen plan.')
    return tuple(sitk.ReadImage(str(path)) for path in paths)


def native_callbacks(engine, pair, modality, identity, config):
    """Both arms include extractor construction/execution; input copies precede timing."""
    if engine == 'pyradiomics':
        from radiomics.featureextractor import RadiomicsFeatureExtractor
        from radaccord.pyradiomics import audit_pyradiomics
        def prepare():
            return tuple(sitk.Image(image) for image in pair)
        def direct(inputs):
            result = RadiomicsFeatureExtractor(deepcopy(config)).execute(*inputs, label=1)
            return {key: value for key, value in result.items() if not key.startswith('diagnostics_')}, None
        def audited(inputs):
            result = audit_pyradiomics(*inputs, config=deepcopy(config), label=1)
            return result['features'], result['report']
    else:
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        image, mask = mirp_objects(pair, modality, identity)
        def prepare():
            return deepcopy(image), deepcopy(mask)
        def direct(inputs):
            result = extract_features_and_images(image=inputs[0], mask=inputs[1], **deepcopy(config),
                export_features=True, export_images=True, write_features=False, write_images=False,
                image_export_format='native')
            if len(result) != 1:
                raise ValueError('The benchmark requires one native workflow per configuration.')
            return result[0][0], None
        def audited(inputs):
            result = audit_mirp(*inputs, config=deepcopy(config))
            return result['features'], result['report']
    return prepare, {'A': direct, 'B': audited}


def feature_comparison(engine, baseline, audited):
    if engine == 'pyradiomics':
        missing = len(baseline.keys() ^ audited.keys())
        changed = sum(not np.array_equal(np.asarray(baseline[key]), np.asarray(audited[key]), equal_nan=True)
                      for key in baseline.keys() & audited.keys())
        details = {'missing_keys': missing, 'changed_shared_values': changed, 'affected_keys': missing+changed}
        return missing+changed == 0, feature_digest(baseline), feature_digest(audited), details
    import pandas as pd
    try:
        pd.testing.assert_frame_equal(baseline, audited, check_exact=True)
        equal = True
    except AssertionError:
        equal = False
    def record(table):
        numeric = table.select_dtypes(include=np.number)
        return feature_digest({str(column): numeric[column].iloc[0] for column in numeric})
    differences = abs(len(baseline.columns)-len(audited.columns))
    for index in range(min(len(baseline.columns), len(audited.columns))):
        try:
            pd.testing.assert_series_equal(baseline.iloc[:, index], audited.iloc[:, index], check_exact=True)
        except AssertionError:
            differences += 1
    details = {'affected_column_positions': differences, 'baseline_rows': len(baseline), 'observed_rows': len(audited),
               'scope': 'Full tables compared exactly; position counts include changed names, metadata and indices without exposing them.'}
    return equal, record(baseline), record(audited), details


def measure_pair(engine, pair, modality, identity, config, order, *, mode='timing'):
    prepare, callbacks = native_callbacks(engine, pair, modality, identity, config)
    phase_name = 'measured' if mode == 'timing' else 'extractions'
    result = {'completed': False, 'mode': mode, 'warmup': {}, phase_name: {}, 'pair_peak_memory_before': peak_memory()}
    outputs = {}
    # Warm both arms once, in the reverse order; keep their timings separate.
    phases = [('warmup', order[::-1])] if mode == 'timing' else []
    for phase, sequence in phases+[(phase_name, order)]:
        warmup_outputs = {}
        for arm in sequence:
            try:
                inputs = prepare()
                started = time.perf_counter()
                features, report = callbacks[arm](inputs)
                seconds = time.perf_counter()-started
                result[phase][arm] = {'completed': True}
                if mode == 'timing':
                    result[phase][arm]['seconds'] = seconds
                if phase == phase_name:
                    outputs[arm] = features
                    if arm == 'B':
                        result['report'] = report
                else:
                    warmup_outputs[arm] = features
                del inputs, features, report
            except Exception as error:
                result[phase][arm] = {'completed': False, 'exception_type': type(error).__name__,
                                      'reason_code': 'native_arm_failed'}
                # Do not manufacture a measured pair after a failed warmup.
                if phase == 'warmup':
                    result['reason_code'] = 'warmup_incomplete'
                    result['pair_peak_memory_after'] = peak_memory()
                    return result
        if phase == 'warmup':
            equal, direct_values, observed_values, details = feature_comparison(
                engine, warmup_outputs['A'], warmup_outputs['B'])
            result['warmup_comparison'] = {'completed': True, 'native_values_unchanged': equal,
                                           'baseline_values': direct_values, 'observed_values': observed_values,
                                           'comparison_details': details}
            del warmup_outputs
    result['pair_peak_memory_after'] = peak_memory()
    if set(outputs) == {'A', 'B'}:
        equal, direct_values, observed_values, details = feature_comparison(engine, outputs['A'], outputs['B'])
        result.update(completed=True, native_values_unchanged=equal, baseline_values=direct_values,
                      observed_values=observed_values, comparison_details=details)
        if mode == 'timing':
            direct, audited = result['measured']['A']['seconds'], result['measured']['B']['seconds']
            result.update(baseline_seconds=direct, audited_seconds=audited,
                          absolute_overhead_seconds=audited-direct, paired_log_ratio=math.log(audited/direct))
    else:
        result['reason_code'] = 'measured_pair_incomplete' if mode == 'timing' else 'coverage_pair_incomplete'
    return result


def constructed_correction_tasks(pair):
    """Owned identity tasks: shared shift or decoded intensity corruption, then restore.

    These are deliberately introduced faults, never independently discovered
    operational errors. The correct target is retained before candidate creation.
    """
    from run_sampling_study import from_sitk, declaration, source_geometry, activity
    from radaccord.numerics import verify_native_operation
    image, mask = pair
    source_pair = (sitk.Cast(image, sitk.sitkFloat64), sitk.Cast(mask == 1, sitk.sitkUInt8))
    source, _ = from_sitk(source_pair)
    spec = declaration(np.eye(4), source.data.shape)
    spec['output_dtype'] = 'float64'
    records = []
    def observe(candidate_pair):
        candidate, paired = from_sitk(candidate_pair)
        return {'paired_geometry': paired, 'source_aware_geometry': source_geometry(source, candidate, spec),
                'radaccord': verify_native_operation(source, candidate, spec),
                'activity': activity(candidate, source), 'candidate': frame_record(candidate)}
    control = observe(tuple(sitk.Image(value) for value in source_pair))
    for mechanism in ('shared_origin_shift', 'decoded_intensity_offset'):
        candidate = tuple(sitk.Image(value) for value in source_pair)
        if mechanism == 'shared_origin_shift':
            for value in candidate:
                value.SetOrigin(tuple(np.asarray(value.GetOrigin())+np.asarray([7., 0., 0.])))
        else:
            candidate = (candidate[0]+2., candidate[1])
        before = observe(candidate)
        corrected = observe(tuple(sitk.Image(value) for value in source_pair))
        records.append({'mechanism': mechanism, 'case_kind': 'constructed_failure_and_declared_correction',
                        'declaration': spec, 'source': frame_record(source), 'valid_control': control,
                        'fault': before, 'correction': corrected,
                        'correction_action': 'restore_retained_identity_source',
                        'restored_declared_relationship': corrected['radaccord']['status'] == 'satisfied'})
    return records


def worker(args, plan, slot):
    item = next(value for value in plan['inputs'] if value['id'] == slot['input_id'])
    workflow = next(value for value in plan['workflows'] if value['id'] == slot['workflow'])
    record = dict(slot)
    try:
        pair = load_pair(item, args.private_inputs)
        record.update(measure_pair(args.engine, pair, item['modality'], item['id'],
                                   workflow['configs'][args.engine], slot['order'], mode=plan['mode']))
        # A single copy per input/engine: repeated timing pairs are not new fault cases.
        first = next(value for value in planned_slots(plan, args.engine) if value['input_id'] == item['id'])
        if plan['mode'] == 'coverage' and slot['slot'] == first['slot']:
            try:
                record['constructed_tasks'] = constructed_correction_tasks(pair)
            except Exception as error:
                record['constructed_tasks_error'] = {'reason_code': 'constructed_task_failed',
                                                      'exception_type': type(error).__name__}
    except Exception as error:
        record.update(completed=False, exception_type=type(error).__name__, reason_code='benchmark_worker_failed')
    temporary = args.worker_result.with_suffix('.tmp')
    temporary.write_text(json.dumps(json_value(record), sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(args.worker_result)


def distribution(values):
    values = [float(value) for value in values if value is not None and math.isfinite(value)]
    if not values:
        return {'n': 0, 'median': None, 'q1': None, 'q3': None}
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    return {'n': len(values), 'median': float(median), 'q1': float(q1), 'q3': float(q3)}


def summarize(rows, mode='timing'):
    if mode not in ('coverage', 'timing') or any(row.get('mode', mode) != mode for row in rows):
        raise ValueError('Coverage and timing must be summarized separately.')
    groups = {}
    for row in rows:
        key = (row['input_id'], row['workflow'])
        groups.setdefault(key, []).append(row)
    volumes = []
    for (input_id, workflow), values in sorted(groups.items()):
        complete = [row for row in values if row.get('completed')]
        record = {'input_id': input_id, 'workflow': workflow, 'planned': len(values),
                  'completed': len(complete), 'unchanged': sum(row.get('native_values_unchanged', False) for row in complete),
                  'orders': {order: sum(row['order'] == order for row in values) for order in ('AB', 'BA')}}
        if mode == 'timing':
            for metric in ('baseline_seconds', 'audited_seconds', 'absolute_overhead_seconds', 'paired_log_ratio'):
                record[metric] = distribution(row.get(metric) for row in complete)
        record['pair_lifetime_peak_bytes'] = distribution(
            row.get('pair_peak_memory_after', {}).get('bytes') for row in complete)
        record['relationship_outcomes'] = {state: sum(row.get('report', {}).get('status') == state for row in complete)
                                           for state in STATES}
        volumes.append(record)
    tasks = [task for row in rows for task in row.get('constructed_tasks', [])]
    constructed = {'recorded_tasks': len(tasks),
                   'active_faults': sum(task['fault']['activity']['active'] for task in tasks),
                   'restored_relationships': sum(task['restored_declared_relationship'] for task in tasks),
                   'task_errors': sum('constructed_tasks_error' in row for row in rows),
                   'comparators': {}}
    for comparator in ('paired_geometry', 'source_aware_geometry', 'radaccord'):
        constructed['comparators'][comparator] = {
            condition: {state: sum(task[condition][comparator]['status'] == state for task in tasks)
                        for state in STATES}
            for condition in ('valid_control', 'fault', 'correction')}
    return {'mode': mode, 'planned': len(rows), 'completed': sum(row.get('completed', False) for row in rows),
            'unchanged': sum(row.get('native_values_unchanged', False) for row in rows),
            'volume_workflow_summaries': volumes,
            'constructed_tasks': constructed,
            'memory_scope': 'Process lifetime high-water mark including both arms and any warmup; not per-arm incremental memory.',
            'inference_scope': ('Descriptive within-volume paired timing; repeats are not independent volumes or participants.'
                                if mode == 'timing' else 'Coverage and exact-output preservation; no overhead estimate.')}


def run_controller(args, plan, freeze):
    slots = planned_slots(plan, args.engine)
    if args.output.exists() or args.private_log_dir.exists():
        raise ValueError('Specify new output/log directories and at least one applicable workflow.')
    public, private = args.output.resolve(), args.private_log_dir.resolve()
    if public == private or public in private.parents or private in public.parents:
        raise ValueError('Public output and private logs must use separate, non-nested directories.')
    args.output.mkdir(parents=True); args.private_log_dir.mkdir(parents=True)
    (args.output/'planned_slots.json').write_text(json.dumps(slots, indent=2)+'\n', encoding='utf-8')
    started = datetime.now(timezone.utc).isoformat()
    metadata = {'schema_version': SCHEMA, 'mode': plan['mode'], 'engine': args.engine,
                'planned': len(slots), 'started_utc': started, 'plan_sha256': digest(args.plan),
                'freeze_sha256': digest(args.freeze)}
    (args.output/'run_metadata.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    rows = []
    with (args.output/'cases.jsonl').open('w', encoding='utf-8', newline='\n') as ledger, \
            (args.output/'attempt_starts.jsonl').open('w', encoding='utf-8', newline='\n') as starts:
        for slot in slots:
            record = dict(slot)
            result_path = args.private_log_dir/f"{slot['slot']:05d}.json"
            command = [sys.executable, str(Path(__file__).resolve()), '--engine', args.engine,
                       '--plan', str(args.plan), '--freeze', str(args.freeze),
                       '--worker-slot', str(slot['slot']), '--worker-result', str(result_path)]
            if args.private_inputs is not None:
                command.extend(['--private-inputs', str(args.private_inputs)])
            start = time.perf_counter()
            emit(starts, {**slot, 'attempt_started_utc': datetime.now(timezone.utc).isoformat()})
            with (args.private_log_dir/f"{slot['slot']:05d}.log").open('wb') as log:
                try:
                    process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                        timeout=plan['timeout_seconds_per_pair'], check=False)
                    if process.returncode == 0 and result_path.is_file():
                        payload = json.loads(result_path.read_text(encoding='utf-8'))
                        if any(payload.get(key) != value for key, value in slot.items()):
                            raise ValueError('The worker record does not match its planned slot.')
                        record = payload
                    else:
                        record.update(completed=False, reason_code='worker_incomplete', worker_exit_code=process.returncode)
                except subprocess.TimeoutExpired:
                    record.update(completed=False, reason_code='worker_timeout')
                except (OSError, ValueError):
                    record.update(completed=False, reason_code='worker_record_unavailable')
            record['worker_wall_seconds'] = time.perf_counter()-start
            rows.append(record); emit(ledger, record)
            emit(sys.stdout, {'engine': args.engine, 'retained_slots': len(rows), 'planned_slots': len(slots)})
    summary = {'schema_version': SCHEMA, 'analysis_role': 'controlled_operational_benchmark',
               'engine': args.engine, 'engine_version': version(args.engine),
               'python_version': platform.python_version(), 'numpy_version': np.__version__,
               'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
               'plan_sha256': digest(args.plan), 'freeze_sha256': digest(args.freeze),
               'records_sha256': digest(args.output/'cases.jsonl'), **summarize(rows, plan['mode'])}
    (args.output/'summary.json').write_text(json.dumps(json_value(summary), indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True, choices=ENGINES)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--freeze', required=True, type=Path)
    parser.add_argument('--private-inputs', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--private-log-dir', type=Path)
    parser.add_argument('--worker-slot', type=int)
    parser.add_argument('--worker-result', type=Path)
    args = parser.parse_args(argv)
    plan = validate_plan(json.loads(args.plan.read_text(encoding='utf-8')))
    freeze = verify_freeze(args.freeze, args.plan, args.private_inputs)
    verify_environment(freeze, args.engine)
    if any(item['kind'] == 'image' for item in plan['inputs']) and args.private_inputs is None:
        raise ValueError('Image inputs require the frozen private manifest.')
    if args.worker_slot is not None:
        slots = planned_slots(plan, args.engine)
        if args.worker_result is None or not 0 <= args.worker_slot < len(slots):
            raise ValueError('Invalid worker slot.')
        worker(args, plan, slots[args.worker_slot])
    else:
        if args.output is None or args.private_log_dir is None:
            raise ValueError('Public output and private log directories are required.')
        run_controller(args, plan, freeze)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not echo exception text, argparse input filenames, or native traces.
        print(json.dumps({'completed': False, 'reason_code': 'benchmark_preflight_failed',
                          'exception_type': type(error).__name__}), flush=True)
        raise SystemExit(2)
