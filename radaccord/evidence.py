"""Small, path-free records linking native observations to their inputs."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np


def json_value(value):
    """Represent numerical evidence without JSON NaN or opaque Python objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (np.bool_, np.integer)):
        return value.item()
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    raise TypeError('Evidence supports only JSON-compatible scalar or array values.')


def config_digest(value):
    encoded = json.dumps(json_value(value), sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def array_digest(value, dtype=None):
    array = np.asarray(value, dtype=dtype)
    array = np.ascontiguousarray(array.astype(array.dtype.newbyteorder('<'), copy=False))
    digest = hashlib.sha256()
    digest.update(json.dumps({'shape': array.shape, 'dtype': array.dtype.str},
                             sort_keys=True).encode('ascii'))
    digest.update(memoryview(array).cast('B'))
    return digest.hexdigest()


def frame_record(frame):
    """Hashes bind decoded samples, selected membership and physical geometry."""
    values = {'image_sha256': array_digest(frame.data, '<f8'),
              'selected_roi_sha256': array_digest(frame.mask == frame.label, 'u1'),
              'affine_sha256': array_digest(frame.affine, '<f8'),
              'shape': list(frame.data.shape), 'source_dtype': str(frame.data.dtype),
              'selected_voxels': int(np.count_nonzero(frame.mask == frame.label))}
    values['frame_sha256'] = config_digest({key: values[key] for key in
        ('image_sha256', 'selected_roi_sha256', 'affine_sha256', 'shape')})
    return values


def feature_digest(features):
    """Bind scalar feature values, retaining explicit nonfinite counts."""
    mapping = {str(key): json_value(value) for key, value in features.items()}
    return {'sha256': config_digest(mapping), 'count': len(mapping),
            'nonfinite_count': sum(value is None for value in mapping.values())}


def sitk_affine(image):
    affine = np.eye(4)
    affine[:3, :3] = np.asarray(image.GetDirection()).reshape(3, 3) @ np.diag(image.GetSpacing())
    affine[:3, 3] = image.GetOrigin()
    return np.diag([-1., -1., 1., 1.]) @ affine


def frame_from_sitk(image, mask, label=1, position_atol_mm=1e-4):
    import SimpleITK as sitk
    from .legacy import Frame
    if image.GetDimension() != 3 or mask.GetDimension() != 3:
        raise ValueError('The native profile requires three-dimensional inputs.')
    if image.GetNumberOfComponentsPerPixel() != 1 or mask.GetNumberOfComponentsPerPixel() != 1:
        raise ValueError('The native profile requires scalar images and masks.')
    if image.GetSize() != mask.GetSize():
        raise ValueError('Native image and mask grids have different shapes.')
    affine, mask_affine = sitk_affine(image), sitk_affine(mask)
    corners = np.asarray(list(itertools.product(*[(0, n-1) for n in image.GetSize()])), dtype=float)
    corners = np.column_stack((corners, np.ones(len(corners))))
    maximum = np.linalg.norm((corners @ (affine-mask_affine).T)[:, :3], axis=1).max()
    if maximum > position_atol_mm:
        raise ValueError('Native image and mask physical coordinates disagree.')
    # Copies isolate retained observations from subsequent native processing.
    return Frame(sitk.GetArrayFromImage(image).transpose(2, 1, 0),
                 sitk.GetArrayFromImage(mask).transpose(2, 1, 0), affine, label)


def read_sitk(value):
    import SimpleITK as sitk
    from pathlib import Path
    if isinstance(value, sitk.Image):
        return value
    if isinstance(value, (str, Path)):
        return sitk.ReadImage(str(value))
    raise TypeError('Expected an image filename or SimpleITK image.')


def overall_status(checks):
    states = [item.get('status', 'unavailable') for item in checks]
    for state in ('violated', 'unavailable', 'indeterminate'):
        if state in states:
            return state
    return 'satisfied' if states and all(item == 'satisfied' for item in states) else 'unavailable'


def implementation_record(adapter):
    """Bind the checking implementation; file contents only, never local paths."""
    from . import __version__
    from importlib.metadata import version, PackageNotFoundError
    from .legacy import physical_contracts, sampling_contracts
    directory = Path(__file__).resolve().parent
    paths = {name: directory / (name+'.py') for name in ('evidence', 'operators', 'numerics', adapter)}
    paths.update(physical_contracts=Path(physical_contracts.__file__),
                 sampling_contracts=Path(sampling_contracts.__file__))
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    backend_versions = {}
    for package in (('SimpleITK',) if adapter == 'pyradiomics' else ('SimpleITK', 'scipy', 'pandas')):
        try:
            backend_versions[package] = version(package)
        except PackageNotFoundError:
            backend_versions[package] = None
    return {'name': 'RadAccord', 'version': __version__, 'numpy_version': np.__version__,
            'backend_versions': backend_versions,
            'source_sha256': hashes, 'implementation_sha256': config_digest(hashes)}
