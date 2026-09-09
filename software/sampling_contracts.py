"""Independent verification of a declared nearest/linear sampling operation.

Arrays are XYZ, voxel centres map to RAS millimetres. The caller declares B
(candidate indices -> source indices) BEFORE running the operator. The expected
candidate affine is L @ source.affine @ B; B is never inferred from candidate
metadata. No SimpleITK/SciPy interpolation code is used by this module.

Required spec fields: index_map, candidate_shape, interpolation (nearest/linear),
outside_value, position_atol_mm, intensity_atol. Optional: world_map (identity),
intensity_gain (1), intensity_offset (0), mask_outside (only 0 is supported).
index_boundary_atol defaults to 1e-9 source/candidate index units and is an
explicit indeterminacy band, NOT a permission to accept a different neighbor.
Inside support, expected intensity is gain * interpolated_source + offset.
outside_value is already in FINAL decoded intensity units.

Support is [-0.5, size-0.5) on every source axis. Nearest uses floor(i+0.5).
Linear clamps coordinates to the first/last centre within this half-voxel rim.
Outside support uses the declared intensity and background ROI. Selected ROI
membership always uses nearest sampling, independently of image interpolation.
Within the boundary band, differing possible neighbors/fill cause an
indeterminate_boundary result if compatible with the observation; incompatible
observations still violate. Strict nominal discrepancies remain reported.

Sampling agreement, coverage of source ROI CENTRES in the declared candidate
field of view, and possible measurement reuse are separate results. Coverage
does not assert conservation of continuous anatomical support or volume.
"""
from itertools import product
import math
import numpy as np
from physical_contracts import Frame


_BLOCK_VOXELS = 131072


def _affine(value, name):
    if np.iscomplexobj(value):
        raise ValueError(name + ' must be a real affine')
    matrix = np.asarray(value, dtype=np.float64)
    if (matrix.shape != (4, 4) or not np.all(np.isfinite(matrix))
            or not np.array_equal(matrix[3], [0., 0., 0., 1.])
            or abs(np.linalg.det(matrix[:3, :3])) < 1e-12):
        raise ValueError(name + ' must be finite, affine and nonsingular')
    return matrix


def _real(value, name, nonnegative=False, positive=False):
    if isinstance(value, (bool, np.bool_)) or np.iscomplexobj(value):
        raise ValueError(name + ' must be a finite real number')
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(name + ' must be a finite real number') from error
    if not math.isfinite(value) or (nonnegative and value < 0) or (positive and value <= 0):
        raise ValueError(name + ' is outside the supported domain')
    return value


def _blocks(shape):
    count = math.prod(shape)
    for start in range(0, count, _BLOCK_VOXELS):
        yield np.array(np.unravel_index(
            np.arange(start, min(start + _BLOCK_VOXELS, count), dtype=np.int64), shape))


def _validate_observed(frame):
    """The candidate may have lost its entire selected ROI; retain that evidence."""
    if np.any(frame.mask == frame.label):
        return frame.validate()
    if frame.mask.shape != frame.data.shape or np.iscomplexobj(frame.mask):
        raise ValueError('The candidate mask must be real and match the image shape')
    for block in np.nditer(frame.mask, flags=['external_loop', 'buffered', 'zerosize_ok'],
                           op_flags=['readonly'], order='C', buffersize=_BLOCK_VOXELS):
        if (not np.all(np.isfinite(block)) or np.any(block < -32768) or np.any(block > 32767)
                or not np.all(block == block.astype(np.int16))):
            raise ValueError('Candidate mask values must be finite int16 integers')
    # A broadcast view supplies only the nonempty-ROI precondition to the
    # frozen validator. Original mask values were checked above; never alter it.
    proxy = np.broadcast_to(np.asarray(frame.label), frame.data.shape)
    Frame(frame.data, proxy, frame.affine, frame.label, frame.slope, frame.intercept).validate()
    return frame


def _integer_reindex(matrix):
    p = matrix[:3, :3]
    return bool(np.all(np.isin(p, [-1., 0., 1.]))
                and np.all(np.abs(p).sum(0) == 1)
                and np.all(np.abs(p).sum(1) == 1)
                and np.all(matrix[:3, 3] == np.rint(matrix[:3, 3])))


def _sample(source, coordinates, interpolation, outside, gain, offset):
    """Expected values for one block; selected membership is always nearest."""
    size = np.asarray(source.data.shape)[:, None]
    inside = np.all((coordinates >= -0.5) & (coordinates < size - 0.5), axis=0)
    expected = np.full(coordinates.shape[1], outside, dtype=np.float64)
    selected = np.zeros(coordinates.shape[1], dtype=bool)
    q = coordinates[:, inside]
    if q.shape[1]:
        nearest = np.floor(q + 0.5).astype(np.int64)
        nearest = np.clip(nearest, 0, size - 1)
        selected[inside] = source.mask[tuple(nearest)] == source.label
        if interpolation == 'nearest':
            values = np.asarray(source.data[tuple(nearest)], dtype=np.float64)
        else:
            q = np.clip(q, 0., size - 1.)
            low = np.floor(q).astype(np.int64)
            high = np.minimum(low + 1, size - 1)
            fraction = q - low
            values = np.zeros(q.shape[1], dtype=np.float64)
            for corner in product((0, 1), repeat=3):
                indices = tuple(high[k] if corner[k] else low[k] for k in range(3))
                weight = np.prod(np.array([fraction[k] if corner[k] else 1. - fraction[k]
                                           for k in range(3)]), axis=0)
                values += np.asarray(source.data[indices], dtype=np.float64) * weight
        expected[inside] = gain * values + offset
    if not np.all(np.isfinite(expected)):
        raise ValueError('The declared sampling produces nonfinite expected intensities')
    return expected, selected, int(np.count_nonzero(~inside))


def _boundary_options(source, coordinates, interpolation, outside, gain, offset,
                      band, actual, actual_roi, intensity_atol):
    """Finite neighboring alternatives only; ambiguity NEVER becomes satisfaction.

    At an NN decision plane there are at most two source indices per axis.
    A source index outside the image denotes declared fill/background. For
    linear intensity, only inside/outside support is discontinuous; the inner
    half-voxel rim is clamped. Possible values are discrete alternatives, not
    a min/max acceptance interval.
    """
    size = np.asarray(source.data.shape)[:, None]
    boundary = np.floor(coordinates) + .5
    near = np.abs(coordinates - boundary) <= band
    reachable = np.all((coordinates >= -.5-band) & (coordinates <= size-.5+band), axis=0)
    positions = np.flatnonzero(np.any(near, axis=0) & reachable)
    ambiguous_i = np.zeros(coordinates.shape[1], dtype=bool)
    ambiguous_r = ambiguous_i.copy()
    compatible_i = np.ones(coordinates.shape[1], dtype=bool)
    compatible_r = compatible_i.copy()
    if not positions.size:
        return ambiguous_i, ambiguous_r, compatible_i, compatible_r
    q = coordinates[:, positions]
    tied = near[:, positions]
    usual = np.floor(q+.5).astype(np.int64)
    low = np.where(tied, np.floor(q).astype(np.int64), usual)
    high = np.where(tied, low+1, usual)
    found_roi = np.zeros(positions.size, dtype=bool)
    found_background = np.zeros(positions.size, dtype=bool)
    min_i = np.full(positions.size, np.inf)
    max_i = np.full(positions.size, -np.inf)
    compatible = np.zeros(positions.size, dtype=bool)
    for corner in product((0, 1), repeat=3):
        indices = np.array([high[k] if corner[k] else low[k] for k in range(3)])
        inside = np.all((indices >= 0) & (indices < size), axis=0)
        selected = np.zeros(positions.size, dtype=bool)
        selected[inside] = source.mask[tuple(indices[:, inside])] == source.label
        found_roi |= selected
        found_background |= ~selected
        if interpolation == 'nearest':
            values = np.full(positions.size, outside)
            values[inside] = gain*np.asarray(source.data[tuple(indices[:, inside])], dtype=float)+offset
            min_i = np.minimum(min_i, values)
            max_i = np.maximum(max_i, values)
            compatible |= np.abs(actual[positions]-values) <= intensity_atol
    ambiguous_r[positions] = found_roi & found_background
    compatible_r[positions] = np.where(actual_roi[positions], found_roi, found_background)
    if interpolation == 'linear':
        support_edge = np.any((np.abs(q+.5) <= band) | (np.abs(q-(size-.5)) <= band), axis=0)
        # A point at a support boundary can evaluate to fill or to the clamped
        # inner-rim limit. Interior NN label ties do not change linear intensity.
        clamped = np.clip(q, 0., size-1.)
        inner, _, _ = _sample(source, clamped, 'linear', outside, gain, offset)
        min_i = np.where(support_edge, np.minimum(inner, outside), inner)
        max_i = np.where(support_edge, np.maximum(inner, outside), inner)
        compatible = (np.abs(actual[positions]-inner) <= intensity_atol) | (
            support_edge & (np.abs(actual[positions]-outside) <= intensity_atol))
    ambiguous_i[positions] = min_i != max_i
    compatible_i[positions] = compatible
    return ambiguous_i, ambiguous_r, compatible_i, compatible_r


def sampling_witness(source: Frame, observed: Frame, spec: dict) -> dict:
    """Check execution and report coverage/reuse separately; invalid inputs raise.

    No feature equality or clinical correctness is inferred. A correctly executed
    crop can lose source ROI support: sampling may satisfy while reuse is blocked.
    General resampling can change the selected voxel count legitimately; only
    integral signed reindex/crop/pad maps receive an exact missing-ROI count.
    All comparisons are absolute (intensity rtol=0). Scratch arrays are bounded
    by _BLOCK_VOXELS, in addition to the caller-owned source and candidate arrays.
    """
    source.validate()
    _validate_observed(observed)
    required = {'index_map', 'candidate_shape', 'interpolation', 'outside_value',
                'position_atol_mm', 'intensity_atol'}
    if not isinstance(spec, dict) or not required <= spec.keys():
        raise ValueError('The sampling declaration is missing required fields')
    b = _affine(spec['index_map'], 'index_map')
    world = _affine(spec.get('world_map', np.eye(4)), 'world_map')
    shape = spec['candidate_shape']
    if (not isinstance(shape, (list, tuple)) or len(shape) != 3
            or any(isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer))
                   or n <= 0 for n in shape)):
        raise ValueError('candidate_shape must contain three positive integers')
    shape = tuple(int(n) for n in shape)
    if math.prod(shape) > np.iinfo(np.int64).max:
        raise ValueError('The declared array size is outside the supported domain')
    interpolation = spec['interpolation']
    if interpolation not in ('nearest', 'linear'):
        raise ValueError('Only nearest and linear image interpolation are supported')
    if isinstance(spec.get('mask_outside', 0), (bool, np.bool_)) or spec.get('mask_outside', 0) != 0:
        raise ValueError('Only background mask_outside=0 is supported')
    outside = _real(spec['outside_value'], 'outside_value')
    gain = _real(spec.get('intensity_gain', 1.), 'intensity_gain', positive=True)
    offset = _real(spec.get('intensity_offset', 0.), 'intensity_offset')
    position_atol = _real(spec['position_atol_mm'], 'position_atol_mm', nonnegative=True)
    intensity_atol = _real(spec['intensity_atol'], 'intensity_atol', nonnegative=True)
    boundary_atol = _real(spec.get('index_boundary_atol', 1e-9), 'index_boundary_atol', nonnegative=True)
    if boundary_atol >= .25:
        raise ValueError('index_boundary_atol must be less than 0.25 index units')
    expected_affine = world @ source.affine @ b
    # Reuse the established physical domain, including orthogonal axes.
    _validate_observed(Frame(observed.data, observed.mask, expected_affine, observed.label))
    declared = {'interpolation': interpolation, 'outside_value': outside, 'mask_outside': 0,
                'position_atol_mm': position_atol, 'intensity_atol': intensity_atol,
                'intensity_rtol': 0., 'index_boundary_atol': boundary_atol,
                'support': 'source indices in [-0.5, size-0.5)',
                'nearest_ties': 'nominal floor(index+0.5); differing boundary alternatives are indeterminate, never satisfied',
                'linear_rim': 'clamp to edge centres',
                'boundary_budget_scope': 'Declared engineering band in index units, not a certified floating-point bound or a clinical tolerance.'}
    if observed.data.shape != shape:
        return {'schema_version': 'sampling-1.0', 'status': 'violated',
                'checks': {'candidate_shape': False}, 'reason': 'candidate shape differs from declaration',
                'coverage': None, 'feature_reuse': {'decision': 'blocked', 'reason': 'sampling disagrees'},
                'contract': declared}
    corners = np.array(list(product(*[(0, n - 1) for n in shape])), dtype=np.float64).T
    displacement = ((observed.affine[:3, :3] - expected_affine[:3, :3]) @ corners
                    + (observed.affine[:3, 3] - expected_affine[:3, 3])[:, None])
    position_error = float(np.max(np.linalg.norm(displacement, axis=0)))
    maximum_error = 0.
    mismatched_roi = 0
    nominal_intensity_mismatches = 0
    violating_intensity = 0
    violating_roi = 0
    ambiguous_intensity = 0
    ambiguous_roi = 0
    expected_roi_count = 0
    candidate_roi_count = 0
    outside_samples = 0
    with np.errstate(over='raise', invalid='raise'):
        for indices in _blocks(shape):
            coordinates = b[:3, :3] @ indices + b[:3, 3, None]
            expected, selected, count = _sample(source, coordinates, interpolation, outside, gain, offset)
            actual = observed.data[tuple(indices)]
            actual_roi = observed.mask[tuple(indices)] == observed.label
            errors = np.abs(actual - expected)
            maximum_error = max(maximum_error, float(np.max(errors)))
            bad_i = errors > intensity_atol
            bad_r = actual_roi != selected
            nominal_intensity_mismatches += int(np.count_nonzero(bad_i))
            mismatched_roi += int(np.count_nonzero(bad_r))
            ai, ar, ci, cr = _boundary_options(source, coordinates, interpolation, outside,
                                               gain, offset, boundary_atol, actual, actual_roi, intensity_atol)
            bad_i[ai] = ~ci[ai]
            bad_r[ar] = ~cr[ar]
            violating_intensity += int(np.count_nonzero(bad_i))
            violating_roi += int(np.count_nonzero(bad_r))
            ambiguous_intensity += int(np.count_nonzero(ai))
            ambiguous_roi += int(np.count_nonzero(ar))
            expected_roi_count += int(np.count_nonzero(selected))
            candidate_roi_count += int(np.count_nonzero(actual_roi))
            outside_samples += count
    inverse = np.linalg.inv(b)
    source_roi = 0
    missing_centres = 0
    ambiguous_fov_centres = 0
    definitely_missing_centres = 0
    # Traverse the mask in bounded C-order buffers, including noncontiguous
    # input views. Only selected ROI voxels need coordinate arrays/inversion.
    start = 0
    for mask_block in np.nditer(source.mask, flags=['external_loop', 'buffered'],
                               op_flags=['readonly'], order='C', buffersize=_BLOCK_VOXELS):
        selected = np.flatnonzero(mask_block == source.label) + start
        start += mask_block.size
        source_roi += int(selected.size)
        if not selected.size:
            continue
        indices = np.array(np.unravel_index(selected, source.data.shape))
        destination = inverse[:3, :3] @ indices + inverse[:3, 3, None]
        inside = np.all((destination >= -0.5) & (destination < np.asarray(shape)[:, None] - 0.5), axis=0)
        missing_centres += int(np.count_nonzero(~inside))
        within_band = np.all((destination >= -.5-boundary_atol) &
                             (destination <= np.asarray(shape)[:, None]-.5+boundary_atol), axis=0)
        near_boundary = np.any((np.abs(destination+.5) <= boundary_atol) |
                               (np.abs(destination-(np.asarray(shape)[:, None]-.5)) <= boundary_atol), axis=0)
        uncertain = within_band & near_boundary
        ambiguous_fov_centres += int(np.count_nonzero(uncertain))
        definitely_missing_centres += int(np.count_nonzero(~inside & ~uncertain))
    integral = _integer_reindex(b)
    coverage_status = 'violated' if definitely_missing_centres else 'indeterminate_boundary' if ambiguous_fov_centres else 'satisfied'
    coverage = {'status': coverage_status,
                'definition': 'Source selected-ROI voxel centres mapped by declared B inverse into candidate [-0.5,size-0.5) FOV; not continuous anatomical support.',
                'source_roi_voxels': source_roi,
                'source_roi_outside_candidate_fov': missing_centres,
                'source_roi_definitely_outside_candidate_fov': definitely_missing_centres,
                'source_roi_centres_near_fov_boundary': ambiguous_fov_centres,
                'expected_candidate_roi_voxels': expected_roi_count,
                'candidate_roi_voxels': candidate_roi_count,
                'missing_roi_voxels': missing_centres if integral else None,
                'exact_roi_preserved': missing_centres == 0 if integral else None,
                'exact_roi_scope': 'Declared integral mapping only; observed correspondence is checked separately.'}
    checks = {'candidate_shape': True, 'position': position_error <= position_atol,
              'intensity': False if violating_intensity else None if ambiguous_intensity else True,
              'roi': False if violating_roi else None if ambiguous_roi else True}
    status = 'violated' if any(v is False for v in checks.values()) else (
        'indeterminate_boundary' if any(v is None for v in checks.values()) else 'satisfied')
    if status != 'satisfied':
        reuse = {'decision': 'blocked', 'reason': 'Sampling is violated or boundary-indeterminate; no approval or feature reuse is inferred.'}
    elif coverage_status == 'indeterminate_boundary':
        reuse = {'decision': 'blocked', 'reason': 'Source ROI centre coverage is boundary-indeterminate.'}
    elif missing_centres:
        reuse = {'decision': 'blocked', 'reason': 'The declared candidate FOV excludes source ROI voxel centres.'}
    elif not candidate_roi_count:
        reuse = {'decision': 'blocked', 'reason': 'The sampled candidate contains no selected ROI voxels.'}
    elif integral and interpolation == 'nearest' and np.array_equal(world, np.eye(4)) and gain == 1. and offset == 0.:
        reuse = {'decision': 'input_roi_preserved', 'reason': 'Integral-grid selected-input correspondence within declared tolerances; measurement reuse still depends on feature, settings and context/halo requirements. No universal feature equality is asserted.'}
    else:
        reuse = {'decision': 'requires_reextraction', 'reason': 'Sampling or physical/intensity change has no assigned feature-reuse equality; correct execution does not imply feature invariance.'}
    return {'schema_version': 'sampling-1.0', 'status': status,
            'checks': checks, 'max_corner_error_mm': position_error,
            'max_intensity_error': maximum_error, 'mismatched_roi_voxels': mismatched_roi,
            'strict_nominal_status': 'satisfied' if position_error <= position_atol and not nominal_intensity_mismatches and not mismatched_roi else 'violated',
            'nominal_mismatched_intensity_voxels': nominal_intensity_mismatches,
            'nominal_mismatched_roi_voxels': mismatched_roi,
            'ambiguous_intensity_voxels': ambiguous_intensity,
            'ambiguous_roi_voxels': ambiguous_roi,
            'violating_intensity_voxels': violating_intensity,
            'violating_roi_voxels': violating_roi,
            'candidate_voxels_outside_source_support': outside_samples,
            'coverage': coverage, 'feature_reuse': reuse, 'contract': declared}
