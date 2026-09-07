"""Prespecified held-out faults in owned adapters, not third-party libraries.

Payload arrays use XYZ indexing; affine maps indices to RAS coordinates.
Data ALWAYS contains decoded physical intensities. The downstream writer
encodes stored=(data-intercept)/slope and records both calibration fields.
This module does not read inputs, run extractors, or inspect outcomes.
"""

from copy import deepcopy
import numpy as np


FAULT_IDS = (
    "H01_reverse_image_slice_stack",
    "H02_misread_contiguous_order",
    "H03_roi_index_off_by_one",
    "H04_linear_mask_then_integer_cast",
    "H05_transpose_direction_matrix",
    "H06_corner_centre_origin_confusion",
    "H07_intercept_before_slope",
    "H08_premature_integer_buffer",
)


class FaultNotApplicable(ValueError):
    """A frozen activation precondition is absent; retain this in the audit."""


def _payload(frame):
    """Copy the frame without changing the caller's arrays or metadata."""
    if not isinstance(frame, dict):
        raise TypeError("frame must be a dict")
    data = np.asarray(frame["data"], dtype=np.float64)
    mask = np.asarray(frame["mask"])
    affine = np.asarray(frame["affine"], dtype=np.float64)
    if data.ndim != 3 or mask.shape != data.shape:
        raise ValueError("data and mask must be matching XYZ arrays")
    if affine.shape != (4, 4) or not np.all(np.isfinite(affine)):
        raise ValueError("affine must be a finite 4x4 RAS transform")
    if not np.all(np.isfinite(data)):
        raise ValueError("held-out phantom data must be finite")
    label = frame.get("label", 1)
    if label == 0 or not np.any(mask == label):
        raise ValueError("the selected nonzero label must exist")
    result = deepcopy(frame)
    result["data"] = data.copy()
    result["mask"] = mask.copy()
    result["affine"] = affine.copy()
    return result, label


def transform_frame(frame, fault_id):
    """Return a corrupted COPY for one frozen fault identifier.

    There is no implicit identity fallback. Unknown names raise KeyError.
    FaultNotApplicable and downstream errors must be reported, not hidden
    by redrawing a seed, switching a fault, or changing its parameters.
    """
    if fault_id not in FAULT_IDS:
        raise KeyError(f"unknown held-out fault: {fault_id}")
    result, label = _payload(frame)
    data, mask, affine = (result[k] for k in ("data", "mask", "affine"))

    if fault_id == "H01_reverse_image_slice_stack":
        if data.shape[2] < 2:
            raise FaultNotApplicable("requires at least two slices")
        changed = data[:, :, ::-1].copy()
        if np.array_equal(changed, data):
            raise FaultNotApplicable("image is symmetric under slice reversal")
        result["data"] = changed

    elif fault_id == "H02_misread_contiguous_order":
        changed_data = data.ravel(order="C").reshape(data.shape, order="F")
        changed_mask = mask.ravel(order="C").reshape(mask.shape, order="F")
        if np.array_equal(changed_data, data) and np.array_equal(changed_mask, mask):
            raise FaultNotApplicable("C/F reinterpretation leaves this frame unchanged")
        result["data"] = changed_data.copy()
        result["mask"] = changed_mask.copy()

    elif fault_id == "H03_roi_index_off_by_one":
        if mask.shape[0] < 2 or np.any(mask[-1, :, :] != 0):
            raise FaultNotApplicable("requires one empty trailing x plane")
        shifted = np.zeros_like(mask)
        shifted[1:, :, :] = mask[:-1, :, :]
        result["mask"] = shifted

    elif fault_id == "H04_linear_mask_then_integer_cast":
        support = mask == label
        neighbour = np.zeros_like(support)
        neighbour[1:, :, :] = support[:-1, :, :]
        interpolated = (support.astype(float) + neighbour.astype(float)) / 2
        retained = interpolated.astype(np.uint8).astype(bool)
        changed = mask.copy()
        changed[support] = 0
        changed[retained] = label
        result["mask"] = changed

    elif fault_id == "H05_transpose_direction_matrix":
        linear = affine[:3, :3]
        spacing = np.linalg.norm(linear, axis=0)
        if np.any(spacing <= 0):
            raise ValueError("affine has a zero-length voxel axis")
        direction = linear / spacing[np.newaxis, :]
        if not np.allclose(direction.T @ direction, np.eye(3), atol=1e-10, rtol=0):
            raise FaultNotApplicable("direction contract requires an orthogonal basis")
        if np.allclose(direction, direction.T, atol=1e-12, rtol=0):
            raise FaultNotApplicable("direction is unchanged by transposition")
        affine[:3, :3] = direction.T * spacing[np.newaxis, :]

    elif fault_id == "H06_corner_centre_origin_confusion":
        affine[:3, 3] += affine[:3, :3] @ np.full(3, 0.5)

    elif fault_id == "H07_intercept_before_slope":
        slope = float(frame.get("slope", 1.0))
        intercept = float(frame.get("intercept", 0.0))
        if not np.isfinite(slope) or not np.isfinite(intercept) or slope == 0:
            raise ValueError("calibration must be finite with nonzero slope")
        if slope == 1.0 or intercept == 0.0:
            raise FaultNotApplicable("requires slope != 1 and intercept != 0")
        stored = (data - intercept) / slope
        result["data"] = (stored + intercept) * slope

    elif fault_id == "H08_premature_integer_buffer":
        limits = np.iinfo(np.int16)
        if np.min(data) < limits.min or np.max(data) > limits.max:
            raise FaultNotApplicable("int16 range required to isolate truncation from overflow")
        changed = data.astype(np.int16).astype(np.float64)
        if np.array_equal(changed, data):
            raise FaultNotApplicable("all physical intensities are already integral")
        result["data"] = changed

    return result
