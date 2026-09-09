"""Observe native PyRadiomics dispatch without replacing its computations.

The declared grid is derived from the retained source ROI and resolved settings
before execute(). Reports verify supported input relationships, not every feature
formula or an unobserved extractor state. Scientific feature values are returned
unchanged; the additional diagnostics stay separate from the evidence report.
"""
from __future__ import annotations

from copy import deepcopy
from importlib.metadata import version
import time

import numpy as np

from .evidence import (config_digest, feature_digest, frame_from_sitk,
                       frame_record, implementation_record, json_value, overall_status, read_sitk)


PROFILE = 'pyradiomics-native-original-2'
TESTED_VERSIONS = {'3.0.1'}


def _bbox(mask, label):
    points = np.argwhere(mask == label)
    if not len(points):
        raise ValueError('The selected source ROI is empty.')
    return points.min(axis=0), points.max(axis=0)


def _crop_spec(source, lower, upper):
    index_map = np.eye(4)
    index_map[:3, 3] = lower
    return {'index_map': index_map.tolist(), 'candidate_shape': (upper-lower+1).tolist(),
            'interpolation': 'nearest', 'boundary': 'sitk', 'outside_value': 0.,
            'position_atol_mm': 1e-4, 'intensity_atol': 1e-4, 'index_boundary_atol': 1e-9,
            'output_dtype': str(source.data.dtype)}


def declare_pyradiomics(source, settings):
    """Derive the loadImage grid from source/configuration only.

    Equations follow the publicly documented 3.0.1 crop/resampling convention.
    Pixel sampling is checked by a separate NumPy implementation.
    """
    source.validate()
    if settings.get('normalize', False):
        raise ValueError('Normalisation is outside this native sampling profile.')
    if settings.get('resegmentRange') is not None:
        raise ValueError('Resegmentation is outside this native sampling profile.')
    if settings.get('force2D', False) or settings.get('voxelBased', False):
        raise ValueError('This profile checks original three-dimensional segment inputs.')
    label = settings.get('label', source.label)
    if label != source.label:
        raise ValueError('Declared labels disagree.')
    lower, upper = _bbox(source.mask, label)
    size = np.asarray(source.data.shape)
    padding = settings.get('padDistance', 5)
    if isinstance(padding, bool) or int(padding) != padding or padding < 0:
        raise ValueError('The declared padding must be a nonnegative integer.')
    padding = int(padding)
    spacing = np.linalg.norm(source.affine[:3, :3], axis=0)
    target = settings.get('resampledPixelSpacing')
    interpolator = settings.get('interpolator')
    if target is None or interpolator is None:
        if settings.get('preCrop', False):
            lower, upper = np.maximum(lower-padding, 0), np.minimum(upper+padding, size-1)
        else:
            lower, upper = np.zeros(3, dtype=int), size-1
        return _crop_spec(source, lower, upper)
    target = np.asarray(target, dtype=float)
    if target.shape != (3,) or not np.all(np.isfinite(target)) or np.any(target < 0):
        raise ValueError('Invalid declared target spacing.')
    target = np.where(target == 0, spacing, target)
    target = np.where(upper-lower+1 == 1, spacing, target)
    # PyRadiomics 3.0.1 calls numpy.allclose without overriding its defaults.
    if np.allclose(spacing, target):
        return _crop_spec(source, np.maximum(lower-padding, 0), np.minimum(upper+padding, size-1))
    names = {1: 'nearest', 2: 'linear', 3: 'bspline3',
             'sitkNearestNeighbor': 'nearest', 'sitkLinear': 'linear', 'sitkBSpline': 'bspline3'}
    if interpolator not in names:
        raise ValueError('The requested interpolator has no verified native profile.')
    ratio = spacing / target
    new_lower = np.maximum(np.floor((lower-.5)*ratio-padding), 0.)
    new_upper = np.minimum(np.ceil((upper+.5)*ratio+padding), np.ceil(size*ratio)-1.)
    index_map = np.diag([*(target/spacing), 1.])
    index_map[:3, 3] = .5*(target-spacing)/spacing + new_lower/ratio
    spec = _crop_spec(source, np.zeros(3, dtype=int), (new_upper-new_lower).astype(int))
    spec.update(index_map=index_map.tolist(), interpolation=names[interpolator])
    return spec


def _unavailable(checkpoint, reason):
    return {'checkpoint': checkpoint, 'status': 'unavailable', 'reason_code': reason}


def audit_pyradiomics(image, mask, *, config=None, label=1):
    """Return unchanged native features plus independently checked observations.

    config is the usual PyRadiomics parameter dictionary with setting,
    imageType and featureClass entries. Unsupported checks abstain while the
    native extractor remains responsible for executing its requested workflow.
    """
    from radiomics import featureextractor
    from .operators import expected_mask
    from .numerics import verify_native_operation
    if config is not None and not isinstance(config, dict):
        raise TypeError('config must be a PyRadiomics parameter dictionary.')
    checkpoints = []
    expected = {}
    start = time.perf_counter()

    class ObservedExtractor(featureextractor.RadiomicsFeatureExtractor):
        def loadImage(self, *args, **kwargs):
            observed_image, observed_mask = super().loadImage(*args, **kwargs)
            capture('loaded_input', observed_image, observed_mask, kwargs)
            return observed_image, observed_mask

        def computeShape(self, observed_image, observed_mask, boundingBox, **kwargs):
            # The dispatcher is observed; its subsequent internal crop and
            # feature-class implementation are explicitly outside this checkpoint.
            capture('shape_dispatch', observed_image, observed_mask, kwargs,
                    bounding_box=np.asarray(boundingBox).tolist())
            return super().computeShape(observed_image, observed_mask, boundingBox, **kwargs)

        def computeFeatures(self, observed_image, observed_mask, imageTypeName, **kwargs):
            capture('feature_input:'+str(imageTypeName), observed_image, observed_mask, kwargs)
            return super().computeFeatures(observed_image, observed_mask, imageTypeName, **kwargs)

    extractor = ObservedExtractor(deepcopy(config)) if config is not None else ObservedExtractor()
    settings = deepcopy(extractor.settings)
    settings['label'] = label
    configuration = {'settings': settings, 'image_types': deepcopy(extractor.enabledImagetypes),
                     'features': deepcopy(extractor.enabledFeatures)}
    configuration_hash = config_digest(configuration)
    engine_version = version('pyradiomics')
    source = None
    source_record = None
    declaration_reason = None
    crop_declaration_ambiguous = False
    try:
        retained_image, retained_mask = read_sitk(image), read_sitk(mask)
        # This single-Frame profile cannot represent two distinct source
        # grids. PyRadiomics derives the target from the mask grid; merely
        # accepting a small image/mask mismatch would misdeclare that intent.
        if any(getattr(retained_image, method)() != getattr(retained_mask, method)()
               for method in ('GetSize', 'GetSpacing', 'GetOrigin', 'GetDirection')):
            raise ValueError('distinct_source_image_and_mask_grids')
        source = frame_from_sitk(retained_image, retained_mask, label)
        source_record = frame_record(source)
        if engine_version not in TESTED_VERSIONS:
            raise ValueError('unverified_engine_version')
        initial = declare_pyradiomics(source, settings)
        selected = expected_mask(source, initial)
        roi_lower, roi_upper = _bbox(selected, True)
        crop = np.eye(4); crop[:3, 3] = roi_lower
        last = deepcopy(initial)
        last['index_map'] = (np.asarray(initial['index_map']) @ crop).tolist()
        last['candidate_shape'] = (roi_upper-roi_lower+1).tolist()
        expected = {'loaded_input': initial, 'shape_dispatch': initial,
                    'feature_input:original': last}
        expected_bbox = np.column_stack((roi_lower, roi_upper)).ravel().tolist()
    except (ValueError, TypeError, RuntimeError, KeyError):
        # Raw library exceptions can contain filenames or source metadata.
        declaration_reason = 'source_or_configuration_outside_native_profile'
        expected_bbox = None

    def capture(checkpoint, observed_image, observed_mask, actual_settings, bounding_box=None):
        nonlocal crop_declaration_ambiguous
        if source is None or checkpoint not in expected:
            checkpoints.append(_unavailable(checkpoint, declaration_reason or 'unassigned_image_type'))
            return
        if checkpoint.startswith('feature_input:') and crop_declaration_ambiguous:
            checkpoints.append(_unavailable(checkpoint, 'roi_crop_depends_on_ambiguous_membership'))
            return
        try:
            observed = frame_from_sitk(observed_image, observed_mask, label)
            evidence = verify_native_operation(source, observed, expected[checkpoint])
            evidence['checkpoint'] = checkpoint
            evidence['observed'] = frame_record(observed)
            if checkpoint == 'loaded_input' and evidence.get('ambiguous_roi_voxels', 0):
                crop_declaration_ambiguous = True
            if bounding_box is not None and crop_declaration_ambiguous:
                evidence['bounding_box_status'] = 'indeterminate'
            elif bounding_box is not None:
                agrees = bounding_box == expected_bbox
                evidence['declared_bounding_box'] = expected_bbox
                evidence['observed_bounding_box'] = bounding_box
                evidence['bounding_box_status'] = 'satisfied' if agrees else 'violated'
                if not agrees:
                    evidence['status'] = 'violated'
            # Resolved runtime settings must still equal the declared ones.
            changes = [key for key in settings if key in actual_settings and
                       config_digest(actual_settings[key]) != config_digest(settings[key])]
            missing = [key for key in settings if key not in actual_settings]
            evidence['changed_declared_setting_keys'] = changes
            evidence['missing_declared_setting_keys'] = missing
            if changes or missing:
                evidence['status'] = 'unavailable' if evidence['status'] != 'violated' else 'violated'
            checkpoints.append(evidence)
        except (ValueError, TypeError, RuntimeError, KeyError):
            checkpoints.append(_unavailable(checkpoint, 'observed_state_outside_native_profile'))

    native = extractor.execute(str(image) if hasattr(image, '__fspath__') else image,
                               str(mask) if hasattr(mask, '__fspath__') else mask, label=label)
    features = {key: value for key, value in native.items() if not key.startswith('diagnostics_')}
    status = overall_status(checkpoints)
    report = {'schema_version': 'radaccord-native-1', 'profile': PROFILE,
              'checker': implementation_record('pyradiomics'),
              'engine': {'name': 'pyradiomics', 'version': engine_version},
              'status': status, 'configuration_sha256': configuration_hash,
              'source': source_record, 'feature_values': feature_digest(features),
              'declaration_timing': 'before_native_execute',
              'declarations': expected, 'checkpoints': checkpoints,
              'unverified_obligations': ['feature_formulae', 'internal_shape_class_crop',
                                        'clinical_validity', 'unobserved_pipeline_states'],
              'scope': 'Post-extraction acceptance evidence for the observed native input boundaries. '
                       'This does not certify all numerical features or clinical use.',
              'elapsed_seconds': time.perf_counter()-start}
    return {'features': features, 'report': json_value(report),
            'diagnostics': {key: value for key, value in native.items() if key.startswith('diagnostics_')}}
