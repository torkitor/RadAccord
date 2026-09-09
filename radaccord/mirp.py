"""Post-extraction evidence for the original-image export of native MIRP 2.5.0.

The declaration uses the decoded source and resolved configuration before native
execution. No preprocessing is substituted and native feature tables are returned
unchanged. Decoding and unobserved internal feature-class states are outside scope.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib.metadata import version
import inspect
import itertools
import time

import numpy as np

from .evidence import (config_digest, frame_record, implementation_record,
                       json_value, overall_status)
from .legacy import Frame


PROFILE = 'mirp-native-original-2'
TESTED_VERSIONS = {'2.5.0'}


def _frame(image, mask):
    """Convert native ZYX/LPS objects to retained XYZ/RAS arrays in millimetres."""
    data, membership = image.get_voxel_grid(), mask.get_voxel_grid()
    if data.ndim != 3 or membership.shape != data.shape:
        raise ValueError('Native image and mask grids must be equally shaped and three-dimensional.')
    affine, mask_affine = image.get_affine_matrix(), mask.get_affine_matrix()
    corners = np.asarray(list(itertools.product(*[(0, n-1) for n in data.shape])), dtype=float)
    corners = np.column_stack((corners, np.ones(len(corners))))
    if np.max(np.linalg.norm((corners @ (affine-mask_affine).T)[:, :3], axis=1)) > 1e-4:
        raise ValueError('Native image and mask physical coordinates disagree.')
    reverse = np.eye(4); reverse[:3, :3] = np.eye(3)[::-1]
    ras = np.diag([-1., -1., 1., 1.])
    return Frame(data.transpose(2, 1, 0).copy(), membership.transpose(2, 1, 0).copy(),
                 ras @ reverse @ affine @ reverse)


def _supported_settings(settings, modality):
    """Admissibility depends on resolved intent, never observed feature values."""
    g, p, a = settings.general, settings.post_process, settings.perturbation
    if modality not in ('mr', 'generic'):
        raise ValueError('unsupported_modality')
    if g.by_slice or any((g.mask_merge, g.mask_split, g.mask_select_largest_region,
                          g.mask_select_largest_slice)):
        raise ValueError('unsupported_mask_or_slice_processing')
    if p.image_denoise_method != 'none' or p.bias_field_correction or \
            p.intensity_normalisation != 'none' or p.intensity_scaling != 1.0:
        raise ValueError('unsupported_intensity_processing')
    if a.crop_around_roi or a.add_noise or a.randomise_roi or \
            any(float(x) != 0 for x in a.rotation_angles + a.translation_fraction +
                a.roi_adapt_size + a.roi_boundary_size):
        raise ValueError('unsupported_perturbation')
    if settings.roi_resegment.resegmentation_method not in (None, ['none']):
        raise ValueError('unsupported_resegmentation')
    if settings.img_transform.spatial_filters is not None:
        raise ValueError('unsupported_filtered_images')
    if settings.roi_interpolate.incl_threshold != .5:
        raise ValueError('unsupported_mask_threshold')


def declare_mirp(source, settings, modality='mr', *, native_spacing=None):
    """Declare MIRP's centre-aligned grid using only the trusted source/settings.

    Arrays and the specification use XYZ; MIRP computes in ZYX. The independent
    operator therefore reproduces its numerical axis order explicitly.
    """
    source.validate()
    _supported_settings(settings, modality)
    interpolation = settings.img_interpolate
    source_spacing = np.linalg.norm(source.affine[:3, :3], axis=0)
    if native_spacing is not None:
        # Preserve the decoded native spacing's floating representation: norm
        # reconstruction can change ceil at a target-grid integer boundary.
        native_spacing = np.asarray(native_spacing, dtype=float)
        if native_spacing.shape != (3,) or not np.allclose(native_spacing, source_spacing,
                                                         atol=1e-12, rtol=1e-12):
            raise ValueError('inconsistent_native_spacing')
        source_spacing = native_spacing
    size = np.asarray(source.data.shape)
    target = source_spacing.copy()
    if interpolation.interpolate:
        if len(interpolation.new_spacing) != 1:
            raise ValueError('unsupported_multiple_target_grids')
        target = np.asarray(interpolation.new_spacing[0][::-1], dtype=float)
    if target.shape != (3,) or np.any(target <= 0) or not np.all(np.isfinite(target)):
        raise ValueError('invalid_target_spacing')
    shape = np.ceil(size*source_spacing/target).astype(int) if interpolation.interpolate else size
    scale = target/source_spacing
    origin = .5*(size-1)-.5*(shape-1)*scale if interpolation.interpolate else np.zeros(3)
    index_map = np.diag([*scale, 1.]); index_map[:3, 3] = origin
    expected_affine = source.affine @ index_map
    # Match native registration's geometry comparison before seeing its output.
    mask_skip = np.array_equal(size, shape) and np.allclose(source_spacing, target) and \
        np.allclose(source.affine[:3, 3], expected_affine[:3, 3])
    if mask_skip and not np.array_equal(index_map, np.eye(4)):
        raise ValueError('near_identity_mask_registration_not_covered')
    orders = {0: 'nearest', 1: 'linear', 3: 'bspline3'}
    image_order = interpolation.spline_order if interpolation.interpolate else 0
    mask_order = settings.roi_interpolate.spline_order
    if image_order not in orders or mask_order not in (0, 1):
        raise ValueError('unsupported_interpolation_order')
    aa = interpolation.interpolate and interpolation.anti_aliasing
    sigma = np.sqrt(-8*scale**2*np.log(interpolation.smoothing_beta)) if aa else None
    dtype = 'float32' if aa else str(source.data.dtype)
    if source.data.dtype.kind in 'iu':
        # Integer storage is admitted only for unchanged samples. Do not infer
        # support for integer interpolation or its antialias/casting pipeline.
        if (str(source.data.dtype) not in ('uint8', 'uint16', 'int16', 'int32')
                or interpolation.interpolate or aa or not mask_skip
                or not np.array_equal(index_map, np.eye(4))):
            raise ValueError('unsupported_integer_processing')
    elif dtype not in ('float32', 'float64'):
        raise ValueError('unsupported_source_storage_dtype')
    return {'index_map': index_map.tolist(), 'candidate_shape': shape.tolist(),
            'world_map': np.eye(4).tolist(), 'interpolation': orders[image_order],
            'boundary': 'nearest', 'outside_value': 0., 'output_dtype': dtype,
            'integer_cast': 'round_half_away',
            'antialias_sigma': None if sigma is None else sigma.tolist(),
            'antialias_dtype': 'float32', 'antialias_boundary': 'nearest',
            'gaussian_truncate': 4., 'axis_order': [2, 1, 0],
            'mask_skip': bool(mask_skip), 'mask_interpolation': orders[mask_order],
            'mask_boundary': 'constant', 'mask_antialias_boundary': 'nearest',
            'mask_antialias_sigma': None if sigma is None or mask_skip else sigma.tolist(),
            'mask_threshold_after_antialias': True, 'mask_threshold': .5,
            'mask_round_decimals': 6, 'mask_threshold_atol': 1e-9,
            'position_atol_mm': 1e-4,
            'intensity_atol': 0. if source.data.dtype.kind in 'iu' else 1e-4,
            'index_boundary_atol': 1e-9}


def _unavailable(reason):
    return {'checkpoint': 'original_image_export_after_extraction',
            'status': 'unavailable', 'reason_code': reason}


def _tables_record(tables):
    records = []
    for table in tables:
        if table is None:
            records.append({'available': False})
        else:
            # Native metadata can contain personal names and paths. Hash the
            # table without exporting its column names or metadata values.
            encoded = table.to_json(orient='split', double_precision=15).encode('utf-8')
            records.append({'available': True, 'rows': len(table), 'columns': len(table.columns),
                            'sha256': hashlib.sha256(encoded).hexdigest()})
    return records


def audit_mirp(image, mask, *, config=None, label=1):
    """Execute native MIRP once and return its feature table plus path-free evidence.

    config contains MIRP keyword arguments. Numeric label selection is translated
    to its native roi_name selector; an already selected BaseMask stays binary.
    A single workflow returns its exact DataFrame. Multiple workflows return a
    list of their exact tables and unavailable evidence for this bounded profile.
    """
    from mirp import extract_features_and_images
    from mirp._data_import.read_data import read_image_and_masks
    from mirp._masks.base_mask import BaseMask
    from mirp.data_import.import_image_and_mask import import_image_and_mask
    from mirp.settings.import_config_parameters import import_configuration_settings
    from .numerics import verify_native_operation

    if config is not None and not isinstance(config, dict):
        raise TypeError('config must be a MIRP keyword-argument dictionary.')
    if isinstance(label, bool) or not isinstance(label, (int, np.integer)) or label <= 0:
        raise ValueError('label must be a positive integer.')
    options = deepcopy(config or {})
    reserved = {'image', 'mask', 'write_dir', 'write_features', 'write_images',
                'export_features', 'export_images', 'image_export_format', 'settings'}
    if reserved.intersection(options):
        raise ValueError('Pass processing keywords only; adapter controls native in-memory export.')
    if not isinstance(mask, BaseMask):
        if 'roi_name' in options and options['roi_name'] != str(label):
            raise ValueError('roi_name must agree with the explicitly selected numeric label.')
        options['roi_name'] = str(label)
    elif label != 1:
        raise ValueError('An already selected BaseMask has binary label 1.')
    engine_version = version('mirp')
    configuration_hash = config_digest(options)
    start = time.perf_counter()
    source = source_record = declaration = None
    reason = 'source_or_configuration_outside_native_profile'
    try:
        settings = import_configuration_settings(compute_features=True, **options)
        if len(settings) != 1 or engine_version not in TESTED_VERSIONS:
            raise ValueError('unverified_engine_or_multiple_configurations')
        import_keys = inspect.signature(import_image_and_mask).parameters
        source_options = {key: deepcopy(value) for key, value in options.items() if key in import_keys}
        inputs = import_image_and_mask(image=deepcopy(image), mask=deepcopy(mask), **source_options)
        if len(inputs) != 1:
            raise ValueError('multiple_input_images')
        retained_image, retained_masks = read_image_and_masks(inputs[0], to_numpy=False,
            pet_suv_conversion=settings[0].post_process.suv_conversion_type)
        if len(retained_masks) != 1:
            raise ValueError('multiple_or_missing_selected_masks')
        source = _frame(retained_image, retained_masks[0].roi)
        source_record = frame_record(source)
        # One Frame has one affine. Coalescing merely close source image/ROI
        # geometries would change the expected registration intensities.
        if not np.array_equal(retained_image.get_affine_matrix(),
                              retained_masks[0].roi.get_affine_matrix()):
            raise ValueError('distinct_source_image_and_roi_grids_not_covered')
        declaration = declare_mirp(source, settings[0], retained_image.modality,
                                   native_spacing=retained_image.image_spacing[::-1])
    except (ValueError, TypeError, RuntimeError, KeyError, AttributeError):
        # Native exception strings can include directories and identifiers.
        declaration = None

    native = extract_features_and_images(image=image, mask=mask, **options,
        export_features=True, export_images=True, write_features=False, write_images=False,
        image_export_format='native')
    tables = [result[0] for result in native]
    checks = []
    if declaration is None or len(native) != 1:
        checks.append(_unavailable(reason if declaration is None else 'multiple_native_workflows'))
    else:
        try:
            images, masks = native[0][1], native[0][2]
            if len(images) != 1 or len(masks) != 1:
                raise ValueError('multiple_or_missing_native_exports')
            exported_mask = masks[0]
            observed = _frame(images[0], exported_mask.roi)
            check = verify_native_operation(source, observed, declaration)
            check.update(checkpoint='original_image_export_after_extraction',
                         observed=frame_record(observed))
            memberships = {}
            for name in ('roi_intensity', 'roi_morphology'):
                component = getattr(exported_mask, name)
                memberships[name] = component is not None and \
                    frame_record(_frame(images[0], component))['selected_roi_sha256'] == \
                    frame_record(observed)['selected_roi_sha256']
            check['exported_feature_roi_agreement'] = memberships
            if not all(memberships.values()):
                check['status'] = 'violated'
            checks.append(check)
        except (ValueError, TypeError, RuntimeError, KeyError, AttributeError):
            checks.append(_unavailable('observed_export_outside_native_profile'))
    status = overall_status(checks)
    accepted = status == 'satisfied' and all(
        check.get('coverage', {}).get('status') == 'satisfied' and
        check.get('candidate_roi_voxels', 0) > 0 for check in checks)
    report = {'schema_version': 'radaccord-native-1', 'profile': PROFILE,
              'checker': implementation_record('mirp'),
              'engine': {'name': 'mirp', 'version': engine_version}, 'status': status,
              'configuration_sha256': configuration_hash, 'source': source_record,
              'feature_tables': _tables_record(tables),
              'declaration_timing': 'before_native_execute',
              'declarations': {} if declaration is None else {'original_image_export': declaration},
              'checkpoints': checks,
              'relationship_acceptance': accepted,
              'acceptance_scope': 'post_extraction_original_input_and_source_centre_coverage',
              'unverified_obligations': ['input_decoding', 'feature_formulae',
                                        'unobserved_internal_feature_states', 'feature_value_validity',
                                        'clinical_validity'],
              'scope': 'The decoded source and original image/ROI export are observed. '
                       'No internal pre-feature checkpoint or clinical validity is certified.',
              'elapsed_seconds': time.perf_counter()-start}
    return {'features': tables[0] if len(tables) == 1 else tables, 'report': json_value(report)}


extract_with_evidence = audit_mirp
