"""Evaluate declared spatial preprocessing using unmodified SimpleITK operators.

Development example (no clinical data are opened):
  python scripts/run_sampling_study.py --synthetic --output results/development
Clinical evaluation, only after the study freeze:
  python scripts/run_sampling_study.py --dataset-root Task04_Hippocampus \
    --dataset-root Task09_Spleen --output results/clinical

The main battery observes materialized SimpleITK image/mask objects. Every
development case, and cases from the first three sorted volume IDs per clinical
dataset, additionally undergo a float64 NIfTI roundtrip. Public reports contain
dataset-relative filenames and hashes, never dataset-root paths. Native radiomic
engines are not executed: reported drift is occupied voxel volume, mean and
population variance. Correct resampling does not imply feature invariance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

import nibabel as nib
import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'software'))
from physical_contracts import Frame, phantom, read_frame, transport_witness
from sampling_contracts import sampling_witness
from radaccord_sampling import _read_candidate, file_sha256 as digest

POSITION_ATOL_MM = 1e-4
INTENSITY_ATOL = 1e-4
INDEX_BOUNDARY_ATOL = 1e-9
MARGIN = 6
RAS_LPS = np.diag([-1., -1., 1.])
CONTROL_NAMES = ('crop_roi_margin', 'identity', 'pad', 'orient',
                 'isotropic_0p8mm', 'isotropic_1mm', 'isotropic_2mm')
MUTATION_NAMES = ('stale_crop_origin', 'shared_origin_shift',
                  'half_voxel_sampling_displacement', 'wrong_image_kernel',
                  'linear_mask_threshold', 'premature_integer_storage')
CASE_ORDER = ('crop_roi_margin', 'stale_crop_origin', 'identity', 'pad', 'orient',
              'isotropic_0p8mm', 'isotropic_1mm', 'isotropic_2mm', 'shared_origin_shift',
              'half_voxel_sampling_displacement', 'wrong_image_kernel',
              'linear_mask_threshold', 'premature_integer_storage', 'roi_truncation')
CASE_KINDS = {**dict.fromkeys(CONTROL_NAMES, 'valid_control'),
              **dict.fromkeys(MUTATION_NAMES, 'own_wrapper_mutation'),
              'roi_truncation': 'support_policy_control'}


def emit(handle, value):
    handle.write(json.dumps(value, allow_nan=False, sort_keys=True) + '\n')
    handle.flush()


def affine_of(image):
    affine = np.eye(4)
    affine[:3, :3] = RAS_LPS @ np.asarray(image.GetDirection()).reshape(3, 3) @ np.diag(image.GetSpacing())
    affine[:3, 3] = RAS_LPS @ np.asarray(image.GetOrigin())
    return affine


def corner_error(left, right, shape):
    corners = np.array(list(product(*[(0, n - 1) for n in shape])), dtype=float).T
    differences = (left[:3, :3] - right[:3, :3]) @ corners + (left[:3, 3] - right[:3, 3])[:, None]
    return float(np.linalg.norm(differences, axis=0).max())


def to_sitk(frame):
    """Input preparation only; candidate operators run in SimpleITK below."""
    pair = (sitk.GetImageFromArray(np.ascontiguousarray(frame.data.transpose(2, 1, 0), dtype=np.float64)),
            sitk.GetImageFromArray(np.ascontiguousarray((frame.mask == frame.label).transpose(2, 1, 0), dtype=np.uint8)))
    spacing = np.linalg.norm(frame.affine[:3, :3], axis=0)
    direction = RAS_LPS @ (frame.affine[:3, :3] / spacing)
    for image in pair:
        image.SetSpacing(spacing.tolist())
        image.SetDirection(direction.ravel().tolist())
        image.SetOrigin((RAS_LPS @ frame.affine[:3, 3]).tolist())
    return pair


def from_sitk(pair):
    image, mask = pair
    data = sitk.GetArrayFromImage(image).transpose(2, 1, 0)
    labels = sitk.GetArrayFromImage(mask).transpose(2, 1, 0)
    image_affine, mask_affine = affine_of(image), affine_of(mask)
    same_shape = image.GetSize() == mask.GetSize()
    error = corner_error(image_affine, mask_affine, image.GetSize()) if same_shape else None
    checks = {'same_shape': same_shape, 'same_geometry': error is not None and error <= POSITION_ATOL_MM,
              'finite_image': bool(np.all(np.isfinite(data))),
              'finite_mask': bool(np.all(np.isfinite(labels))), 'nonempty_roi': bool(np.any(labels == 1))}
    paired = {'status': 'satisfied' if all(checks.values()) else 'violated', 'checks': checks,
              'max_image_mask_corner_error_mm': error}
    return Frame(data, labels, image_affine), paired


def declaration(index_map, shape, interpolation='nearest'):
    return {'index_map': np.asarray(index_map).tolist(), 'candidate_shape': [int(n) for n in shape],
            'world_map': np.eye(4).tolist(), 'interpolation': interpolation, 'outside_value': 0.,
            'position_atol_mm': POSITION_ATOL_MM, 'intensity_atol': INTENSITY_ATOL,
            'index_boundary_atol': INDEX_BOUNDARY_ATOL,
            'intensity_gain': 1., 'intensity_offset': 0., 'mask_outside': 0}


def source_geometry(source, candidate, spec):
    expected = np.asarray(spec['world_map']) @ source.affine @ np.asarray(spec['index_map'])
    shape_ok = tuple(spec['candidate_shape']) == candidate.data.shape
    error = corner_error(expected, candidate.affine, candidate.data.shape)
    checks = {'declared_shape': shape_ok, 'declared_physical_geometry': error <= POSITION_ATOL_MM}
    return {'status': 'satisfied' if all(checks.values()) else 'violated',
            'checks': checks, 'max_corner_error_mm': error}


def legacy(source, candidate, spec):
    """Gate the historical full-grid domain before calling its unchanged witness."""
    b = np.asarray(spec['index_map'])
    p = b[:3, :3]
    integral = (np.all(np.isin(p, [-1., 0., 1.])) and np.all(np.abs(p).sum(0) == 1)
                and np.all(np.abs(p).sum(1) == 1) and np.all(b[:3, 3] == np.rint(b[:3, 3])))
    if integral:
        perm = np.argmax(np.abs(p), axis=0)
        expected_shape = tuple(source.data.shape[k] for k in perm)
        corners = np.array(list(product(*[(0, n - 1) for n in spec['candidate_shape']])), float).T
        mapped = p @ corners + b[:3, 3, None]
        integral = (tuple(spec['candidate_shape']) == expected_shape
                    and np.array_equal(mapped.min(1), [0, 0, 0])
                    and np.array_equal(mapped.max(1), np.asarray(source.data.shape) - 1))
    if not integral:
        return {'domain_status': 'outside_original_full_grid_domain', 'status': 'not_applicable'}
    return {'domain_status': 'supported', **transport_witness(source, candidate, spec)}


def moments(frame):
    values = np.asarray(frame.data[frame.mask == frame.label], dtype=np.float64)
    if not values.size:
        return None
    return {'roi_voxels': int(values.size),
            'occupied_volume_mm3': float(values.size * abs(np.linalg.det(frame.affine[:3, :3]))),
            'mean': float(values.mean()), 'population_variance': float(values.var())}


def difference(candidate, reference):
    if candidate is None or reference is None:
        return None
    return {name: candidate[name] - reference[name] for name in reference}


def activity(candidate, intended):
    changed_image = int(np.count_nonzero(candidate.data != intended.data))
    intensity_error = float(np.max(np.abs(candidate.data - intended.data)))
    changed_mask = int(np.count_nonzero((candidate.mask == 1) != (intended.mask == 1)))
    header_error = corner_error(candidate.affine, intended.affine, candidate.data.shape)
    return {'active': bool(intensity_error > INTENSITY_ATOL or changed_mask or header_error > POSITION_ATOL_MM),
            'definition': 'Decoded intensities or geometry differ beyond declared absolute tolerances, or any selected ROI membership differs, relative to the correct operation. Exact numerical changes are also retained.',
            'any_exact_decoded_change': bool(changed_image or changed_mask or header_error != 0.),
            'changed_intensity_voxels': changed_image, 'changed_roi_voxels': changed_mask,
            'max_changed_intensity': intensity_error,
            'max_changed_header_displacement_mm': header_error}


def save_pair(frame, directory, prefix):
    paths = []
    for name, data in (('image', frame.data.astype(np.float64)), ('mask', frame.mask.astype(np.int16))):
        path = directory / (prefix + '_' + name + '.nii.gz')
        image = nib.Nifti1Image(data, frame.affine)
        image.header.set_xyzt_units('mm')
        image.set_qform(frame.affine, code=1)
        image.set_sform(frame.affine, code=1)
        nib.save(image, path)
        paths.append(path)
    return paths


def roundtrip(source, candidate, spec):
    started = perf_counter()
    try:
        with TemporaryDirectory(prefix='radaccord_roundtrip_') as folder:
            directory = Path(folder)
            source_paths = save_pair(source, directory, 'source')
            candidate_paths = save_pair(candidate, directory, 'candidate')
            loaded_source, source_pair = read_frame(*source_paths)
            loaded_candidate, candidate_pair = _read_candidate(candidate_paths[0], candidate_paths[1], 1)
            io_seconds = perf_counter() - started
            check_start = perf_counter()
            result = sampling_witness(loaded_source, loaded_candidate, spec)
            return {'boundary': 'saved_NIfTI_float64_image_int16_union_ROI',
                    'status': result['status'] if all(source_pair.values()) and all(candidate_pair.values()) else 'violated',
                    'source_paired': source_pair, 'candidate_paired': candidate_pair,
                    'sampling': result, 'io_seconds': io_seconds,
                    'witness_seconds': perf_counter() - check_start}
    except (ValueError, OSError, RuntimeError) as error:
        return {'boundary': 'saved_NIfTI_float64_image_int16_union_ROI', 'status': 'not_available',
                'error_type': type(error).__name__,
                'reason': 'NIfTI serialization or loading did not meet the declared input domain.',
                'elapsed_seconds': perf_counter() - started}


def resample(pair, shape, spacing, image_kernel=sitk.sitkLinear, displacement=None, linear_mask=False):
    """Evaluated native operator; no oracle sampling or B construction is called."""
    outputs = []
    for index, original in enumerate(pair):
        operator = sitk.ResampleImageFilter()
        operator.SetSize([int(n) for n in shape])
        operator.SetOutputSpacing([float(x) for x in spacing])
        operator.SetOutputOrigin(pair[0].GetOrigin())
        operator.SetOutputDirection(pair[0].GetDirection())
        operator.SetDefaultPixelValue(0.)
        operator.SetInterpolator(image_kernel if index == 0 else (sitk.sitkLinear if linear_mask else sitk.sitkNearestNeighbor))
        operator.SetOutputPixelType(sitk.sitkFloat64 if index == 0 or linear_mask else sitk.sitkUInt8)
        operator.SetTransform(sitk.Transform(3, sitk.sitkIdentity) if displacement is None
                              else sitk.TranslationTransform(3, [float(x) for x in displacement]))
        image = operator.Execute(sitk.Cast(original, sitk.sitkFloat64) if linear_mask and index == 1 else original)
        if index == 1 and linear_mask:
            image = sitk.Cast(image >= 0.5, sitk.sitkUInt8)
        outputs.append(image)
    return tuple(outputs)


def crop_plan(frame, margin):
    indices = np.argwhere(frame.mask == frame.label)
    start = np.maximum(indices.min(0) - margin, 0)
    stop = np.minimum(indices.max(0) + margin + 1, frame.data.shape)
    b = np.eye(4)
    b[:3, 3] = start
    return start.tolist(), (stop - start).tolist(), declaration(b, stop - start)


def run_volume(source, dataset, volume_id, roundtrip_selected, case_file, checkpoint_file, checkpoint_selected,
               native_output=None, native_manifest=None, progress=None):
    rows = []
    if progress is None:
        progress = {'completed': {}, 'current_case': None}

    def begin(name):
        progress['current_case'] = name
        progress['operation_phase'] = 'native_producer_or_its_declared_plan'

    def record(name, kind, basis, pair, spec, seconds, intended=None, source_scope='working_ROI_crop'):
        progress['current_case'] = name
        progress['operation_phase'] = 'comparison_or_record_output'
        observed, paired = from_sitk(pair)
        row = {'dataset': dataset, 'volume_id': volume_id, 'case': name, 'kind': kind,
               'source_scope': source_scope, 'boundary': 'materialized_SimpleITK_image_and_mask',
               'declaration': spec, 'source_shape': list(basis.data.shape), 'candidate_shape': list(observed.data.shape),
               'producer_seconds': seconds, 'paired_QA': paired,
               'source_aware_geometry': source_geometry(basis, observed, spec),
               'legacy_full_grid': legacy(basis, observed, spec)}
        check_start = perf_counter()
        try:
            row['sampling'] = sampling_witness(basis, observed, spec)
        except (ValueError, ArithmeticError) as error:
            row['sampling'] = {'status': 'not_available', 'error_type': type(error).__name__,
                               'reason': 'Source or observed state falls outside the sampling-witness input domain.'}
        row['witness_seconds'] = perf_counter() - check_start
        reference = observed if intended is None else intended
        row['mutation'] = activity(observed, reference) if kind == 'own_wrapper_mutation' else None
        before, after, correct = moments(basis), moments(observed), moments(reference)
        row['voxel_statistics'] = {'source': before, 'candidate': after, 'correct_operation': correct,
                                   'candidate_minus_source': difference(after, before),
                                   'candidate_minus_correct_operation': difference(after, correct),
                                   'scope': 'Direct occupied voxel volume and ROI intensity summaries; no native feature extraction.'}
        row['file_roundtrip'] = roundtrip(basis, observed, spec) if roundtrip_selected else {
            'status': 'not_selected', 'reason': 'Prespecified file-I/O subset; main record observes in-memory native outputs.'}
        native_roles = {'crop_roi_margin': 'source_working_crop', 'isotropic_0p8mm': 'isotropic_0p8mm',
                        'isotropic_1mm': 'isotropic_1mm',
                        'isotropic_2mm': 'isotropic_2mm', 'wrong_image_kernel': 'wrong_image_kernel'}
        if native_output is not None and name in native_roles:
            directory = native_output / dataset / volume_id
            directory.mkdir(parents=True, exist_ok=True)
            role = native_roles[name]
            paths = save_pair(observed, directory, role)
            emit(native_manifest, {'dataset': dataset, 'volume_id': volume_id, 'role': role,
                 'case': name, 'declaration': spec, 'sampling_status': row['sampling']['status'],
                 'shape': list(observed.data.shape),
                 'files': [{'role': kind, 'path': path.relative_to(native_output).as_posix(), 'sha256': digest(path)}
                           for kind, path in zip(('image', 'mask'), paths)],
                 'scope': 'Prespecified first-three-volume subset; saved input pairs only. No native features have been extracted by this harness.'})
        emit(case_file, row)
        rows.append(row)
        progress['completed'][name] = row['sampling']['status']
        progress['current_case'] = None
        return observed

    # This declaration is fixed from retained source ROI bounds before cropping.
    begin('crop_roi_margin')
    start, size, crop_spec = crop_plan(source, MARGIN)
    conversion_start = perf_counter()
    full_pair = to_sitk(source)
    input_conversion_seconds = perf_counter() - conversion_start
    started = perf_counter()
    working_pair = tuple(sitk.RegionOfInterest(image, size, start) for image in full_pair)
    producer_seconds = perf_counter() - started
    working = record('crop_roi_margin', 'valid_control', source, working_pair, crop_spec,
                     producer_seconds, source_scope='full_retained_volume')
    begin('stale_crop_origin')
    started = perf_counter()
    stale_pair = tuple(sitk.Image(image) for image in working_pair)
    for image in stale_pair:
        image.SetOrigin(full_pair[0].GetOrigin())
    record('stale_crop_origin', 'own_wrapper_mutation', source, stale_pair, crop_spec,
           perf_counter() - started, intended=working, source_scope='full_retained_volume')
    del full_pair, stale_pair

    begin('identity')
    identity_spec = declaration(np.eye(4), working.data.shape)
    record('identity', 'valid_control', working, working_pair, identity_spec, 0.)

    begin('pad')
    lower, upper = [3, 4, 2], [2, 1, 3]
    b = np.eye(4)
    b[:3, 3] = -np.asarray(lower)
    pad_spec = declaration(b, np.asarray(working.data.shape) + lower + np.asarray(upper))
    started = perf_counter()
    padded = tuple(sitk.ConstantPad(image, lower, upper, 0) for image in working_pair)
    record('pad', 'valid_control', working, padded, pad_spec, perf_counter() - started)
    del padded

    begin('orient')
    perm, flips = [2, 0, 1], [True, False, True]
    b = np.zeros((4, 4))
    b[3, 3] = 1.
    for axis, old in enumerate(perm):
        b[old, axis] = -1. if flips[axis] else 1.
        if flips[axis]:
            b[old, 3] = working.data.shape[old] - 1
    orient_spec = declaration(b, [working.data.shape[i] for i in perm])
    started = perf_counter()
    oriented = tuple(sitk.Flip(sitk.PermuteAxes(image, perm), flips, False) for image in working_pair)
    record('orient', 'valid_control', working, oriented, orient_spec, perf_counter() - started)
    del oriented

    target_0p8mm = None
    for millimetres, name in ((0.8, 'isotropic_0p8mm'), (1., 'isotropic_1mm'), (2., 'isotropic_2mm')):
        begin(name)
        # Endpoint-centre extent determines size. This is NOT a claim of identical
        # source/destination voxel support; the witness reports ROI-centre coverage.
        ratio = millimetres / np.asarray(working_pair[0].GetSpacing())
        shape = np.floor((np.asarray(working.data.shape) - 1) / ratio).astype(int) + 1
        b = np.eye(4)
        b[:3, :3] = np.diag(ratio)
        spec = declaration(b, shape, 'linear')
        started = perf_counter()
        pair = resample(working_pair, shape, [millimetres] * 3)
        candidate = record(name, 'valid_control', working, pair, spec,
                           perf_counter() - started)
        if millimetres == 0.8:
            target_0p8mm = (pair, candidate, spec, shape)
    del pair, candidate

    begin('shared_origin_shift')
    started = perf_counter()
    shifted = tuple(sitk.Image(image) for image in working_pair)
    for image in shifted:
        # +11 mm in RAS x, with image/mask remaining paired.
        origin = np.asarray(image.GetOrigin()) + np.array([-11., 0., 0.])
        image.SetOrigin(origin.tolist())
    record('shared_origin_shift', 'own_wrapper_mutation', working, shifted, identity_spec,
           perf_counter() - started, intended=working)
    del shifted

    fine_pair, fine, fine_spec, fine_shape = target_0p8mm
    for name in MUTATION_NAMES[2:]:
        begin(name)
        started = perf_counter()
        if name == 'half_voxel_sampling_displacement':
            direction = np.asarray(working_pair[0].GetDirection()).reshape(3, 3)
            shift = direction[:, 0] * working_pair[0].GetSpacing()[0] * 0.5
            mutant = resample(working_pair, fine_shape, [0.8] * 3, displacement=shift)
        elif name == 'wrong_image_kernel':
            mutant = resample(working_pair, fine_shape, [0.8] * 3, image_kernel=sitk.sitkNearestNeighbor)
        elif name == 'linear_mask_threshold':
            mutant = resample(working_pair, fine_shape, [0.8] * 3, linear_mask=True)
        else:
            # Own premature output storage, AFTER interpolation and BEFORE any
            # feature extraction. Int32 truncation is not a native-library fault.
            if np.min(fine.data) < np.iinfo(np.int32).min or np.max(fine.data) > np.iinfo(np.int32).max:
                raise ValueError('The integer-storage mutation exceeds its declared Int32 range.')
            mutant = (sitk.Cast(sitk.Cast(fine_pair[0], sitk.sitkInt32), sitk.sitkFloat64), fine_pair[1])
        record(name, 'own_wrapper_mutation', working, mutant, fine_spec,
               perf_counter() - started, intended=fine)
        del mutant

    # Deliberately lose some ROI while executing the declared crop correctly.
    begin('roi_truncation')
    start, size, _ = crop_plan(working, 0)
    size[0] = max(1, size[0] // 2)
    b = np.eye(4)
    b[:3, 3] = start
    truncated_spec = declaration(b, size)
    started = perf_counter()
    truncated = tuple(sitk.RegionOfInterest(image, size, start) for image in working_pair)
    record('roi_truncation', 'support_policy_control', working, truncated, truncated_spec,
           perf_counter() - started)

    if checkpoint_selected:
        progress['operation_phase'] = 'constructed_checkpoint_demonstration'
        for name, shifted in (('identity_checkpoints', False), ('compensated_intermediate_geometry', True)):
            intermediate = working
            if shifted:
                affine = working.affine.copy()
                affine[:3, 3] += [11., 0., 0.]
                intermediate = replace(working, affine=affine)
            stages = []
            for stage_name, frame in (('intermediate', intermediate), ('endpoint', working)):
                started = perf_counter()
                stages.append({'stage': stage_name, 'sampling': sampling_witness(working, frame, identity_spec),
                               'witness_seconds': perf_counter() - started})
            first = next((stage['stage'] for stage in stages if stage['sampling']['status'] != 'satisfied'), None)
            emit(checkpoint_file, {'dataset': dataset, 'volume_id': volume_id, 'case': name,
                 'kind': 'constructed_checkpoint_demonstration', 'stages': stages,
                 'first_observed_failure': first, 'endpoint_only_status': stages[-1]['sampling']['status'],
                 'scope': 'Supplied image states only; no unobserved internal extractor state is inferred.'})
    return rows, input_conversion_seconds


def load_clinical(root, entry):
    paths = [(root / entry[key]).resolve() for key in ('image', 'label')]
    if any(not path.is_relative_to(root.resolve()) for path in paths):
        raise ValueError('Dataset metadata resolves outside its declared root.')
    image, mask = (nib.load(path) for path in paths)
    for item in (image, mask):
        if item.ndim != 3 or item.header.get_xyzt_units()[0] != 'mm':
            raise ValueError('Clinical input must be 3D with explicit millimetre units.')
        q, qc = item.get_qform(coded=True)
        s, sc = item.get_sform(coded=True)
        if qc and sc and not np.allclose(q, s, atol=POSITION_ATOL_MM, rtol=0):
            raise ValueError('Conflicting coded qform and sform.')
    if image.shape != mask.shape or corner_error(image.affine, mask.affine, image.shape) > POSITION_ATOL_MM:
        raise ValueError('Source image and annotation geometry disagree.')
    labels = np.asanyarray(mask.dataobj)
    if not np.all(np.isfinite(labels)) or not np.all(labels >= 0) or not np.all(labels == np.floor(labels)):
        raise ValueError('Source labels must be finite nonnegative integers.')
    frame = Frame(image.get_fdata(dtype=np.float64), (labels > 0).astype(np.int16), image.affine).validate()
    provenance = {'source_files': [{'role': key, 'path': path.relative_to(root.resolve()).as_posix(),
                                    'sha256': digest(path)} for key, path in zip(('image', 'annotation'), paths)],
                  'original_labels': [int(x) for x in np.unique(labels)],
                  'roi_preparation': 'Union of all original annotation labels > 0, stored as selected label 1.',
                  'unit': 'released_volume; no patient linkage assumed'}
    return frame, provenance


def volume_id(entry):
    return Path(entry['image']).name.removesuffix('.nii.gz').removesuffix('.nii')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--seed-start', type=int, default=30000)
    parser.add_argument('--seed-stop', type=int, default=30012, help='Exclusive endpoint; development is 30000:30012.')
    parser.add_argument('--dataset-root', type=Path, action='append', default=[])
    parser.add_argument('--native-input-output', type=Path,
                        help='Optional PRIVATE directory outside this software tree; saves five roles for first three clinical IDs.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.synthetic == bool(args.dataset_root):
        parser.error('Choose --synthetic OR one or more --dataset-root values.')
    if args.synthetic and args.seed_stop <= args.seed_start:
        parser.error('seed-stop must exceed seed-start.')
    if args.native_input_output is not None and args.native_input_output.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Native input images must remain outside the software tree.')
    args.output.mkdir(parents=True, exist_ok=True)
    targets = [args.output / name for name in ('cases.jsonl', 'volumes.jsonl', 'checkpoint_demo.jsonl', 'run_summary.json')]
    if any(path.exists() for path in targets):
        parser.error('This output already contains study records; select a new directory to preserve them.')
    native_manifest = None
    if args.native_input_output is not None:
        if args.synthetic:
            parser.error('--native-input-output is reserved for the predefined clinical subset.')
        args.native_input_output.mkdir(parents=True, exist_ok=True)
        native_manifest = args.native_input_output / 'manifest.jsonl'
        if native_manifest.exists():
            parser.error('The native input manifest already exists; choose a new private directory.')

    groups = []
    if args.synthetic:
        entries = [{'seed': seed, 'id': f'synthetic_{seed}'} for seed in range(args.seed_start, args.seed_stop)]
        groups.append(('synthetic', None, entries))
    else:
        for root in args.dataset_root:
            metadata = json.loads((root / 'dataset.json').read_text(encoding='utf-8'))
            entries = sorted(metadata['training'], key=volume_id)
            if len({volume_id(entry) for entry in entries}) != len(entries):
                parser.error('Duplicate volume IDs in a dataset; resolve the manifest before evaluation.')
            groups.append((root.name, root, entries))

    started = perf_counter()
    counts = Counter()
    run_metadata = {'schema_version': 'sampling-study-1.0', 'controls': list(CONTROL_NAMES),
        'own_wrapper_mutations': list(MUTATION_NAMES), 'crop_margin_source_voxels': MARGIN,
        'support_policy_controls': ['roi_truncation'], 'planned_case_order': list(CASE_ORDER),
        'isotropic_spacing_mm': [0.8, 1., 2.], 'mutation_reference_spacing_mm': 0.8,
        'grid_rationale': 'Clinical 1/2 mm grids plus 0.8 mm, fixed from known input-spacing metadata before outcome evaluation, to include fractional resampling of 1 mm MRI sources.',
        'output_size': 'floor((source_size-1)*source_spacing/target_spacing)+1',
        'target_origin_and_direction': 'Preserved from working source; no centring or outcome-dependent shift.',
        'roundtrip_policy': 'All synthetic cases; first three lexicographically sorted IDs of every clinical dataset, without replacement.',
        'checkpoint_policy': 'Two constructed examples on first sorted ID of each dataset, without replacement.',
        'boundary': 'Native materialized image/mask outputs; separate prespecified NIfTI subset.',
        'native_feature_extraction': False,
        'index_boundary_atol': INDEX_BOUNDARY_ATOL,
        'acceptance_policy': 'Only status=satisfied is a satisfied sampling check; indeterminate_boundary and not_available are distinct from acceptance. Support and feature reuse remain separate decisions.',
        'native_input_subset_requested': args.native_input_output is not None,
        'native_input_roles': ['source_working_crop', 'isotropic_0p8mm', 'isotropic_1mm', 'isotropic_2mm', 'wrong_image_kernel'],
        'software': {'python': platform.python_version(), 'numpy': np.__version__,
                     'nibabel': nib.__version__, 'SimpleITK': sitk.Version_VersionString()},
        'source_hashes': {path.name: digest(path) for path in (
            Path(__file__), ROOT / 'software' / 'sampling_contracts.py', ROOT / 'software' / 'physical_contracts.py',
            ROOT / 'radaccord_sampling.py')},
        'datasets': []}
    with targets[0].open('x', encoding='utf-8', newline='\n') as cases, \
            targets[1].open('x', encoding='utf-8', newline='\n') as volumes, \
            targets[2].open('x', encoding='utf-8', newline='\n') as checkpoints, \
            (native_manifest.open('x', encoding='utf-8', newline='\n') if native_manifest is not None else nullcontext()) as native_file:
        for dataset, root, entries in groups:
            ids = [entry['id'] if root is None else volume_id(entry) for entry in entries]
            run_metadata['datasets'].append({'name': dataset, 'attempted_ids': ids,
                'file_roundtrip_ids': ids if root is None else ids[:3], 'checkpoint_id': ids[0] if ids else None,
                'planned_case_counts': {name: len(ids) for name in CASE_ORDER},
                'planned_kind_counts': {kind: sum(value == kind for value in CASE_KINDS.values()) * len(ids)
                                       for kind in set(CASE_KINDS.values())},
                'dataset_json_sha256': digest(root / 'dataset.json') if root is not None else None})
            for index, entry in enumerate(entries):
                identifier = ids[index]
                volume_start = perf_counter()
                metadata = {'dataset': dataset, 'volume_id': identifier, 'file_roundtrip_selected': root is None or index < 3}
                progress = {'completed': {}, 'current_case': None, 'operation_phase': 'input_preparation'}
                counts['attempted_volumes'] += 1
                try:
                    phase = 'input_preparation'
                    io_start = perf_counter()
                    if root is None:
                        source = phantom(entry['seed'])
                        source.data = source.data - 130.125
                        provenance = {'seed': entry['seed'], 'unit': 'synthetic_volume',
                                      'generator': 'physical_contracts.phantom(seed), then subtract 130.125 intensity units; signed, nonintegral development data.'}
                    else:
                        source, provenance = load_clinical(root, entry)
                    metadata.update(provenance)
                    metadata['input_io_seconds'] = perf_counter() - io_start
                    metadata['source_shape'] = list(source.data.shape)
                    phase = 'case_generation_or_evaluation'
                    rows, conversion_seconds = run_volume(source, dataset, identifier, root is None or index < 3,
                        cases, checkpoints, index == 0,
                        native_output=args.native_input_output if index < 3 and root is not None else None,
                        native_manifest=native_file, progress=progress)
                    metadata['input_to_native_seconds'] = conversion_seconds
                    metadata['status'] = 'evaluated'
                    counts['evaluated_volumes'] += 1
                except (ValueError, OSError, RuntimeError, ArithmeticError) as error:
                    metadata.update({'status': 'not_available', 'error_type': type(error).__name__,
                                     'phase': phase, 'partial_case_records_possible': phase != 'input_preparation',
                                     'failed_case': progress['current_case'], 'operation_phase': progress['operation_phase'],
                                     'reason': 'Input preparation or native operation unavailable; retain this volume in the attempted denominator.'})
                    counts['unavailable_volumes'] += 1
                ledger = []
                for name in CASE_ORDER:
                    item = {'case': name, 'kind': CASE_KINDS[name]}
                    if name in progress['completed']:
                        item.update({'execution_status': 'completed', 'sampling_status': progress['completed'][name]})
                    elif name == progress['current_case']:
                        item.update({'execution_status': 'unavailable', 'error_type': metadata.get('error_type'),
                                     'operation_phase': progress['operation_phase']})
                    else:
                        item.update({'execution_status': 'not_reached',
                            'reason': 'source_input_unavailable' if phase == 'input_preparation' else 'preceding_operation_unavailable'})
                    counts['case_execution:' + item['execution_status']] += 1
                    ledger.append(item)
                metadata['case_ledger'] = ledger
                metadata['total_seconds'] = perf_counter() - volume_start
                emit(volumes, metadata)
                print(json.dumps({'dataset': dataset, 'volume_id': identifier, 'status': metadata['status']}, sort_keys=True), flush=True)
    # Count the written records, including any completed cases preceding a later
    # unavailable operation. Do not silently discard partial-volume evidence.
    with targets[0].open(encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            counts['cases'] += 1
            counts[row['kind'] + ':' + row['sampling']['status']] += 1
            if row['mutation'] is not None:
                counts['mutation_active' if row['mutation']['active'] else 'mutation_inactive'] += 1
            counts['roundtrip:' + row['file_roundtrip']['status']] += 1
    run_metadata['counts'] = dict(counts)
    run_metadata['elapsed_seconds'] = perf_counter() - started
    targets[3].write_text(json.dumps(run_metadata, indent=2, allow_nan=False, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'counts': dict(counts)}, sort_keys=True))
    return 0 if counts['unavailable_volumes'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
