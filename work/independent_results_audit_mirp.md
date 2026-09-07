# Independent held-out results audit: mirp

All case IDs, jobs and completed outputs were retained: 4096 cases and 4608 extraction jobs. There were no duplicate/missing IDs, no inactive fault cases and no boundary failures. The frozen software hashes and case-manifest hash match. All 8192 input files were decoded for the input audit; the observed digests and raw geometry match the case log. This run reused that verified input audit against unchanged case/job manifest hashes.

The four independently recomputed source anchor sets use `math.fsum` for mean, energy and population variance, plus physical voxel volume from the decoded affine. All 24 comparisons to the sampled native outputs satisfy the frozen tolerances.

## Injected faults

Counts below are detections among 64 cases per mechanism. Repetition compares the same corrupted input with itself.

| Mechanism | Native/schema | Pair geometry | Repeat | Feature relation | Anchors | Witness | Combined |
|---|---:|---:|---:|---:|---:|---:|---:|
| H01_reverse_image_slice_stack | 0/0 | 0 | 0 | 64 | 64 | 64 | 64 |
| H02_misread_contiguous_order | 0/0 | 0 | 0 | 64 | 0 | 64 | 64 |
| H03_roi_index_off_by_one | 0/0 | 0 | 0 | 64 | 64 | 64 | 64 |
| H04_linear_mask_then_integer_cast | 0/0 | 0 | 0 | 64 | 64 | 64 | 64 |
| H05_transpose_direction_matrix | 0/0 | 0 | 0 | 0 | 0 | 64 | 64 |
| H06_corner_centre_origin_confusion | 0/0 | 0 | 0 | 0 | 0 | 64 | 64 |
| H07_intercept_before_slope | 0/0 | 0 | 0 | 64 | 64 | 64 | 64 |
| H08_premature_integer_buffer | 0/0 | 0 | 0 | 64 | 64 | 64 | 64 |

## Correctly transported and context controls

| Group | Cases | Witness alerts | Conditional feature alerts | Anchor alerts | Combined alerts | Unconditional invariance alerts |
|---|---:|---:|---:|---:|---:|---:|
| reference | 64 | 0 | 0 | 0 | 0 | 0 |
| equivalent | 3200 | 0 | 0 | 0 | 0 | 0 |
| covariant | 256 | 0 | 0 | 0 | 0 | 256 |
| not_applicable | 64 | 0 | 0 | 0 | 0 | 64 |

Correctly transported cases with combined alerts: **0**. These are preserved as observed output-level alerts; they must not be relabelled as injected input corruption. No tolerance, feature inclusion or case selection was changed after observing these outcomes.

Alert counts by phantom: {}.

Alert counts by feature: {}.

Detailed per-case decisions, worst numerical discrepancies and raw-output hashes are retained in the companion JSON/JSONL audit files.

These are synthetic software cases nested within 64 phantoms and eight mechanisms. They are not clinical sensitivity, fault prevalence, or thousands of independent patient observations. The source-aware witness's counts are derived from the frozen case log; this audit additionally rechecks all decoded-input digests/geometry and independently computes scalar decisions.
