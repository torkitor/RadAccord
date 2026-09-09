"""Synthetic read/write reproduction of MIRP issue 124; no clinical inputs.

Run as a module from the repository root in each isolated historical environment:
python -B -m scripts.reproduce_mirp_nifti_regression --expected-version 2.4.1 --out results/mirp_nifti_regression/2.4.1.json
Only JSON evidence is retained. NIfTI fixtures live in a temporary directory.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import inspect
import itertools
import json
from pathlib import Path
import platform
import tempfile
import time

import nibabel as nib
import numpy as np
from radaccord.legacy import Frame
from radaccord.operators import verify_operation


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rotation(x, y, z):
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    rx = np.array([[1., 0., 0.], [0., cx, -sx], [0., sx, cx]])
    ry = np.array([[cy, 0., sy], [0., 1., 0.], [-sy, 0., cy]])
    rz = np.array([[cz, -sz, 0.], [sz, cz, 0.], [0., 0., 1.]])
    return rz@ry@rx


def _fixture(angles):
    shape = (11, 13, 9)
    x, y, z = np.indices(shape)
    data = 137.+2.25*x-1.5*y+.75*z+.125*x*y
    mask = (((x-4.3)/3.1)**2+((y-6.1)/4.2)**2+((z-3.7)/2.7)**2 < 1.).astype(np.int16)
    mask[7:9, 4:7, 2:4] = 1
    affine = np.eye(4)
    affine[:3, :3] = _rotation(*angles)@np.diag([.8, 1.3, 2.1])
    affine[:3, 3] = [27.5, -61.25, 14.75]
    return Frame(data.astype(np.float64), mask, affine)


def _write_input(data, affine, path):
    image = nib.Nifti1Image(data, affine)
    image.header.set_xyzt_units('mm')
    image.set_sform(affine, code=1)
    image.set_qform(affine, code=1)
    nib.save(image, path)


def _corner_error(left, right, shape):
    indices = np.array(list(itertools.product(*[(0, n-1) for n in shape])), dtype=float).T
    delta = left-right
    return float(np.max(np.linalg.norm(delta[:3, :3]@indices+delta[:3, 3, None], axis=0)))


def reproduce(expected_version):
    actual_version = importlib.metadata.version('mirp')
    if actual_version != expected_version or actual_version not in ('2.4.1', '2.4.2'):
        raise ValueError('Run in an isolated environment with exactly the requested MIRP 2.4.1 or 2.4.2.')
    from mirp.data_import.import_image import import_image
    from mirp._data_import.read_data import read_image
    from mirp._images.generic_image import GenericImage
    cases = [('axis_aligned', (0., 0., 0.)), ('oblique_z', (0., 0., .31)),
             ('oblique_xyz', (.23, -.17, .31))]
    rows = []
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='radaccord_mirp_nifti_') as temporary:
        directory = Path(temporary)
        for case_id, angles in cases:
            source = _fixture(angles)
            source.validate()
            case_directory = directory/case_id
            case_directory.mkdir()
            image_path, mask_path = case_directory/'source.nii.gz', case_directory/'source_mask.nii.gz'
            _write_input(source.data, source.affine, image_path)
            _write_input(source.mask, source.affine, mask_path)
            # The known affine is retained before invoking MIRP. The two
            # exported files are read solely with NiBabel for comparison.
            native = read_image(import_image(image=str(image_path), image_modality='mr')[0], to_numpy=False)
            native_mask = read_image(import_image(image=str(mask_path), image_modality='mr')[0], to_numpy=False)
            native.write(case_directory, file_name='exported', file_format='nifti')
            native_mask.write(case_directory, file_name='exported_mask', file_format='nifti')
            exported_image = nib.load(case_directory/'exported.nii.gz')
            exported_mask = nib.load(case_directory/'exported_mask.nii.gz')
            candidate = Frame(exported_image.get_fdata(dtype=np.float64),
                              np.asarray(exported_mask.dataobj).astype(np.int16), exported_image.affine)
            spec = dict(index_map=np.eye(4).tolist(), candidate_shape=list(source.data.shape),
                        interpolation='nearest', outside_value=0., output_dtype='float64',
                        position_atol_mm=1e-4, intensity_atol=1e-4, index_boundary_atol=1e-9)
            result = verify_operation(source, candidate, spec)
            pair_error = _corner_error(exported_image.affine, exported_mask.affine, source.data.shape)
            row = dict(case_id=case_id, rotation_radians=list(angles), shape=list(source.data.shape),
                       source_affine_ras_mm=source.affine.tolist(), exported_affine_ras_mm=exported_image.affine.tolist(),
                       original_nifti_affine_ras_mm=nib.load(image_path).affine.tolist(),
                       max_input_serialization_corner_error_mm=_corner_error(source.affine, nib.load(image_path).affine, source.data.shape),
                       paired_export_max_corner_error_mm=pair_error, paired_export_geometry_agrees=pair_error <= 1e-4,
                       array_exact=np.array_equal(candidate.data, source.data), mask_exact=np.array_equal(candidate.mask, source.mask),
                       source_nifti_sha256=_sha(image_path), source_mask_nifti_sha256=_sha(mask_path),
                       exported_nifti_sha256=_sha(case_directory/'exported.nii.gz'),
                       exported_mask_nifti_sha256=_sha(case_directory/'exported_mask.nii.gz'),
                       verification=result)
            rows.append(row)
    packages = {}
    for name in ['mirp', 'itk', 'itk-core', 'itk-io', 'numpy', 'nibabel', 'scipy', 'pandas', 'pydicom', 'scikit-image']:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    from radaccord import operators
    return dict(schema_version='historical-nifti-1', experiment='MIRP issue 124 synthetic read-write boundary reproduction',
                provenance=dict(release_url='https://github.com/oncoray/mirp/releases/tag/v2.4.2',
                                issue_url='https://github.com/oncoray/mirp/issues/124',
                                fix_commit='172d24964a6d8ab8b264bc32650c6f09f5635805'),
                environment=dict(python=platform.python_version(), system=platform.system(), packages=packages),
                implementation_sha256=dict(reproduction_script=_sha(__file__),
                                           generic_image_module=_sha(inspect.getfile(GenericImage)),
                                           operator_checker=_sha(inspect.getfile(operators))),
                scope='Three synthetic images and matching masks; native NIfTI write boundary only. No feature extraction, clinical accuracy, or automatic bug localisation is tested.',
                source_trust='Analytical source arrays and RAS affine declared before NiBabel serialization and before MIRP import; exported files are read independently with NiBabel.',
                cases=rows, runtime_seconds=time.perf_counter()-start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-version', choices=['2.4.1', '2.4.2'], required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Choose a fresh evidence path; existing records are not overwritten.')
    result = reproduce(args.expected_version)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'mirp': args.expected_version, 'cases': [
        {'case_id': row['case_id'], 'status': row['verification']['status'],
         'corner_error_mm': row['verification'].get('max_corner_error_mm'),
         'arrays_exact': row['array_exact'] and row['mask_exact'],
         'paired_geometry_agrees': row['paired_export_geometry_agrees']} for row in result['cases']]}))


if __name__ == '__main__':
    main()
