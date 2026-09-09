"""Conditional source-derived floating-point envelopes for native operators.

The nominal NumPy reference and its original decision are retained. This layer
does not adjust the declared intensity tolerance or estimate an error budget
from the observed output. A compatible but numerically unresolved relationship
is indeterminate, including when the output equals the nominal reference.

This is an explicit engineering model, not a certified proof of a whole native
backend: IEEE round-to-nearest arithmetic, normal finite intermediates, and
elementary kernel functions within two binary64 ulps are assumptions. The
coordinate model covers affine forward/inverse evaluation; it does not cover
unobserved preprocessing or arbitrary transformations.

ITK cubic tail definition, version 5.3.0 (tolerance 1e-10, horizon 18):
https://github.com/InsightSoftwareConsortium/ITK/blob/v5.3.0/Modules/Core/ImageFunction/include/itkBSplineDecompositionImageFilter.hxx
https://github.com/InsightSoftwareConsortium/ITK/blob/v5.3.0/Modules/Core/ImageFunction/include/itkBSplineDecompositionImageFilter.h
"""
from copy import deepcopy
from itertools import product
import math
import numpy as np
from . import operators as op

_U = np.finfo(np.float64).eps / 2.
_PROFILE = 'native-conditional-envelope-1'


def _gamma(n):
    nu = float(n)*_U
    if not 0 <= nu < .01:
        raise ValueError('Arithmetic count is outside the conditional envelope')
    return nu/(1.-nu)


def _cast_interval(raw, error, dtype):
    """Outward binary64 endpoints, then monotone declared storage conversion."""
    low = np.where(error == 0., raw, np.nextafter(raw-error, -np.inf))
    high = np.where(error == 0., raw, np.nextafter(raw+error, np.inf))
    with np.errstate(over='ignore', invalid='ignore'):
        low, high = low.astype(dtype).astype(float), high.astype(dtype).astype(float)
    if not np.all(np.isfinite(low)) or not np.all(np.isfinite(high)):
        raise ValueError('Envelope overflow is outside the numerical profile')
    return low, high


def _convolve(array, offsets, kernel, axis, boundary):
    out = np.zeros(array.shape, dtype=float)
    indices = np.arange(array.shape[axis])
    for offset, weight in zip(offsets, kernel):
        shifted = indices+offset
        values = np.take(array, np.clip(shifted, 0, len(indices)-1), axis=axis)
        if boundary == 'constant':
            shape = [1]*3
            shape[axis] = len(indices)
            values = values*((shifted >= 0) & (shifted < len(indices))).reshape(shape)
        out += weight*values
    return out


def _gaussian_envelope(array, sigma, dtype, order, truncate, boundary):
    """Propagate each separable stage and its output rounding before the next."""
    value = np.asarray(array, dtype=dtype)
    error = np.zeros(value.shape)
    if sigma is None:
        return value, error
    for axis in order:
        sd = sigma[axis]
        if sd <= 1e-15:
            continue
        radius = int(truncate*sd+.5)
        offsets = np.arange(-radius, radius+1)
        kernel = np.exp(-.5*(offsets/sd)**2)
        kernel /= kernel.sum()
        raw = _convolve(value.astype(float), offsets, kernel, axis, boundary)
        propagated = _convolve(error, offsets, kernel, axis, boundary)
        magnitude = _convolve(np.abs(value.astype(float))+error, offsets, kernel, axis, boundary)
        # Two evaluations: exponent/normalization budget plus K products/sums.
        # The 16 operations include kernel construction and the assumed libm
        # error; this model is explicitly conditional, not a libm certificate.
        radius_raw = propagated + 2.*_gamma(2*len(kernel)+16)*magnitude
        lo, hi = _cast_interval(raw, radius_raw, dtype)
        value = raw.astype(dtype)
        error = np.maximum(np.abs(lo-value.astype(float)), np.abs(hi-value.astype(float)))
    return value, error


def _axis_solve(values, axis, boundary, absolute=False):
    """The same interpolation equations; abs(A^-1) is an M-matrix solve."""
    y = np.moveaxis(np.asarray(values, dtype=float), axis, 0).copy()
    n = len(y)
    if n == 1:
        return np.moveaxis(y, 0, axis)
    y *= 6.
    diag = np.full(n, 4.)
    off = -1. if absolute else 1.
    upper = np.full(n-1, off)
    lower = np.full(n-1, off)
    if boundary == 'sitk':
        upper[0] *= 2.
        lower[-1] *= 2.
    else:
        diag[0] = diag[-1] = 5.
    for k in range(1, n):
        m = lower[k-1]/diag[k-1]
        diag[k] -= m*upper[k-1]
        y[k] -= m*y[k-1]
    y[-1] /= diag[-1]
    for k in range(n-2, -1, -1):
        y[k] = (y[k]-upper[k]*y[k+1])/diag[k]
    return np.moveaxis(y, 0, axis)


def _itk_tail(values, radius, axis):
    """Absolute causal-tail error propagated analytically to every coefficient."""
    x = np.moveaxis(np.abs(values)+radius, axis, 0)
    n = len(x)
    out = np.zeros(x.shape)
    r = abs(math.sqrt(3.)-2.)
    horizon = math.ceil(math.log(1e-10)/math.log(r))
    if n <= horizon:
        return np.moveaxis(out, 0, axis)
    powers = np.arange(n)
    denominator = 1.-r**(2*n-2)
    difference = np.empty(n)
    difference[0] = r**(2*n-2)/denominator
    for k in range(1, n-1):
        difference[k] = ((r**(k+2*n-2)+r**(2*n-2-k)) if k < horizon
                         else (r**k+r**(2*n-2-k)))/denominator
    difference[-1] = r**(n-1)/denominator
    initial = 6.*np.tensordot(difference, x, axes=(0, 0))
    response = (r**(powers+1)+r**(2*n-1-powers))/(1.-r*r)
    out = response.reshape((n,)+(1,)*(x.ndim-1))*initial
    return np.moveaxis(out, 0, axis)


def _coefficient_envelope(data, data_error, p, nominal):
    """Local tail plus propagated arithmetic/initial-storage uncertainty."""
    values = np.asarray(data, dtype=float)
    error = data_error.copy()
    boundary = p['boundary']
    if boundary == 'nearest':
        values = np.pad(values, 12, mode='edge')
        error = np.pad(error, 12, mode='edge')
    # ITK filters contiguous XYZ axes; nearest/SciPy uses declared array order.
    order = [0, 1, 2] if boundary == 'sitk' else p['axis_order']
    largest_tail = 0.
    for axis in order:
        n = values.shape[axis]
        if n == 1:
            continue
        tail = _itk_tail(values, error, axis) if boundary == 'sitk' else np.zeros(values.shape)
        largest_tail = max(largest_tail, float(tail.max()))
        propagated = _axis_solve(error, axis, boundary, absolute=True)
        local_size = np.max(np.abs(values)+error, axis=axis, keepdims=True)
        # <= 8N+32 scalar ops covers both direct and recursive 1D evaluations;
        # ||A^-1||inf <= 3 for the normalized mirror/reflect equations.
        arithmetic = 2.*_gamma(8*n+32)*3.*local_size
        values = _axis_solve(values, axis, boundary)
        error = propagated+tail+arithmetic
    # A different direct-solve axis order is source-only, never candidate-derived.
    error += np.abs(values-nominal)
    return error, largest_tail


def _coordinate_radius(source, p, indices, q):
    """Conditional affine product/inversion envelope in source-index units."""
    a, b = source.affine, p['index_map']
    m = a[:3, :3]
    inverse = np.linalg.inv(m)
    residual = np.abs(np.eye(3)-inverse@m)+_gamma(3)*(np.abs(inverse)@np.abs(m))
    rho = np.linalg.norm(residual, ord=np.inf)
    if not np.isfinite(rho) or rho >= .01:
        raise ValueError('Affine inversion is outside the numerical profile')
    inverse_error = rho/(1.-rho)*np.linalg.norm(inverse, ord=np.inf)
    j = np.vstack((indices, np.ones(indices.shape[1])))
    # Both forming A B and evaluating its point, subtraction of the origin,
    # inversion, and direct B j evaluation are included.
    physical_magnitude = np.abs(a)@np.abs(b)@np.abs(j)
    physical_error = 2.*_gamma(4)*physical_magnitude[:3]
    translated_magnitude = np.abs(m)@np.abs(q)
    inverse_round = _gamma(4)*(np.abs(inverse)@(physical_magnitude[:3]+np.abs(a[:3, 3, None])))
    inverse_uncertainty = inverse_error*np.max(translated_magnitude, axis=0)
    direct_round = _gamma(4)*(np.abs(b)@np.abs(j))[:3]
    return np.abs(inverse)@physical_error+inverse_round+inverse_uncertainty+direct_round


def _gradient_limits(array, radius=None):
    # Per-axis Lipschitz constants. Linear interpolation uses voxel differences;
    # cardinal cubic derivatives use adjacent coefficient differences.
    limits = []
    for axis in range(3):
        if array.shape[axis] == 1:
            limits.append(0.)
            continue
        differences = np.abs(np.diff(array, axis=axis))
        if radius is not None:
            differences += (np.take(radius, np.arange(array.shape[axis]-1), axis=axis)
                            + np.take(radius, np.arange(1, array.shape[axis]), axis=axis))
        limits.append(float(differences.max()))
    return np.asarray(limits)


def _image_interval(prepared, field_error, q, q_error, p):
    data, _, coefficients = prepared[:3]
    raw, inside = op._interpolate(data, q, p['interpolation'], p['boundary'], p['outside_value'], coefficients)
    field = data if coefficients is None else coefficients
    e, _ = op._interpolate(field_error if coefficients is None else data, q,
                          p['interpolation'], p['boundary'], 0.,
                          None if coefficients is None else field_error)
    magnitude, _ = op._interpolate(np.abs(data), q, p['interpolation'], p['boundary'], 0.,
                                   None if coefficients is None else np.abs(coefficients))
    operations = 16 if coefficients is None else 128
    arithmetic = 2.*_gamma(operations)*magnitude
    coordinate = _gradient_limits(field, field_error)@q_error
    radius = e+arithmetic+coordinate
    radius[~inside] = 0.
    lo, hi = _cast_interval(raw, radius, p['output_dtype'])
    return lo, hi, radius


def _mask_fields(source, p):
    roi = (source.mask == source.label).astype(float)
    if p['mask_skip'] or p['mask_antialias_sigma'] is None:
        return roi, roi, 0.
    value, error = _gaussian_envelope(roi, p['mask_antialias_sigma'], p['antialias_dtype'],
                                     p['axis_order'], p['gaussian_truncate'], p['mask_antialias_boundary'])
    lo, hi = _cast_interval(value.astype(float), error, p['antialias_dtype'])
    if p['mask_threshold_after_antialias']:
        # Retain the declared six-decimal threshold and bracket the native
        # float32 decimal-rounding arithmetic as well as binary storage.
        rounding = (3.*np.finfo(np.float32).eps*np.maximum(np.abs(lo), np.abs(hi))
                    if p['antialias_dtype'] == 'float32' and p['mask_round_decimals'] is not None else 0.)
        lo = op._threshold(lo-rounding-p['mask_threshold_atol'], p).astype(float)
        hi = op._threshold(hi+rounding+p['mask_threshold_atol'], p).astype(float)
    return lo, hi, float(error.max())


def _unavailable(nominal, reason):
    result = deepcopy(nominal)
    demonstrated_geometry_fault = any(nominal.get('checks', {}).get(k) is False
                                      for k in ('candidate_shape', 'position', 'output_dtype'))
    result.update(status='violated' if demonstrated_geometry_fault else 'unavailable', reason=reason, nominal_reference=nominal,
                  numerical_envelope={'profile': _PROFILE, 'status': 'unavailable', 'reason': reason})
    result['checks'] = dict(result.get('checks', {}), numerical_profile=None)
    result['feature_reuse'] = {'decision': 'blocked', 'reason': reason}
    return result


def verify_native_operation(source, candidate, spec):
    """Observe a declared native relationship under a source-only error model.

    Preserves nominal_reference. Bounds do not establish clinical validity or
    validate implementation paths that the adapter did not actually observe.
    """
    nominal = op.verify_operation(source, candidate, spec)
    if nominal['status'] == 'unavailable' or nominal.get('checks', {}).get('candidate_shape') is False:
        return nominal
    try:
        p = op._parse(source, spec)
        if not np.array_equal(p['world_map'], np.eye(4)):
            return _unavailable(nominal, 'The numerical coordinate profile covers identity world_map only')
        if p['intensity_gain'] != 1. or p['intensity_offset'] != 0.:
            return _unavailable(nominal, 'The numerical profile covers unit gain and zero offset only')
        if str(candidate.data.dtype) != p['output_dtype']:
            result = deepcopy(nominal)
            result.update(status='violated', nominal_reference=nominal,
                          reason='Candidate storage dtype differs from the declared native output')
            result['checks']['output_dtype'] = False
            result['feature_reuse'] = {'decision': 'blocked'}
            return result
        # Exact selection/casting has no weighted arithmetic to bound. Existing
        # discontinuous coordinate and storage policies remain fully visible.
        exact_selection = (p['interpolation'] == 'nearest' and p['antialias_sigma'] is None
                           and (p['mask_skip'] or (p['mask_antialias_sigma'] is None
                                                  and p['mask_interpolation'] == 'nearest')))
        if exact_selection:
            coordinate_max = 0.
            for indices in op.base._blocks(p['candidate_shape']):
                q = p['index_map'][:3, :3]@indices+p['index_map'][:3, 3, None]
                coordinate_max = max(coordinate_max, float(_coordinate_radius(source, p, indices, q).max()))
            if coordinate_max > p['index_boundary_atol']:
                return _unavailable(nominal, 'Source-derived coordinate radius exceeds the declared boundary band')
            result = deepcopy(nominal)
            result['nominal_reference'] = nominal
            result['numerical_envelope'] = {'profile': _PROFILE, 'status': 'exact_selection',
                                           'max_coordinate_radius_voxels': coordinate_max,
                                           'scope': 'Existing nearest-neighbour coordinate and cast policies'}
            return result
        if p['output_dtype'] not in ('float32', 'float64'):
            return _unavailable(nominal, 'Weighted integer output is outside the floating-point envelope')
        magnitude = np.abs(source.data.astype(float))
        if np.any((magnitude > 0.) & (magnitude < np.finfo(np.float64).tiny)):
            return _unavailable(nominal, 'Subnormal binary64 source values are outside the normal-arithmetic profile')
        if not np.all(np.isfinite(source.data)) or np.max(np.abs(source.data.astype(float))) > 1e100:
            return _unavailable(nominal, 'Source magnitude is outside the normal finite arithmetic profile')
        prepared = op._prepare(source, p)
        if p['antialias_sigma'] is None:
            data_error = np.zeros(source.data.shape)
        else:
            data, data_error = _gaussian_envelope(source.data, p['antialias_sigma'], p['antialias_dtype'],
                                                p['axis_order'], p['gaussian_truncate'], p['antialias_boundary'])
            if not np.array_equal(data, prepared[0]):
                return _unavailable(nominal, 'Gaussian envelope and nominal stage differ')
        field_error, tail_max = data_error, 0.
        if p['interpolation'] == 'bspline3':
            field_error, tail_max = _coefficient_envelope(prepared[0], data_error, p, prepared[2])
        roi_low, roi_high, mask_aa_max = _mask_fields(source, p)
        counts = dict(ambiguous_intensity_voxels=0, ambiguous_roi_voxels=0,
                      violating_intensity_voxels=0, violating_roi_voxels=0)
        raw_max = width_max = coordinate_max = 0.
        for indices in op.base._blocks(p['candidate_shape']):
            q = p['index_map'][:3, :3]@indices+p['index_map'][:3, 3, None]
            qe = _coordinate_radius(source, p, indices, q)
            coordinate_max = max(coordinate_max, float(qe.max()))
            if coordinate_max > p['index_boundary_atol']:
                return _unavailable(nominal, 'Source-derived coordinate radius exceeds the declared boundary band')
            values, selected, raw, mask_values, _ = op._sample(prepared, q, p)
            actual = candidate.data[tuple(indices)].astype(float)
            actual_roi = candidate.mask[tuple(indices)] == candidate.label
            ai, ar, ci, cr = op._alternatives(prepared, q, p, actual, actual_roi, values, selected, raw, mask_values)
            lo, hi, radius = _image_interval(prepared, field_error, q, qe, p)
            # Outer half-voxel and NN boundaries are discontinuous. Include
            # both side envelopes, including uncertain intermediate storage.
            size = np.asarray(source.data.shape)[:, None]
            near = ((np.abs(q+.5) <= p['index_boundary_atol']) |
                    (np.abs(q-(size-.5)) <= p['index_boundary_atol'])) if p['boundary'] == 'sitk' else np.zeros(q.shape, bool)
            if p['interpolation'] == 'nearest':
                near |= np.abs(q-(np.floor(q)+.5)) <= p['index_boundary_atol']
            positions = np.flatnonzero(np.any(near, axis=0))
            if positions.size:
                for signs in product((-1., 1.), repeat=3):
                    shifted = q[:, positions]+np.asarray(signs)[:, None]*near[:, positions]*max(2*p['index_boundary_atol'], 1e-14)
                    ll, hh, _ = _image_interval(prepared, field_error, shifted, qe[:, positions], p)
                    lo[positions] = np.minimum(lo[positions], ll)
                    hi[positions] = np.maximum(hi[positions], hh)
            compatible = (actual >= lo-p['intensity_atol']) & (actual <= hi+p['intensity_atol'])
            stable = (np.abs(actual-lo) <= p['intensity_atol']) & (np.abs(actual-hi) <= p['intensity_atol'])
            ambiguous = (hi-lo > p['intensity_atol']) | (compatible & ~stable) | ai
            # Existing boundary alternatives remain a separate, visible reason
            # for abstention; their compatible membership never produces pass.
            compatible |= ai & ci
            low_values, _ = op._interpolate(roi_low, q, 'nearest' if p['mask_skip'] else p['mask_interpolation'], p['mask_boundary'])
            high_values, _ = op._interpolate(roi_high, q, 'nearest' if p['mask_skip'] else p['mask_interpolation'], p['mask_boundary'])
            mask_radius = 2.*_gamma(16)+np.maximum(_gradient_limits(roi_low), _gradient_limits(roi_high))@qe
            lower = op._threshold(low_values-mask_radius-p['mask_threshold_atol'], p)
            upper = op._threshold(high_values+mask_radius+p['mask_threshold_atol'], p)
            mask_ambiguous = (lower != upper) | ar
            mask_compatible = (actual_roi == lower) | (actual_roi == upper) | (ar & cr)
            counts['ambiguous_intensity_voxels'] += int(np.count_nonzero(ambiguous))
            counts['violating_intensity_voxels'] += int(np.count_nonzero(~compatible))
            counts['ambiguous_roi_voxels'] += int(np.count_nonzero(mask_ambiguous))
            counts['violating_roi_voxels'] += int(np.count_nonzero(~mask_compatible))
            raw_max = max(raw_max, float(radius.max()))
            width_max = max(width_max, float((hi-lo).max()))
        result = deepcopy(nominal)
        result['nominal_reference'] = nominal
        result.update(counts)
        checks = dict(result['checks'])
        checks['intensity'] = False if counts['violating_intensity_voxels'] else None if counts['ambiguous_intensity_voxels'] else True
        checks['roi'] = False if counts['violating_roi_voxels'] else None if counts['ambiguous_roi_voxels'] else True
        result['checks'] = checks
        result['status'] = 'violated' if any(v is False for v in checks.values()) else 'indeterminate' if any(v is None for v in checks.values()) else 'satisfied'
        result['schema_version'] = _PROFILE
        result['numerical_envelope'] = {
            'profile': _PROFILE, 'status': 'evaluated', 'candidate_used_to_set_bounds': False,
            'formal_backend_certificate': False, 'intensity_atol_unchanged': p['intensity_atol'],
            'max_precast_radius': raw_max, 'max_storage_interval_width': width_max,
            'max_coordinate_radius_voxels': coordinate_max, 'max_image_antialias_radius': float(data_error.max()),
            'max_mask_antialias_radius': mask_aa_max, 'max_single_axis_itk_tail_radius': tail_max,
            'itk_cubic_horizon': 18 if p['interpolation'] == 'bspline3' and p['boundary'] == 'sitk' else None,
            'assumptions': ['IEEE round-to-nearest, normal finite binary64 intermediates',
                'Elementary Gaussian kernel functions within two binary64 ulps',
                'Declared affine forward/inverse evaluation and observed checkpoint only',
                'ITK 5.3 mirror cubic causal initialization tolerance 1e-10 when boundary=sitk',
                'Intermediate Gaussian storage and threshold uncertainty propagated',
                'Conditional arithmetic operation budgets; not a formal native-backend proof']}
        blocked = result['status'] != 'satisfied' or result['coverage']['status'] != 'satisfied' or result['candidate_roi_voxels'] == 0
        result['feature_reuse'] = {'decision': 'blocked' if blocked else 'requires_reextraction',
                                  'reason': 'Execution or coverage is unresolved.' if blocked else 'Operator agreement does not establish feature invariance.'}
        return result
    except (ValueError, TypeError, OverflowError, FloatingPointError) as error:
        return _unavailable(nominal, str(error))
