"""Run a frozen, paired native integration study; retain every attempted audit.

Only study-local public identifiers and derived evidence are written. Native
warnings should be redirected to a private log by the caller. No clinical image
is copied into the output. Timing is descriptive wall-clock time on this host.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import SimpleITK as sitk
from radaccord.evidence import config_digest, feature_digest, json_value
from radaccord.legacy import physical_contracts


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pair_synthetic(seed):
    source = physical_contracts.phantom(seed)
    # Input preparation only; no candidate operation is computed here.
    image = sitk.GetImageFromArray(source.data.transpose(2, 1, 0).copy())
    mask = sitk.GetImageFromArray(source.mask.transpose(2, 1, 0).astype('uint8'))
    affine = np.diag([-1., -1., 1., 1.]) @ source.affine
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    image.SetSpacing(tuple(spacing)); image.SetOrigin(tuple(affine[:3, 3]))
    image.SetDirection(tuple((affine[:3, :3]/spacing).ravel()))
    mask.CopyInformation(image)
    return image, mask


def mirp_objects(pair, modality, identity):
    from mirp._images.generic_image import GenericImage
    from mirp._masks.base_mask import BaseMask
    image, mask = pair
    if any(getattr(image, method)() != getattr(mask, method)()
           for method in ('GetSize', 'GetSpacing', 'GetOrigin', 'GetDirection')):
        raise ValueError('Converting distinct native source grids is outside this study.')
    reverse = np.eye(3)[::-1]
    # In-memory native MIRP objects avoid paths in native table metadata.
    geometry = dict(image_origin=tuple(reverse @ np.asarray(image.GetOrigin())),
                    image_orientation=reverse @ np.asarray(image.GetDirection()).reshape(3, 3) @ reverse,
                    image_spacing=tuple(image.GetSpacing()[::-1]),
                    image_dimensions=tuple(image.GetSize()[::-1]),
                    image_modality=modality, sample_name=identity)
    values = sitk.GetArrayFromImage(image)
    membership = sitk.GetArrayFromImage(mask) == 1
    return (GenericImage(image_data=values.copy(), **geometry),
            BaseMask(roi_name='selected_label_1', image_data=membership, **geometry))


def parameters(engine, operation):
    if engine == 'pyradiomics':
        result = {'setting': {'binWidth': 25.}, 'imageType': {'Original': {}}}
        if operation != 'identity':
            result['setting']['resampledPixelSpacing'] = [1.3]*3
            if operation == 'linear_1p3':
                result['setting']['interpolator'] = 'sitkLinear'
        return result
    result = {'base_feature_families': ['all'],
              'base_discretisation_method': 'fixed_bin_number', 'base_discretisation_n_bins': 32}
    if operation != 'identity':
        result['new_spacing'] = 1.3
        if operation == 'linear_1p3':
            result['spline_order'] = 1
    return result


def run_pair(engine, pair, modality, identity, config):
    if engine == 'pyradiomics':
        from radiomics.featureextractor import RadiomicsFeatureExtractor
        from radaccord.pyradiomics import audit_pyradiomics
        start = time.perf_counter()
        baseline = RadiomicsFeatureExtractor(deepcopy(config)).execute(*pair, label=1)
        baseline_seconds = time.perf_counter()-start
        result = audit_pyradiomics(*pair, config=config, label=1)
        native = {k: v for k, v in baseline.items() if not k.startswith('diagnostics_')}
        observed = result['features']
        same_keys = native.keys() == observed.keys()
        equal = same_keys and all(np.array_equal(np.asarray(native[k]), np.asarray(observed[k]), equal_nan=True)
                                  for k in native)
        payload = {'baseline_values': feature_digest(native), 'observed_values': feature_digest(observed)}
    else:
        import pandas as pd
        from mirp import extract_features_and_images
        from radaccord.mirp import audit_mirp
        image, mask = mirp_objects(pair, modality, identity)
        start = time.perf_counter()
        baseline = extract_features_and_images(image=deepcopy(image), mask=deepcopy(mask), **config,
            export_features=True, export_images=True, write_features=False, write_images=False,
            image_export_format='native')[0][0]
        baseline_seconds = time.perf_counter()-start
        result = audit_mirp(image, mask, config=config)
        observed = result['features']
        try:
            pd.testing.assert_frame_equal(baseline, observed, check_exact=True)
            equal = True
        except AssertionError:
            equal = False
        numeric = baseline.select_dtypes(include=np.number)
        numeric_observed = observed.select_dtypes(include=np.number)
        payload = {'baseline_values': feature_digest({str(c): numeric[c].iloc[0] for c in numeric}),
                   'observed_values': feature_digest({str(c): numeric_observed[c].iloc[0] for c in numeric_observed}),
                   'values_scope': 'All native numeric columns, including numeric metadata; full tables compared exactly.'}
    return {'native_values_unchanged': bool(equal), 'baseline_seconds': baseline_seconds,
            'audited_seconds': result['report']['elapsed_seconds'], **payload,
            'report': result['report']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['pyradiomics', 'mirp'], required=True)
    parser.add_argument('--plan', type=Path, default=ROOT/'protocol/native_study_plan.json')
    parser.add_argument('--freeze', type=Path, default=ROOT/'protocol/native_freeze.json')
    parser.add_argument('--dataset-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--development', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('The output directory must be new.')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if not args.development:
        freeze = json.loads(args.freeze.read_text(encoding='utf-8'))
        for relative, expected in freeze['files'].items():
            if digest(ROOT/relative) != expected:
                raise SystemExit('A frozen implementation or protocol file has changed.')
        if digest(args.plan) != freeze['files']['protocol/native_study_plan.json']:
            raise SystemExit('The selected plan does not match the frozen native plan.')
    args.output.mkdir(parents=True)
    records = []
    with (args.output/'cases.jsonl').open('w', encoding='utf-8', newline='\n') as output:
        for item in plan['inputs']:
            operations = item['operations']
            for operation in operations:
                record = {'input_id': item['id'], 'source_kind': item['kind'], 'modality': item['modality'],
                          'engine': args.engine, 'operation': operation, 'config': parameters(args.engine, operation)}
                start = time.perf_counter()
                try:
                    if item['kind'] == 'synthetic':
                        pair = pair_synthetic(item['seed'])
                    else:
                        if args.dataset_root is None:
                            raise ValueError('A dataset root is required.')
                        paths = [args.dataset_root/item['dataset']/relative for relative in (item['image'], item['mask'])]
                        if [digest(path) for path in paths] != [item['image_sha256'], item['mask_sha256']]:
                            raise ValueError('The declared input digest differs.')
                        pair = tuple(sitk.ReadImage(str(path)) for path in paths)
                    record.update(run_pair(args.engine, pair, item['modality'], item['id'], record['config']))
                    record['completed'] = True
                except Exception as error:
                    # All failures retained. Exception text may contain private paths.
                    record.update(completed=False, exception_type=type(error).__name__,
                                  reason_code='native_study_attempt_failed')
                record['total_seconds'] = time.perf_counter()-start
                record = json_value(record)
                records.append(record)
                output.write(json.dumps(record, sort_keys=True, allow_nan=False)+'\n'); output.flush()
                print(f"{args.engine}: {len(records)} attempts retained", flush=True)
    summary = {'schema_version': 'native-study-1', 'engine': args.engine,
               'engine_version': version(args.engine), 'numpy_version': np.__version__,
               'development': args.development, 'finished_utc': datetime.now(timezone.utc).isoformat(),
               'planned': sum(len(item['operations']) for item in plan['inputs']),
               'attempted': len(records), 'completed': sum(record['completed'] for record in records),
               'unchanged': sum(record.get('native_values_unchanged', False) for record in records),
               'plan_sha256': digest(args.plan), 'records_sha256': digest(args.output/'cases.jsonl')}
    (args.output/'run_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
