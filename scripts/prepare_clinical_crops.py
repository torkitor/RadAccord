"""Prepare fixed physical-context crops without interpolation or intensity changes.

Raw data, cropped images and manifests with paths must remain private. Only
source hashes, crop indices, geometry and deterministic verification are public.
No RadAccord checker or native feature extractor is used by this preparation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import nibabel as nib
import numpy as np

REPOSITORY = Path(__file__).resolve().parents[1]


class SourceIntegrityError(ValueError):
    """Bound source bytes changed; stop rather than evaluate another source."""


def _bounds(shape, lower, upper):
    lower, upper = np.asarray(lower), np.asarray(upper)
    if (len(shape) != 3 or lower.shape != (3,) or upper.shape != (3,)
            or lower.dtype.kind not in 'iu' or upper.dtype.kind not in 'iu'
            or np.any(lower < 0) or np.any(upper > shape) or np.any(lower >= upper)):
        raise ValueError('Crop bounds must be nonempty, integral and inside the source grid.')
    return lower, upper


def _corner_error(first, second, shape):
    corners = np.array(np.meshgrid(*[(0, size-1) for size in shape], indexing='ij')).reshape(3, -1).T
    delta = np.c_[corners, np.ones(len(corners))] @ (first-second).T
    return float(np.max(np.linalg.norm(delta[:, :3], axis=1)))


def _validate_pair(image, mask):
    """Recheck the declared physical domain without calling RadAccord."""
    if image.shape != mask.shape or len(image.shape) != 3 or min(image.shape) < 2:
        raise ValueError('Selected image and mask must have matching scalar 3D grids.')
    for source in (image, mask):
        affine = source.affine
        if source.header.get_xyzt_units()[0] != 'mm' or not np.all(np.isfinite(affine)):
            raise ValueError('Crop source requires finite millimetre geometry.')
        spacing = np.linalg.norm(affine[:3, :3], axis=0)
        if np.any(spacing <= 0) or not np.all(np.isfinite(spacing)):
            raise ValueError('Crop source has invalid voxel spacing.')
        direction = affine[:3, :3] / spacing
        if np.max(np.abs(direction.T @ direction-np.eye(3))) > 1e-5:
            raise ValueError('Crop source axes must be orthogonal.')
        qform, qcode = source.get_qform(coded=True)
        sform, scode = source.get_sform(coded=True)
        if not qcode and not scode:
            raise ValueError('Crop source requires an active coordinate form.')
        if qcode and scode and (not np.all(np.isfinite(qform)) or not np.all(np.isfinite(sform))
                              or _corner_error(qform, sform, source.shape) > 1e-4):
            raise ValueError('Source qform and sform disagree.')
        values = np.asanyarray(source.dataobj)
        if values.dtype.kind not in 'iuf' or not np.all(np.isfinite(values)):
            raise ValueError('Crop source requires finite real numeric values.')
    if _corner_error(image.affine, mask.affine, image.shape) > 1e-4:
        raise ValueError('Selected image and mask physical coordinates disagree.')
    labels = np.asanyarray(mask.dataobj)
    if not np.array_equal(labels, np.round(labels)):
        raise ValueError('Crop mask labels must be integral.')
    selected = np.where(labels == 1)
    if len(selected[0]) < 8 or any(axis.max()-axis.min()+1 < 2 for axis in selected):
        raise ValueError('Selected ROI does not meet the declared source-domain extent.')


def digest(path):
    with Path(path).open('rb') as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
        return value.hexdigest()


def crop_bounds(mask, spacing, context_mm=10.0, label=1):
    spacing = np.asarray(spacing, dtype=float)
    if (mask.ndim != 3 or spacing.shape != (3,) or not np.all(np.isfinite(spacing))
            or np.any(spacing <= 0) or not np.isfinite(context_mm) or context_mm < 0):
        raise ValueError('Invalid crop domain or physical context.')
    coords = np.where(mask == label)
    if not len(coords[0]):
        raise ValueError('The selected label is absent; no replacement case is chosen.')
    padding = np.ceil(context_mm / spacing).astype(int)
    lower = np.maximum([int(axis.min()) for axis in coords] - padding, 0)
    upper = np.minimum(np.array([int(axis.max()) + 1 for axis in coords]) + padding, mask.shape)
    return lower, upper


def crop_object(source, lower, upper):
    """Retain decoded values and update the voxel-to-world map by index translation."""
    lower, upper = _bounds(source.shape, lower, upper)
    values = np.asanyarray(source.dataobj)
    section = tuple(slice(int(a), int(b)) for a, b in zip(lower, upper))
    cropped = values[section].copy()
    translation = np.eye(4)
    translation[:3, 3] = lower
    affine = source.affine @ translation
    header = source.header.copy()
    header.set_data_dtype(cropped.dtype)
    header.set_slope_inter(1.0, 0.0)
    output = nib.Nifti1Image(cropped, affine, header)
    output.set_sform(affine, code=1)
    output.set_qform(affine, code=1, strip_shears=False)
    return output


def verify_crop(source, cropped, lower, upper, label=None):
    """Direct array and world-coordinate checks, independent of RadAccord."""
    lower, upper = _bounds(source.shape, lower, upper)
    original = np.asanyarray(source.dataobj)
    observed = np.asanyarray(cropped.dataobj)
    section = tuple(slice(int(a), int(b)) for a, b in zip(lower, upper))
    expected = original[section]
    if observed.dtype != expected.dtype or not np.array_equal(observed, expected, equal_nan=True):
        raise ValueError('Crop changed decoded values or their dtype.')
    translation = np.eye(4)
    translation[:3, 3] = lower
    expected_affine = source.affine @ translation
    # NIfTI-1 stores affine rows in float32. Bound the representational error
    # explicitly; do not require bit equality to a float64 matrix product.
    corners = np.array(np.meshgrid(*[(0, size - 1) for size in observed.shape], indexing='ij')).reshape(3, -1).T
    world_error = np.c_[corners, np.ones(len(corners))] @ (cropped.affine - expected_affine).T
    error_mm = float(np.max(np.linalg.norm(world_error[:, :3], axis=1)))
    if not np.isfinite(error_mm) or error_mm > 1e-4:
        raise ValueError('Serialized crop geometry exceeds the fixed 0.0001 mm bound.')
    result = {'decoded_array_equal': True, 'decoded_dtype_equal': True,
              'maximum_world_error_mm': error_mm, 'geometry_tolerance_mm': 1e-4}
    if label is not None:
        before, after = int(np.count_nonzero(original == label)), int(np.count_nonzero(observed == label))
        if not before or before != after:
            raise ValueError('The complete selected ROI was not retained.')
        result.update(selected_roi_voxels_before=before, selected_roi_voxels_after=after,
                      selected_roi_completely_retained=True)
    return result


def _write_json(path, value):
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def prepare(selected_inputs, output, public_receipt, private_manifest):
    selected_inputs, output, public_receipt, private_manifest = map(
        Path, (selected_inputs, output, public_receipt, private_manifest))
    if any(path.resolve().is_relative_to(REPOSITORY)
           for path in (selected_inputs, output, private_manifest)):
        raise ValueError('Private input manifests, crop volumes and path manifests must remain outside the repository.')
    destinations = [str(path.resolve()).casefold() for path in (output, public_receipt, private_manifest)]
    if len(set(destinations)) != 3:
        raise ValueError('Crop output, public receipt and private manifest require distinct destinations.')
    if output.exists() or public_receipt.exists() or private_manifest.exists():
        raise ValueError('Preparation destinations must be new; existing evidence is never overwritten.')
    records = [json.loads(line) for line in selected_inputs.read_text(encoding='utf-8').splitlines() if line.strip()]
    receipts, manifest, identities = [], {}, set()
    for row in records:
        if (not re.fullmatch(r'Task[0-9]{2}_[A-Za-z0-9]+', row['task'])
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*_[0-9]+\.nii\.gz', row['source_basename'])
                or not isinstance(row['source_eligible'], bool)
                or not isinstance(row['selection_rank'], int) or isinstance(row['selection_rank'], bool)
                or row['selection_rank'] < 1
                or not isinstance(row['exclusion_reasons'], list)
                or any(not isinstance(code, str) or not re.fullmatch('[a-z0-9_]+(?::[a-z0-9_]+)?', code)
                       for code in row['exclusion_reasons'])
                or any(not ((row[key] is None and not row['source_eligible'] and row['exclusion_reasons'])
                            or (isinstance(row[key], str) and re.fullmatch('[0-9a-f]{64}', row[key])))
                       for key in ('image_sha256', 'mask_sha256'))):
            raise ValueError('Selection identifiers, eligibility codes and bound hashes must be canonical.')
        identity = row['task'] + '_' + row['source_basename'].removesuffix('.nii.gz')
        if identity.casefold() in identities:
            raise ValueError('Duplicate or case-colliding selected source identity.')
        identities.add(identity.casefold())
        receipt = {'id': identity, 'task': row['task'], 'selection_rank': row['selection_rank'],
                   'source_image_sha256': row['image_sha256'], 'source_mask_sha256': row['mask_sha256'],
                   'source_eligible': row['source_eligible'], 'exclusion_reasons': row['exclusion_reasons'],
                   'status': 'not_reached' if row['source_eligible'] else 'source_excluded'}
        receipts.append(receipt)
    output.mkdir(parents=True)
    public_receipt.parent.mkdir(parents=True, exist_ok=True)
    private_manifest.parent.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 'clinical-crop-receipt-1', 'records': receipts,
              'planned_source_volumes': len(records),
              'source_eligible_volumes': sum(row['source_eligible'] for row in records),
              'active_id': None,
              'scope': 'Direct decoded-array and geometry verification. Native feature equivalence to full volumes is not asserted.'}
    _write_json(public_receipt, result)
    _write_json(private_manifest, manifest)
    for row, receipt in zip(records, receipts):
        if not row['source_eligible']:
            continue
        identity = receipt['id']
        result['active_id'] = identity
        receipt['status'] = 'preparation_in_progress'
        _write_json(public_receipt, result)
        try:
            paths = [Path(row[key]) for key in ('image', 'mask')]
            if [digest(p) for p in paths] != [row['image_sha256'], row['mask_sha256']]:
                raise SourceIntegrityError('A selected source differs from its bound hash.')
            source_image, source_mask = [nib.load(p) for p in paths]
            _validate_pair(source_image, source_mask)
            spacing = np.linalg.norm(source_image.affine[:3, :3], axis=0)
            lower, upper = crop_bounds(np.asanyarray(source_mask.dataobj), spacing)
            receipt.update(lower_index=lower.tolist(), upper_index_exclusive=upper.tolist(), context_mm=10.0,
                           original_shape=list(source_image.shape), crop_shape=(upper-lower).tolist(), label=1)
            crop_paths = [output/(identity+'_'+kind+'.nii.gz') for kind in ('image', 'mask')]
            for kind, source, destination in zip(('image', 'mask'), (source_image, source_mask), crop_paths):
                nib.save(crop_object(source, lower, upper), destination)
                receipt[kind+'_verification'] = verify_crop(source, nib.load(destination), lower, upper,
                                                            label=1 if kind == 'mask' else None)
                receipt[kind+'_sha256'] = digest(destination)
            receipt['status'] = 'prepared_and_verified'
            manifest[identity] = dict(zip(('image', 'mask'), [str(p.resolve()) for p in crop_paths]))
        except Exception as error:
            receipt.update(status='preparation_failed', exception_type=type(error).__name__,
                           reason_code='source_hash_mismatch' if isinstance(error, SourceIntegrityError)
                                       else 'preparation_or_verification_failed')
            if isinstance(error, SourceIntegrityError):
                raise
        finally:
            result['active_id'] = None
            _write_json(private_manifest, manifest)
            _write_json(public_receipt, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selected-inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-receipt', type=Path, required=True)
    parser.add_argument('--private-manifest', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.selected_inputs, args.output, args.public_receipt, args.private_manifest)
