"""Declared operator references implemented with NumPy, independently of producers.

Arrays and all axis-valued settings use XYZ; Frame affines map centres to RAS mm.
The index_map is declared before production, never estimated from the candidate.
Supported cubic profiles are cardinal degree-three B-splines: whole-sample mirror
coefficients for ITK, and SciPy's nearest extension with 12 edge-padding samples.
The coefficient reference solves the interpolation equations directly; it does
not call a producer's recursive prefilter, interpolator or Gaussian filter.

Gaussian filtering uses sampled, normalized kernels, truncate=4 by default, and
an explicit working dtype/axis order. Thresholded mask interpolation is a
separate operation. Engineering ambiguity bands are not certified error bounds.
Nominal expected_* helpers are planning tools, not verification decisions.

Primary definitions: https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.ndimage.map_coordinates.html
and https://docs.itk.org/projects/doxygen/en/stable/classitk_1_1BSplineInterpolateImageFunction.html
"""
from itertools import product
import math
import numpy as np
from .legacy import Frame, sampling_contracts as base


_KEYS = set('index_map candidate_shape interpolation boundary outside_value world_map '
            'intensity_gain intensity_offset position_atol_mm intensity_atol index_boundary_atol '
            'output_dtype integer_cast output_cast_atol antialias_sigma antialias_dtype antialias_boundary '
            'axis_order gaussian_truncate mask_outside mask_interpolation mask_boundary '
            'mask_threshold mask_round_decimals mask_threshold_atol mask_antialias_sigma '
            'mask_antialias_boundary mask_threshold_after_antialias mask_skip'.split())


def _parse(source, spec):
    source.validate()
    required = {'index_map', 'candidate_shape', 'interpolation', 'outside_value',
                'position_atol_mm', 'intensity_atol'}
    if not isinstance(spec, dict) or not required <= spec.keys():
        raise ValueError('Missing required operator declaration fields')
    if set(spec) - _KEYS:
        raise ValueError('Unsupported operator declaration fields: ' + ', '.join(sorted(set(spec)-_KEYS)))
    p = dict(spec)
    p['index_map'] = base._affine(p['index_map'], 'index_map')
    p['world_map'] = base._affine(p.get('world_map', np.eye(4)), 'world_map')
    shape = p['candidate_shape']
    if (not isinstance(shape, (tuple, list)) or len(shape) != 3 or
            any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)) or v < 1 for v in shape)):
        raise ValueError('candidate_shape must be three positive integers')
    p['candidate_shape'] = tuple(int(v) for v in shape)
    if math.prod(shape) > np.iinfo(np.int64).max:
        raise ValueError('candidate_shape is outside the supported domain')
    defaults = dict(boundary='sitk', output_dtype='float64', integer_cast='truncate', output_cast_atol=1e-9,
                    intensity_gain=1., intensity_offset=0., index_boundary_atol=1e-9,
                    antialias_sigma=None, antialias_dtype='float32', antialias_boundary='nearest',
                    axis_order=[2, 1, 0], gaussian_truncate=4., mask_outside=0,
                    mask_interpolation='nearest', mask_threshold=.5, mask_round_decimals=None,
                    mask_threshold_atol=1e-9, mask_antialias_sigma=None,
                    mask_antialias_boundary='nearest', mask_threshold_after_antialias=False,
                    mask_skip=False)
    for key, value in defaults.items():
        p.setdefault(key, value)
    p.setdefault('mask_boundary', p['boundary'])
    if p['interpolation'] not in ('nearest', 'linear', 'bspline3'):
        raise ValueError('Supported interpolation profiles are nearest, linear and bspline3')
    if p['boundary'] not in ('sitk', 'nearest') or p['mask_boundary'] not in ('sitk', 'nearest', 'constant'):
        raise ValueError('Unsupported image or mask boundary profile')
    if p['mask_interpolation'] not in ('nearest', 'linear'):
        raise ValueError('Supported mask interpolation profiles are nearest and linear')
    if p['output_dtype'] not in ('float64', 'float32', 'int16', 'int32', 'uint16', 'uint8'):
        raise ValueError('Unsupported output_dtype')
    if p['integer_cast'] not in ('truncate', 'round_half_away'):
        raise ValueError('integer_cast must be truncate or round_half_away')
    if p['antialias_dtype'] not in ('float32', 'float64'):
        raise ValueError('antialias_dtype must be float32 or float64')
    if sorted(p['axis_order']) != [0, 1, 2] or len(p['axis_order']) != 3:
        raise ValueError('axis_order must be a permutation of XYZ axes 0,1,2')
    for key in ('antialias_boundary', 'mask_antialias_boundary'):
        if p[key] not in ('nearest', 'constant'):
            raise ValueError(key + ' must be nearest or constant')
    for key in ('antialias_sigma', 'mask_antialias_sigma'):
        if p[key] is not None:
            if len(p[key]) != 3:
                raise ValueError(key + ' must contain three XYZ standard deviations')
            p[key] = [base._real(v, key, nonnegative=True) for v in p[key]]
    for key in ('position_atol_mm', 'intensity_atol', 'index_boundary_atol', 'mask_threshold_atol', 'output_cast_atol'):
        p[key] = base._real(p[key], key, nonnegative=True)
    if p['index_boundary_atol'] >= .25 or p['mask_threshold_atol'] >= .25 or p['output_cast_atol'] >= .25:
        raise ValueError('Ambiguity bands must be less than 0.25 in their declared units')
    for key in ('outside_value', 'intensity_offset', 'mask_threshold'):
        p[key] = base._real(p[key], key)
    p['intensity_gain'] = base._real(p['intensity_gain'], 'intensity_gain', positive=True)
    p['gaussian_truncate'] = base._real(p['gaussian_truncate'], 'gaussian_truncate', positive=True)
    if not 0 < p['mask_threshold'] < 1 or p['mask_outside'] != 0 or isinstance(p['mask_outside'], bool):
        raise ValueError('Only background mask fill and thresholds strictly between zero and one are supported')
    decimals = p['mask_round_decimals']
    if decimals is not None and (isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 12):
        raise ValueError('mask_round_decimals must be None or an integer from 0 to 12')
    if decimals is not None and np.round(p['mask_threshold'], decimals) <= 0.:
        raise ValueError('Rounding must not turn the selected-mask threshold into zero')
    for key in ('mask_skip', 'mask_threshold_after_antialias'):
        if not isinstance(p[key], (bool, np.bool_)):
            raise ValueError(key + ' must be boolean')
    if p['mask_skip'] and (tuple(source.data.shape) != p['candidate_shape'] or not np.array_equal(p['index_map'], np.eye(4))):
        raise ValueError('mask_skip is supported only for an exactly unchanged index grid')
    p['expected_affine'] = p['world_map'] @ source.affine @ p['index_map']
    # Reuse the established orthogonal, real and finite physical domain.
    base._validate_observed(Frame(source.data, source.mask, p['expected_affine'], source.label))
    return p


def _gaussian(array, sigma, dtype, axis_order, truncate, boundary):
    """Sampled Gaussian with explicit sequential dtype rounding and edge policy."""
    out = np.asarray(array, dtype=dtype)
    if sigma is None:
        return out
    for axis in axis_order:
        sd = sigma[axis]
        if sd <= 1e-15:  # SciPy gaussian_filter skips numerically zero axes.
            continue
        radius = int(truncate*sd + .5)
        offsets = np.arange(-radius, radius+1)
        kernel = np.exp(-.5*(offsets/sd)**2)
        kernel /= kernel.sum()
        accum = np.zeros(out.shape, dtype=np.float64)
        indices = np.arange(out.shape[axis])
        for offset, weight in zip(offsets, kernel):
            shifted = indices + offset
            values = np.take(out, np.clip(shifted, 0, out.shape[axis]-1), axis=axis)
            if boundary == 'constant':
                keep_shape = [1]*out.ndim
                keep_shape[axis] = len(indices)
                values = values * ((shifted >= 0) & (shifted < len(indices))).reshape(keep_shape)
            accum += weight*values.astype(np.float64)
        out = accum.astype(dtype)
    return out


def _coefficients(array, boundary, axis_order):
    """Solve f_i = (c_(i-1)+4*c_i+c_(i+1))/6 along each axis.

    Mirror: c_-1=c_1. Reflect after nearest prepadding: c_-1=c_0.
    Unlike producer recursive implementations this is a tridiagonal solve.
    """
    values = np.asarray(array, dtype=np.float64)
    if boundary == 'nearest':
        values = np.pad(values, 12, mode='edge')
    for axis in axis_order:
        y = np.moveaxis(values, axis, 0).copy()
        n = len(y)
        if n == 1:
            continue
        y *= 6.
        diag = np.full(n, 4.)
        upper = np.ones(n-1)
        lower = np.ones(n-1)
        if boundary == 'sitk':
            upper[0] = lower[-1] = 2.
        else:
            diag[0] = diag[-1] = 5.
        for k in range(1, n):
            multiplier = lower[k-1]/diag[k-1]
            diag[k] -= multiplier*upper[k-1]
            y[k] -= multiplier*y[k-1]
        y[-1] /= diag[-1]
        for k in range(n-2, -1, -1):
            y[k] = (y[k]-upper[k]*y[k+1])/diag[k]
        values = np.moveaxis(y, 0, axis)
    return values


def _basis(distance):
    u = np.abs(distance)
    return np.where(u < 1., (4.-6.*u*u+3.*u*u*u)/6.,
                    np.where(u < 2., (2.-u)**3/6., 0.))


def _interpolate(array, q, interpolation, boundary, outside=0., coefficients=None):
    size = np.asarray(array.shape)[:, None]
    if boundary == 'sitk':
        inside = np.all((q >= -.5) & (q < size-.5), axis=0)
    elif boundary == 'constant':
        inside = np.all((q >= 0.) & (q <= size-1.), axis=0)
    else:
        inside = np.ones(q.shape[1], dtype=bool)
    result = np.full(q.shape[1], outside, dtype=np.float64)
    x = q[:, inside]
    if not x.shape[1]:
        return result, inside
    if interpolation == 'nearest':
        indices = np.clip(np.floor(x+.5).astype(np.int64), 0, size-1)
        result[inside] = array[tuple(indices)]
    elif interpolation == 'linear':
        x = np.clip(x, 0., size-1.)
        low = np.floor(x).astype(np.int64)
        high = np.minimum(low+1, size-1)
        fraction = x-low
        values = np.zeros(x.shape[1])
        for corner in product((0, 1), repeat=3):
            idx = tuple(high[a] if corner[a] else low[a] for a in range(3))
            weight = np.prod([fraction[a] if corner[a] else 1.-fraction[a] for a in range(3)], axis=0)
            values += weight*np.asarray(array[idx], dtype=float)
        result[inside] = values
    else:
        if boundary == 'nearest':
            x = x+12.
        low = np.floor(x).astype(np.int64)-1
        values = np.zeros(x.shape[1])
        for corner in product(range(4), repeat=3):
            idx = low+np.asarray(corner)[:, None]
            weight = np.prod(_basis(x-idx), axis=0)
            for axis in range(3):
                n = coefficients.shape[axis]
                if boundary == 'nearest' or n == 1:
                    idx[axis] = np.clip(idx[axis], 0, n-1)
                else:
                    folded = idx[axis] % (2*(n-1))
                    idx[axis] = np.minimum(folded, 2*(n-1)-folded)
            values += coefficients[tuple(idx)]*weight
        result[inside] = values
    return result, inside


def _threshold(values, p):
    if p['mask_round_decimals'] is None:
        return values >= p['mask_threshold']
    return np.round(values, p['mask_round_decimals']) >= np.round(p['mask_threshold'], p['mask_round_decimals'])


def _prepare(source, p):
    data = source.data
    if p['antialias_sigma'] is not None:
        data = _gaussian(data, p['antialias_sigma'], p['antialias_dtype'], p['axis_order'],
                         p['gaussian_truncate'], p['antialias_boundary'])
    roi = (source.mask == source.label).astype(np.float64)
    lower_roi = upper_roi = None
    if p['mask_antialias_sigma'] is not None and not p['mask_skip']:
        roi = _gaussian(roi, p['mask_antialias_sigma'], p['antialias_dtype'], p['axis_order'],
                        p['gaussian_truncate'], p['mask_antialias_boundary'])
        if p['mask_threshold_after_antialias']:
            # Evaluate the engineering band in float64 even when the declared
            # producer stage is float32; sub-ULP bands must not silently vanish.
            lower_roi = _threshold(roi.astype(float)-p['mask_threshold_atol'], p).astype(float)
            upper_roi = _threshold(roi.astype(float)+p['mask_threshold_atol'], p).astype(float)
            roi = _threshold(roi, p).astype(float)
    coefficients = _coefficients(data, p['boundary'], p['axis_order']) if p['interpolation'] == 'bspline3' else None
    return data, roi, coefficients, lower_roi, upper_roi


def _integer_values(values, p):
    return np.trunc(values) if p['integer_cast'] == 'truncate' else np.copysign(np.floor(np.abs(values)+.5), values)


def _cast(values, p):
    if not np.all(np.isfinite(values)):
        raise ValueError('The declared operation produces nonfinite intensities')
    dtype = np.dtype(p['output_dtype'])
    if dtype.kind in 'iu':
        limits = np.iinfo(dtype)
        # ITK truncates; SciPy rounds half away from zero. Overflow/wrap/
        # saturation is deliberately outside these finite-range profiles.
        values = _integer_values(values, p)
        if np.any(values < limits.min) or np.any(values > limits.max):
            raise ValueError('Integer output overflow is outside the verified cast profile')
    out = values.astype(dtype)
    if not np.all(np.isfinite(out)):
        raise ValueError('The declared output cast overflows')
    return out


def _sample(prepared, q, p):
    data, roi, coefficients = prepared[:3]
    values, inside = _interpolate(data, q, p['interpolation'], p['boundary'], p['outside_value'], coefficients)
    values[inside] = values[inside]*p['intensity_gain']+p['intensity_offset']
    mask_values, _ = _interpolate(roi, q, 'nearest' if p['mask_skip'] else p['mask_interpolation'], p['mask_boundary'])
    return _cast(values, p), _threshold(mask_values, p), values, mask_values, inside


def expected_operation(source: Frame, spec: dict) -> Frame:
    """Nominal source-only plan; this function makes no acceptance decision."""
    p = _parse(source, spec)
    prepared = _prepare(source, p)
    data = np.empty(p['candidate_shape'], dtype=p['output_dtype'])
    mask = np.zeros(p['candidate_shape'], dtype=np.int16)
    for indices in base._blocks(p['candidate_shape']):
        q = p['index_map'][:3, :3] @ indices+p['index_map'][:3, 3, None]
        values, selected, _, _, _ = _sample(prepared, q, p)
        data[tuple(indices)] = values
        mask[tuple(indices)] = selected.astype(np.int16)*source.label
    return Frame(data, mask, p['expected_affine'], source.label)


def expected_mask(source: Frame, spec: dict) -> np.ndarray:
    """Nominal selected membership for a pre-production bounding-box plan."""
    p = _parse(source, spec)
    roi = (source.mask == source.label).astype(np.float64)
    if p['mask_antialias_sigma'] is not None and not p['mask_skip']:
        roi = _gaussian(roi, p['mask_antialias_sigma'], p['antialias_dtype'], p['axis_order'],
                        p['gaussian_truncate'], p['mask_antialias_boundary'])
        if p['mask_threshold_after_antialias']:
            roi = _threshold(roi, p).astype(float)
    out = np.empty(p['candidate_shape'], dtype=bool)
    for indices in base._blocks(p['candidate_shape']):
        q = p['index_map'][:3, :3] @ indices+p['index_map'][:3, 3, None]
        values, _ = _interpolate(roi, q, p['mask_interpolation'], p['mask_boundary'])
        out[tuple(indices)] = _threshold(values, p)
    return out


def _coverage(source, p):
    inverse = np.linalg.inv(p['index_map'])
    limit = np.asarray(p['candidate_shape'])[:, None]-.5
    band = p['index_boundary_atol']
    total = missing = uncertain = definite = start = 0
    for block in np.nditer(source.mask, flags=['external_loop', 'buffered'], op_flags=['readonly'],
                           order='C', buffersize=base._BLOCK_VOXELS):
        selected = np.flatnonzero(block == source.label)+start
        start += block.size
        total += selected.size
        if not selected.size:
            continue
        coords = np.array(np.unravel_index(selected, source.data.shape))
        q = inverse[:3, :3] @ coords+inverse[:3, 3, None]
        inside = np.all((q >= -.5) & (q < limit), axis=0)
        near = np.all((q >= -.5-band) & (q <= limit+band), axis=0) & np.any((np.abs(q+.5) <= band) | (np.abs(q-limit) <= band), axis=0)
        missing += int(np.count_nonzero(~inside))
        uncertain += int(np.count_nonzero(near))
        definite += int(np.count_nonzero(~inside & ~near))
    integral = base._integer_reindex(p['index_map'])
    return {'status': 'violated' if definite else 'indeterminate' if uncertain else 'satisfied',
            'definition': 'Selected source voxel centres in declared candidate [-0.5,size-0.5) FOV; not continuous anatomical support.',
            'source_roi_voxels': int(total), 'source_roi_outside_candidate_fov': missing,
            'source_roi_definitely_outside_candidate_fov': definite,
            'source_roi_centres_near_fov_boundary': uncertain,
            'missing_roi_voxels': missing if integral else None,
            'exact_roi_preserved': missing == 0 if integral else None}


def _alternatives(prepared, q, p, actual, actual_roi, nominal, nominal_roi, raw, mask_values):
    """Enumerate discontinuous boundary alternatives, never approve ambiguity."""
    n = q.shape[1]
    size = np.asarray(prepared[0].shape)[:, None]
    band = p['index_boundary_atol']
    ai = np.zeros(n, bool)
    ar = np.zeros(n, bool)
    ci = np.abs(actual.astype(float)-nominal.astype(float)) <= p['intensity_atol']
    cr = actual_roi == nominal_roi
    # Coordinate alternatives are used only at discontinuities. Smooth
    # interpolation does not become indeterminate merely for a tiny slope.
    image_ties = np.abs(q-(np.floor(q)+.5)) <= band if p['interpolation'] == 'nearest' else np.zeros(q.shape, bool)
    mask_ties = np.abs(q-(np.floor(q)+.5)) <= band if p['mask_interpolation'] == 'nearest' else np.zeros(q.shape, bool)
    image_edge = (np.abs(q+.5) <= band) | (np.abs(q-(size-.5)) <= band) if p['boundary'] == 'sitk' else np.zeros(q.shape, bool)
    if p['mask_boundary'] == 'sitk':
        mask_edge = (np.abs(q+.5) <= band) | (np.abs(q-(size-.5)) <= band)
    elif p['mask_boundary'] == 'constant':
        mask_edge = (np.abs(q) <= band) | (np.abs(q-(size-1.)) <= band)
    else:
        mask_edge = np.zeros(q.shape, bool)
    varying = image_ties | mask_ties | image_edge | mask_edge
    positions = np.flatnonzero(np.any(varying, axis=0))
    if positions.size:
        nominal_i = nominal[positions].astype(float)
        nominal_r = nominal_roi[positions]
        mini = maxi = nominal_i.copy()
        any_true = nominal_r.copy()
        any_false = ~nominal_r
        image_discontinuous = np.any(image_ties[:, positions] | image_edge[:, positions], axis=0)
        mask_discontinuous = np.any(mask_ties[:, positions] | mask_edge[:, positions], axis=0)
        for corner in product((-1., 1.), repeat=3):
            perturbed = q[:, positions].copy()
            for axis, sign in enumerate(corner):
                active = varying[axis, positions]
                # Move to either side of the declared engineering band.
                perturbed[axis, active] += sign*max(2.*band, 1e-14)
            values, selected, _, _, _ = _sample(prepared, perturbed, p)
            values = np.where(image_discontinuous, values.astype(float), nominal_i)
            selected = np.where(mask_discontinuous, selected, nominal_r)
            mini = np.minimum(mini, values)
            maxi = np.maximum(maxi, values)
            any_true |= selected
            any_false |= ~selected
            ci[positions] |= np.abs(actual[positions].astype(float)-values) <= p['intensity_atol']
            cr[positions] |= actual_roi[positions] == selected
            if prepared[3] is not None:
                lower_values, _ = _interpolate(prepared[3], perturbed, p['mask_interpolation'], p['mask_boundary'])
                upper_values, _ = _interpolate(prepared[4], perturbed, p['mask_interpolation'], p['mask_boundary'])
                lower = _threshold(lower_values-p['mask_threshold_atol'], p)
                upper = _threshold(upper_values+p['mask_threshold_atol'], p)
                any_true |= upper
                any_false |= ~lower
                cr[positions] |= (actual_roi[positions] == lower) | (actual_roi[positions] == upper)
        ai[positions] = (maxi-mini) > p['intensity_atol']
        ar[positions] = any_true & any_false
    if p['mask_interpolation'] == 'linear' or (p['mask_antialias_sigma'] is not None and not p['mask_threshold_after_antialias']):
        lower = _threshold(mask_values-p['mask_threshold_atol'], p)
        upper = _threshold(mask_values+p['mask_threshold_atol'], p)
        ar |= lower != upper
        cr |= (actual_roi == lower) | (actual_roi == upper)
    if prepared[3] is not None:
        # NN/linear interpolation and thresholding are monotone. Propagate the
        # lower/upper possible binary masks from the first threshold stage;
        # unresolved membership blocks approval, even when nominal agrees.
        low_values, _ = _interpolate(prepared[3], q, p['mask_interpolation'], p['mask_boundary'])
        high_values, _ = _interpolate(prepared[4], q, p['mask_interpolation'], p['mask_boundary'])
        lower = _threshold(low_values-p['mask_threshold_atol'], p)
        upper = _threshold(high_values+p['mask_threshold_atol'], p)
        ar |= lower != upper
        cr |= (actual_roi == lower) | (actual_roi == upper)
    if np.dtype(p['output_dtype']).kind in 'iu' and p['interpolation'] != 'nearest':
        lower = _integer_values(raw-p['output_cast_atol'], p)
        upper = _integer_values(raw+p['output_cast_atol'], p)
        ambiguous = lower != upper
        ai |= ambiguous
        ci |= ambiguous & ((np.abs(actual-lower) <= p['intensity_atol']) | (np.abs(actual-upper) <= p['intensity_atol']))
    return ai, ar, ci, cr


def verify_operation(source: Frame, candidate: Frame, spec: dict) -> dict:
    """Verify execution, centre coverage and reuse policy as separate outcomes.

    Unsupported declarations/invalid frames return unavailable; a supported
    candidate with wrong geometry/values/membership is violated. Expected input
    correspondence is never a claim of feature invariance or clinical validity.
    """
    try:
        p = _parse(source, spec)
        base._validate_observed(candidate)
        if tuple(candidate.data.shape) != p['candidate_shape']:
            return {'status': 'violated', 'checks': {'candidate_shape': False}, 'coverage': None,
                    'feature_reuse': {'decision': 'blocked'}, 'reason': 'Candidate shape differs from declaration'}
        corners = np.array(list(product(*[(0, n-1) for n in p['candidate_shape']]))).T
        delta = candidate.affine-p['expected_affine']
        position_error = float(np.max(np.linalg.norm(delta[:3, :3]@corners+delta[:3, 3, None], axis=0)))
        prepared = _prepare(source, p)
        counts = {k: 0 for k in ('nominal_mismatched_intensity_voxels', 'nominal_mismatched_roi_voxels',
                                 'ambiguous_intensity_voxels', 'ambiguous_roi_voxels', 'violating_intensity_voxels',
                                 'violating_roi_voxels', 'candidate_voxels_outside_source_support',
                                 'expected_candidate_roi_voxels', 'candidate_roi_voxels')}
        maximum_error = 0.
        for indices in base._blocks(p['candidate_shape']):
            q = p['index_map'][:3, :3]@indices+p['index_map'][:3, 3, None]
            values, selected, raw, mask_values, inside = _sample(prepared, q, p)
            actual = candidate.data[tuple(indices)]
            actual_roi = candidate.mask[tuple(indices)] == candidate.label
            error = np.abs(actual.astype(float)-values.astype(float))
            maximum_error = max(maximum_error, float(np.max(error)))
            bad_i = error > p['intensity_atol']
            bad_r = actual_roi != selected
            ai, ar, ci, cr = _alternatives(prepared, q, p, actual, actual_roi, values, selected, raw, mask_values)
            for key, array in (('nominal_mismatched_intensity_voxels', bad_i), ('nominal_mismatched_roi_voxels', bad_r),
                               ('ambiguous_intensity_voxels', ai), ('ambiguous_roi_voxels', ar),
                               ('violating_intensity_voxels', np.where(ai, ~ci, bad_i)),
                               ('violating_roi_voxels', np.where(ar, ~cr, bad_r)),
                               ('candidate_voxels_outside_source_support', ~inside),
                               ('expected_candidate_roi_voxels', selected), ('candidate_roi_voxels', actual_roi)):
                counts[key] += int(np.count_nonzero(array))
        coverage = _coverage(source, p)
        coverage.update({k: counts[k] for k in ('expected_candidate_roi_voxels', 'candidate_roi_voxels')})
        checks = {'candidate_shape': True, 'position': position_error <= p['position_atol_mm'],
                  'intensity': False if counts['violating_intensity_voxels'] else None if counts['ambiguous_intensity_voxels'] else True,
                  'roi': False if counts['violating_roi_voxels'] else None if counts['ambiguous_roi_voxels'] else True}
        status = 'violated' if any(v is False for v in checks.values()) else 'indeterminate' if any(v is None for v in checks.values()) else 'satisfied'
        blocked = status != 'satisfied' or coverage['status'] != 'satisfied' or counts['candidate_roi_voxels'] == 0
        reuse = {'decision': 'blocked' if blocked else 'requires_reextraction',
                 'reason': 'Execution and source-centre coverage are not established.' if blocked else
                           'Operator agreement does not establish feature invariance; re-extraction is required.'}
        declaration = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in p.items() if k != 'expected_affine'}
        declaration['intensity_rtol'] = 0.
        declaration['boundary_budget_scope'] = 'Declared engineering bands, not certified floating-point bounds or clinical tolerances.'
        return {'schema_version': 'operators-1.0', 'status': status, 'checks': checks,
                'max_corner_error_mm': position_error, 'max_intensity_error': maximum_error, **counts,
                'strict_nominal_status': 'satisfied' if checks['position'] and not counts['nominal_mismatched_intensity_voxels'] and not counts['nominal_mismatched_roi_voxels'] else 'violated',
                'coverage': coverage, 'feature_reuse': reuse, 'contract': declaration}
    except (ValueError, TypeError, OverflowError, FloatingPointError) as error:
        return {'schema_version': 'operators-1.0', 'status': 'unavailable', 'reason': str(error),
                'checks': {}, 'coverage': None, 'feature_reuse': {'decision': 'blocked'}}
