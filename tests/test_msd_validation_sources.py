"""Synthetic source-selection and archive-safety tests; no clinical checks."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile

import nibabel as nib
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
SELECT = REPO / 'scripts/select_msd_validation.py'
DOWNLOAD = REPO / 'scripts/download_msd_validation.py'
selection = runpy.run_path(str(SELECT), run_name='selection_definitions')
acquisition = runpy.run_path(str(DOWNLOAD), run_name='acquisition_definitions')


def save(values, path, affine=None):
    affine = np.eye(4) if affine is None else affine
    obj = nib.Nifti1Image(values, affine)
    obj.header.set_xyzt_units('mm')
    obj.set_qform(affine, 1)
    obj.set_sform(affine, 1)
    nib.save(obj, path)


def test_source_eligibility_geometry_and_empty_roi(tmp_path):
    image, mask = tmp_path/'image.nii.gz', tmp_path/'mask.nii.gz'
    data = np.arange(64, dtype=np.float32).reshape(4, 4, 4)
    roi = np.zeros(data.shape, dtype=np.uint8)
    roi[1:3, 1:3, 1:3] = 1
    save(data, image)
    save(roi, mask)
    reasons, meta = selection['inspect'](image, mask)
    assert not reasons
    assert meta['foreground_voxels'] == 8
    assert meta['proposed_10mm_crop_shape'] == [4, 4, 4]
    shifted = np.eye(4)
    shifted[0, 3] = .01
    save(roi, mask, shifted)
    assert 'paired_affine_mismatch' in selection['inspect'](image, mask)[0]
    save(np.zeros_like(roi), mask)
    assert 'mask:foreground_fewer_than_8_voxels' in selection['inspect'](image, mask)[0]


def test_selection_cli_retains_failed_fixed_slot_and_paths_private(tmp_path):
    data_dir, public = tmp_path/'private', tmp_path/'public'
    expected = {}
    for task in selection['TASKS']:
        root = data_dir/task
        (root/'imagesTr').mkdir(parents=True)
        (root/'labelsTr').mkdir()
        rows = [{'image': f'./imagesTr/synthetic_{i:02}.nii.gz',
                 'label': f'./labelsTr/synthetic_{i:02}.nii.gz'} for i in range(13)]
        ranked = sorted(rows, key=lambda r: hashlib.sha256(
            f"RadAccord-new-cohort-v1|{task}|{Path(r['image']).name}".encode()).hexdigest())
        expected[task] = [Path(r['image']).name for r in ranked[:12]]
        for row in rows:
            values = np.arange(64, dtype=np.float32).reshape(4, 4, 4)
            roi = np.zeros(values.shape, dtype=np.uint8)
            roi[1:3, 1:3, 1:3] = 1
            save(values, root/row['image'])
            save(roi, root/row['label'])
        # A selected unreadable image stays selected; rank 13 must not replace it.
        (root/ranked[0]['image']).unlink()
        (root/'dataset.json').write_text(json.dumps({'labels': {'1': 'target'}, 'training': rows}))
    command = [sys.executable, '-B', str(SELECT), '--data-dir', str(data_dir), '--public-output', str(public)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout
    result = json.loads((public/'selected_source_eligibility.json').read_text())
    assert (result['selected_slots'], result['eligible_slots'], result['excluded_slots']) == (24, 22, 2)
    for task in selection['TASKS']:
        records = [r for r in result['records'] if r['task'] == task]
        assert [r['source_basename'] for r in records] == expected[task]
        assert records[0]['image_sha256'] is None
        assert 'image:source_read_failed' in records[0]['exclusion_reasons']
    for path in public.iterdir():
        assert str(tmp_path) not in path.read_text()
    private = [json.loads(line) for line in (data_dir/'selected_inputs.jsonl').read_text().splitlines()]
    assert len(private) == 24 and all(Path(r['image']).is_absolute() for r in private)
    prior = (public/'selection_order.json').read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert (public/'selection_order.json').read_bytes() == prior


@pytest.mark.parametrize('kind', ['traversal', 'symlink', 'duplicate'])
def test_archive_unsafe_members_rejected_before_write(tmp_path, kind):
    task = 'Task02_Heart'
    with tarfile.open(tmp_path/(task+'.tar'), 'w') as tar:
        first = tarfile.TarInfo(task+'/dataset.json')
        first.size = 2
        tar.addfile(first, io.BytesIO(b'{}'))
        member = tarfile.TarInfo('../escape' if kind == 'traversal' else task+'/dataset.json')
        if kind == 'symlink':
            member.name = task+'/link'
            member.type = tarfile.SYMTYPE
            member.linkname = '../escape'
        tar.addfile(member)
    with pytest.raises(ValueError):
        acquisition['extract'](task, tmp_path)
    assert not (tmp_path/(task+'.extracting')).exists()
    assert not (tmp_path/task).exists()
