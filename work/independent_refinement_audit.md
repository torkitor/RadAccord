# Independent targeted refinement audit

The initial and follow-up frozen hashes are unchanged. All 2048 planned cases are retained. Two equivalent cases were rejected at the format boundary and were not approved or scheduled for native extraction. All 2302 scheduled jobs have one complete, finite 72-feature PyRadiomics output, including all 256 repeated corrupted inputs. No fault mechanism was reclassified as inactive or not applicable.

All 4092 analysable input files were decoded and their logged digests and image–mask geometry were checked. The 32 source digests are unique and consistent across their cases. Six anchors on each source were independently recomputed with scalar sums and the decoded affine: all 192 native-and-logged comparisons satisfy the frozen tolerances.

| Group | Attempted | Analysable | Outside domain | Initial feature alerts | Revised feature alerts | Witness alerts | Anchor alerts | Combined alerts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| reference | 32 | 32 | 0 | 0 | 0 | 0 | 0 | 0 |
| equivalent | 1600 | 1598 | 2 | 384 | 0 | 0 | 0 | 0 |
| covariant | 128 | 128 | 0 | 0 | 0 | 0 | 0 | 0 |
| not_applicable | 32 | 32 | 0 | 0 | 0 | 0 | 0 | 0 |
| fault | 256 | 256 | 0 | 192 | 192 | 256 | 160 | 256 |

| Known mechanism | Cases | Repeated identical | Repeat alerts | Feature alerts | Anchors | Witness | Combined |
|---|---:|---:|---:|---:|---:|---:|---:|
| H01_reverse_image_slice_stack | 32 | 32 | 0 | 32 | 32 | 32 | 32 |
| H02_misread_contiguous_order | 32 | 32 | 0 | 32 | 0 | 32 | 32 |
| H03_roi_index_off_by_one | 32 | 32 | 0 | 32 | 32 | 32 | 32 |
| H04_linear_mask_then_integer_cast | 32 | 32 | 0 | 32 | 32 | 32 | 32 |
| H05_transpose_direction_matrix | 32 | 32 | 0 | 0 | 0 | 32 | 32 |
| H06_corner_centre_origin_confusion | 32 | 32 | 0 | 0 | 0 | 32 | 32 |
| H07_intercept_before_slope | 32 | 32 | 0 | 32 | 32 | 32 | 32 |
| H08_premature_integer_buffer | 32 | 32 | 0 | 32 | 32 | 32 | 32 |

The 1600 equivalent attempts comprise 800 natural-fixture cases and 800 enriched-fixture cases. The enriched denominator contains the two retained boundary rejections. All 384 initial feature alerts occur in the enriched fixtures; the refined reindexing profile has no feature alert among 1598 analysable equivalent cases. This does not validate the four withheld mesh features. The 32 changed-bin-width controls abstain from the feature relation and are not counted as approved feature equivalence.

The audit explicitly verifies and archives all 6136 `initial_obligation` records for the four withheld mesh features in the 1534 analysable reindexing cases. Other feature decisions, non-reindexing relations, numerical tolerances, anchors and witness values are unchanged. The compact published decision log retains the initial aggregate status; the companion independent JSONL additionally retains each original actual/expected value, error and status under the revised not-applicable record. The original 64-phantom native-output SHA-256 still matches the original audit, where all 36 alerts remain recorded.

These are targeted follow-up inputs after a profile restriction informed by the initial challenge. Sixteen phantoms are natural and sixteen contain a prospectively specified checkerboard enrichment. The eight fault mechanisms are known; this is neither an unseen-mechanism benchmark nor clinical sensitivity.
