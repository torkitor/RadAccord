# Native integration evaluation

Calibration-informed reevaluation on reused inputs; not independent clinical validation.

Every planned slot is accounted for by an original record or an explicit interruption ledger; all frozen files and archived record hashes were verified.

| Engine | Planned pairs | Recorded attempts | Candidate attempts including interrupted slot | Completed | Exact native values preserved | Satisfied | Violated | Indeterminate | Unavailable | Recorded failure | Interrupted without record | Not reached |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mirp | 62 | 62 | 62 | 62 | 62 | 47 | 0 | 11 | 4 | 0 | 0 | 0 |
| pyradiomics | 62 | 62 | 62 | 62 | 62 | 52 | 0 | 8 | 2 | 0 | 0 | 0 |

These are pair outcomes. The separate checkpoint table counts each recorded observation boundary.

| Engine | Checkpoint | Observed | Satisfied | Violated | Indeterminate | Unavailable |
|---|---|---:|---:|---:|---:|---:|
| mirp | original_image_export_after_extraction | 62 | 47 | 0 | 11 | 4 |
| pyradiomics | feature_input:original | 62 | 57 | 0 | 3 | 2 |
| pyradiomics | loaded_input | 62 | 52 | 0 | 8 | 2 |
| pyradiomics | shape_dispatch | 62 | 52 | 0 | 8 | 2 |

## Timing and interpretation

Times are reported as observed seconds in timings.csv (median, quartiles, minimum, maximum and mean). Baseline extraction always preceded audited extraction; timing differences are not a causal estimate of overhead.

Exact native-value preservation means the observer returned the producer values unchanged. It does not establish feature correctness, finiteness, clinical validity or cross-engine equality. MIRP numeric-column counts include metadata.

All non-satisfied checkpoints and their row identifiers remain in summary.json and checkpoints.csv. Coverage and feature-reuse decisions use recorded-checkpoint denominators, separately from pair completion.

An interrupted unrecorded slot is not a completed extraction or a measured result. Its start and completion are not established by an archived case record. Later not-reached slots contain no fabricated feature, timing or checkpoint observations. The interruption cause is undetermined.

The sampled public clinical images appeared in the preceding study. They do not form a new independent clinical cohort.

Freeze SHA-256: `8a99094b119db04275251de57f1e2915720b5bad649736e5212fcecadf6a3b4e`.
Plan SHA-256: `b9128084776ef95aca598c420ed36fd41d90c09cd9b29054c891aa486e8124d2`.
