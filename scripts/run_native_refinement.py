"""Run every amended native pair in its own bounded subprocess.

This is a calibration-informed reevaluation, not external validation. Native
stdout/stderr and temporary worker records go only to the private log directory.
The public ledger retains all planned slots, including timeouts and crashes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import time

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'):
    os.environ[variable] = '1'
from run_native_study import ROOT, digest, pair_synthetic, run_pair, parameters, json_value, sitk
sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(1)


def configuration(engine, operation, modality):
    result = parameters(engine, operation)
    if engine == 'pyradiomics' and modality.lower() != 'ct':
        result['setting'].pop('binWidth', None)
        result['setting']['binCount'] = 32
    return result


def verify_freeze(path):
    freeze = json.loads(path.read_text(encoding='utf-8'))
    for relative, expected in freeze['files'].items():
        if digest(ROOT/relative) != expected:
            raise ValueError('A frozen refinement file has changed: '+relative)
    if digest(ROOT/'data/RadAccord-native-calibration-1.zip') != freeze['calibration_archive_sha256']:
        raise ValueError('The retained calibration archive differs.')
    return freeze


def worker(args, item, operation):
    record = {'input_id': item['id'], 'source_kind': item['kind'], 'modality': item['modality'],
              'engine': args.engine, 'operation': operation,
              'config': configuration(args.engine, operation, item['modality'])}
    start = time.perf_counter()
    try:
        if item['kind'] == 'synthetic':
            pair = pair_synthetic(item['seed'])
        else:
            paths = [args.dataset_root/item['dataset']/relative for relative in (item['image'], item['mask'])]
            if [digest(path) for path in paths] != [item['image_sha256'], item['mask_sha256']]:
                raise ValueError('The declared input digest differs.')
            pair = tuple(sitk.ReadImage(str(path)) for path in paths)
        record.update(run_pair(args.engine, pair, item['modality'], item['id'], record['config']))
        record['completed'] = True
    except Exception as error:
        record.update(completed=False, exception_type=type(error).__name__,
                      reason_code='native_refinement_attempt_failed')
    record['total_seconds'] = time.perf_counter()-start
    temporary = args.worker_result.with_suffix('.tmp')
    temporary.write_text(json.dumps(json_value(record), sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(args.worker_result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['pyradiomics', 'mirp'], required=True)
    parser.add_argument('--plan', type=Path, default=ROOT/'protocol/native_study_plan.json')
    parser.add_argument('--freeze', type=Path, default=ROOT/'protocol/native_refinement_freeze.json')
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--private-log-dir', type=Path)
    parser.add_argument('--worker-slot', type=int)
    parser.add_argument('--worker-result', type=Path)
    args = parser.parse_args()
    freeze = verify_freeze(args.freeze)
    if digest(args.plan) != freeze['files']['protocol/native_study_plan.json']:
        parser.error('Plan differs from the frozen plan.')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    slots = [(item, operation) for item in plan['inputs'] for operation in item['operations']]
    if args.worker_slot is not None:
        worker(args, *slots[args.worker_slot])
        return
    if not args.output or not args.private_log_dir or args.output.exists() or args.private_log_dir.exists():
        parser.error('Supply new public output and private log directories.')
    args.output.mkdir(parents=True)
    args.private_log_dir.mkdir(parents=True)
    records = []
    started = datetime.now(timezone.utc).isoformat()
    with (args.output/'cases.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        for slot, (item, operation) in enumerate(slots):
            record = {'input_id': item['id'], 'source_kind': item['kind'], 'modality': item['modality'],
                      'engine': args.engine, 'operation': operation,
                      'config': configuration(args.engine, operation, item['modality'])}
            result_path = args.private_log_dir/f'{slot+1:03d}.json'
            command = [sys.executable, str(Path(__file__).resolve()), '--engine', args.engine,
                       '--plan', str(args.plan), '--freeze', str(args.freeze), '--dataset-root', str(args.dataset_root),
                       '--worker-slot', str(slot), '--worker-result', str(result_path)]
            start = time.perf_counter()
            with (args.private_log_dir/f'{slot+1:03d}.log').open('wb') as log:
                try:
                    process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                             timeout=freeze['timeout_seconds_per_pair'], check=False)
                    if process.returncode == 0 and result_path.is_file():
                        completed = json.loads(result_path.read_text(encoding='utf-8'))
                        if any(completed.get(k) != v for k, v in record.items()):
                            raise ValueError('Worker identity differs from its planned slot.')
                        record = completed
                    else:
                        record.update(completed=False, reason_code='native_worker_incomplete',
                                      worker_exit_code=process.returncode)
                except subprocess.TimeoutExpired:
                    record.update(completed=False, reason_code='native_worker_timeout')
                except (OSError, ValueError):
                    record.update(completed=False, reason_code='native_worker_record_unavailable')
            record['total_seconds'] = time.perf_counter()-start
            record = json_value(record)
            records.append(record)
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False)+'\n')
            stream.flush()
            print(f'{args.engine}: {slot+1}/{len(slots)} planned slots retained', flush=True)
    summary = {'schema_version': 'native-study-1', 'evaluation_phase': 'calibration_informed_reevaluation',
               'engine': args.engine, 'engine_version': version(args.engine),
               'numpy_version': version('numpy'), 'development': False,
               'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
               'planned': len(slots), 'attempted': len(records),
               'completed': sum(row['completed'] for row in records),
               'unchanged': sum(row.get('native_values_unchanged', False) for row in records),
               'plan_sha256': digest(args.plan), 'freeze_sha256': digest(args.freeze),
               'records_sha256': digest(args.output/'cases.jsonl')}
    (args.output/'run_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
