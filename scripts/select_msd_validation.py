"""Fixed input selection and source eligibility only; never imports RadAccord."""
from collections import Counter
from datetime import datetime, timezone
from itertools import product
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

import nibabel as nib
import numpy as np

TASKS = ('Task02_Heart', 'Task06_Lung')
PREFIX = 'RadAccord-new-cohort-v1'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def corner_error(first, second, shape):
    corners = np.array(list(product(*[(0,n-1) for n in shape])) + [],dtype=float)
    homogeneous = np.c_[corners, np.ones(len(corners))]
    delta = homogeneous @ (first-second).T
    return float(np.max(np.linalg.norm(delta[:,:3],axis=1)))

def inspect(image_path, mask_path):
    reasons, details = [], {}
    pair = {}
    for kind, path in (('image',image_path),('mask',mask_path)):
        try:
            obj = nib.load(path)
            pair[kind] = obj
            dtype = obj.get_data_dtype()
            details[kind+'_dtype'] = str(dtype)
            details[kind+'_shape'] = list(obj.shape)
            details[kind+'_units'] = obj.header.get_xyzt_units()[0]
            if len(obj.shape)!=3 or min(obj.shape)<2:
                reasons.append(kind+':not_scalar_3d_domain')
            if dtype.kind not in 'iuf':
                reasons.append(kind+':not_real_numeric')
            if obj.header.get_xyzt_units()[0] != 'mm':
                reasons.append(kind+':units_not_mm')
            affine = obj.affine
            if affine is None or not np.all(np.isfinite(affine)):
                reasons.append(kind+':nonfinite_affine')
                continue
            spacing = np.linalg.norm(affine[:3,:3],axis=0)
            if np.any(~np.isfinite(spacing)) or np.any(spacing<=0) or abs(np.linalg.det(affine[:3,:3]))<1e-12:
                reasons.append(kind+':singular_affine')
                continue
            details[kind+'_spacing_mm'] = spacing.tolist()
            axes = affine[:3,:3]/spacing
            orth = float(np.max(np.abs(axes.T@axes-np.eye(3))))
            details[kind+'_orthogonality_error'] = orth
            if orth>1e-5:
                reasons.append(kind+':nonorthogonal_axes')
            q,qc = obj.get_qform(coded=True)
            s,sc = obj.get_sform(coded=True)
            details[kind+'_qform_code'],details[kind+'_sform_code'] = int(qc),int(sc)
            if not qc and not sc:
                reasons.append(kind+':no_active_transform')
            if qc and sc and len(obj.shape)==3:
                error = corner_error(q,s,obj.shape)
                details[kind+'_qform_sform_corner_error_mm'] = error
                if not np.isfinite(error) or error>1e-4:
                    reasons.append(kind+':qform_sform_conflict')
        except Exception:
            reasons.append(kind+':source_read_failed')
    if len(pair)!=2:
        return sorted(set(reasons)),details
    image,mask = pair['image'],pair['mask']
    if image.shape!=mask.shape:
        reasons.append('paired_shape_mismatch')
    elif len(image.shape)==3:
        error = corner_error(image.affine,mask.affine,image.shape)
        details['paired_corner_error_mm'] = error
        if not np.isfinite(error) or error>1e-4:
            reasons.append('paired_affine_mismatch')
    if len(image.shape)==3 and len(mask.shape)==3:
        try:
            image_data = np.asanyarray(image.dataobj)
            mask_data = np.asanyarray(mask.dataobj)
            if not np.all(np.isfinite(image_data)):
                reasons.append('image:nonfinite_decoded_values')
            if not np.all(np.isfinite(mask_data)):
                reasons.append('mask:nonfinite_decoded_values')
            elif not np.all(mask_data == np.floor(mask_data)):
                reasons.append('mask:nonintegral_labels')
            roi = mask_data == 1
            details['label'] = 1
            details['foreground_voxels'] = int(np.count_nonzero(roi))
            if details['foreground_voxels']<8:
                reasons.append('mask:foreground_fewer_than_8_voxels')
            if np.any(roi):
                coordinates = np.where(roi)
                lower = np.array([int(x.min()) for x in coordinates])
                upper = np.array([int(x.max())+1 for x in coordinates])
                extent = upper-lower
                details['foreground_bbox_extent_voxels'] = extent.tolist()
                if np.any(extent<2):
                    reasons.append('mask:foreground_not_3d_extent')
                if 'image_spacing_mm' in details:
                    pad = np.ceil(10.0/np.asarray(details['image_spacing_mm'])).astype(int)
                    crop_lower = np.maximum(lower-pad,0)
                    crop_upper = np.minimum(upper+pad,np.array(mask.shape))
                    details['proposed_10mm_crop_lower_index'] = crop_lower.tolist()
                    details['proposed_10mm_crop_shape'] = (crop_upper-crop_lower).tolist()
            del image_data,mask_data,roi
        except Exception:
            reasons.append('content:eligibility_read_failed')
    return sorted(set(reasons)),details

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True,
                        help='Verified extracted archives, outside the repository.')
    parser.add_argument('--public-output', type=Path, required=True,
                        help='New provenance directory; prior selection files are never overwritten.')
    parser.add_argument('--selection-protocol', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'protocol/new_cohort_selection.md')
    args = parser.parse_args()
    data, public_output = args.data_dir.resolve(), args.public_output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if data.is_relative_to(repo) or repo.is_relative_to(data):
        parser.error('The private data directory must be outside, and not contain, the repository.')
    if data.is_relative_to(public_output) or public_output.is_relative_to(data):
        parser.error('Private data and public provenance must occupy separate directory trees.')
    for dest in (public_output/'selection_order.json', public_output/'selected_source_eligibility.json', data/'selected_inputs.jsonl'):
        if dest.exists():
            parser.error('A selection output already exists; use a fresh output destination and private acquisition tree.')
    public_output.mkdir(parents=True,exist_ok=True)
    selected, census = [], []
    for task in TASKS:
        root = data/task
        document = json.loads((root/'dataset.json').read_text(encoding='utf-8'))
        if '1' not in document['labels']:
            raise ValueError('Release does not declare foreground label 1')
        candidates = []
        for row in document['training']:
            for field in ('image', 'label'):
                value = row[field]
                relative = PurePosixPath(value)
                if (relative.is_absolute() or '..' in relative.parts or '\\' in value or ':' in value
                        or not (root / relative).resolve().is_relative_to(root.resolve())):
                    raise ValueError('Unsafe release manifest path')
            basename = Path(row['image']).name
            key = hashlib.sha256(f'{PREFIX}|{task}|{basename}'.encode('utf-8')).hexdigest()
            candidates.append(dict(task=task,source_basename=basename,selection_hash=key,
                image_relative=row['image'],mask_relative=row['label']))
        if len({r['source_basename'] for r in candidates}) != len(candidates):
            raise ValueError('Duplicate source basename')
        candidates.sort(key=lambda r:(r['selection_hash'],r['source_basename']))
        for rank,row in enumerate(candidates,1):
            row.update(selection_rank=rank,selected=rank<=12)
        census.extend(candidates)
        selected.extend(dict(r) for r in candidates[:12])
    # Bind all selections before any selected voxel-array read.
    selection = dict(schema='radaccord-new-clinical-selection-1',
        selected_at_utc=datetime.now(timezone.utc).isoformat(),prefix=PREFIX,
        selection_protocol_sha256=sha(args.selection_protocol),
        selected_slots=len(selected),requested_per_collection=12,all_ranked_training=census)
    selection_path = public_output/'selection_order.json'
    selection_path.write_text(json.dumps(selection,indent=2)+'\n',encoding='utf-8')
    private, public = [], []
    for row in selected:
        task = row['task']
        image = data/task/row['image_relative']
        mask = data/task/row['mask_relative']
        reasons,details = inspect(image,mask)
        hashes = {}
        for kind, path in (('image', image), ('mask', mask)):
            try:
                hashes[kind] = sha(path)
            except OSError:
                hashes[kind] = None
                reasons.append(kind + ':source_hash_unavailable')
        reasons = sorted(set(reasons))
        entry = dict(row,case_id=f"{task}:{row['source_basename'][:-7]}",
            image_sha256=hashes['image'],mask_sha256=hashes['mask'],label=1,
            source_eligible=not reasons,exclusion_reasons=reasons,source_metadata=details)
        public.append(entry)
        private.append(dict(entry,image=str(image.resolve()),mask=str(mask.resolve())))
        print(json.dumps({'task':task,'rank':row['selection_rank'],'eligible':not reasons,'reasons':reasons}),flush=True)
    result = dict(schema='radaccord-new-clinical-eligibility-1',
        inspection_scope='Source headers, finite values and selected-label occupancy only; no transformations, RadAccord decisions or native feature outcomes.',
        selection_sha256=sha(selection_path),selected_slots=len(selected),
        eligible_slots=sum(r['source_eligible'] for r in public),
        excluded_slots=sum(not r['source_eligible'] for r in public),records=public)
    (public_output/'selected_source_eligibility.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (data/'selected_inputs.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in private),encoding='utf-8')
    for task in TASKS:
        rows=[r for r in public if r['task']==task]
        print(json.dumps({'task':task,'selected':len(rows),'eligible':sum(r['source_eligible'] for r in rows),
            'storage_dtypes':dict(Counter(r['source_metadata'].get('image_dtype') for r in rows)),
            'crop_shapes':[r['source_metadata'].get('proposed_10mm_crop_shape') for r in rows]}))

if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'unavailable', 'reason': 'selection_failed',
                          'error_type': type(error).__name__}))
        raise SystemExit(2) from None
