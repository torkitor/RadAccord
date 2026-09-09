# Evaluation on previously unused clinical volumes

Phase: `prospective-native-validation-1`. Candidate: `1.3.0rc1`.

This is an author-run computational evaluation with prospectively fixed analysis
on previously unused public source volumes. It is not independent-user validation,
a clinical trial, public registry preregistration, or a patient-outcome study.
An immutable public Git tag will bind the code and this protocol before any
RadAccord decision or native extraction is obtained on these collections.
Earlier development and calibration evidence remains unchanged and separately
labelled. Public selection metadata may be inspected for feasibility before the
freeze; native checking outcomes may not.

## Selection and input preparation

Use [the fixed collection and eligibility rules](new_cohort_selection.md): twelve
training image/label pairs each from MSD Task02_Heart and Task06_Lung, ordered by
the prespecified filename SHA-256. All twenty-four selected slots remain in the
intention-to-evaluate denominator. Neither exclusions nor failed workflows are
replaced. Volume identity, rather than inferred unique participant identity, is
the unit of analysis. These collections did not contribute to the previous
Hippocampus/Spleen sampling or native development evaluations.

For each source-eligible pair, retain the bounding box of label 1 with ten
millimetres of context along each voxel axis. Padding in voxels is the ceiling
of 10 divided by that axis's spacing; clip the box to the original field of view.
Apply the identical index crop to image and mask. Preserve decoded values,
decoded dtype and every label-1 voxel; update each affine by multiplying its
source affine by the crop index translation. No interpolation, intensity
normalisation, relabelling or geometric repair is performed. Serialize NIfTI-1
with unit scaling and independently compare reread arrays, selected voxel counts
and world coordinates with the retained source (maximum corner error 0.0001 mm).
Source ineligibility, preparation failure and native failure remain distinct.

This fixed context limits computational cost. It defines the inputs to this
evaluation: the study does not assert that cropped and full-volume native
features are equal or that this context encloses every filter's support. Direct
and observed native arms receive the same cropped source. Crop code and synthetic
verification are frozen before execution; subsequently generated input hashes
are a deterministic realization, bound in a separate operational-plan freeze
before native extraction. Raw files, crops and path-bearing manifests stay private.

## Configurations and two experiments

Use PyRadiomics 3.0.1 with Python 3.10.11, NumPy 1.23.5 and SimpleITK 2.2.1.
Use MIRP 2.5.0 with Python 3.13.5, NumPy 2.2.6, SciPy 1.15.3, pandas 2.3.3,
SimpleITK 2.5.3, ITK 5.4.6 and pydicom 3.0.1. Freeze the complete environment
inventory and exact relevant versions before execution. One native/BLAS thread
is used. The Windows host and observed process memory method are recorded.

Use original-image feature families only, all native default three-dimensional families enabled. Select
numeric label 1. PyRadiomics uses binCount 32 for MRI and binWidth 25 for CT;
MIRP uses fixed_bin_number with 32 bins for both modalities. No cross-engine
feature equality or modality-normalized speed claim is made. Native settings
other than the explicit changes below remain at the pinned version's defaults.
Both MIRP arms request native original-image exports; neither writes images or
feature tables to disk. The report observes the original-image feature dispatcher
and the final original-image export, not internal formula calculations.

| Workflow | PyRadiomics | MIRP |
| --- | --- | --- |
| Identity | No resampledPixelSpacing | No new_spacing |
| Linear 1.5 mm | resampledPixelSpacing [1.5,1.5,1.5], sitkLinear | new_spacing 1.5, spline_order 1 |
| Cubic 2 mm | resampledPixelSpacing [2,2,2], sitkBSpline | new_spacing 2, spline_order 3 |

MIRP antialiasing remains enabled for requested resampling, including its native
mask handling and CT quantization. No tolerance is fitted to these volumes.
Nominal intensity tolerance is 0.0001 decoded units (relative zero); MIRP's
integral CT comparisons and supported exact integer identities use zero intensity
tolerance. Physical tolerance is 0.0001 mm. The frozen source-derived conditional
numerical model propagates the declared storage and quantization operations.
An indeterminate or unavailable obligation never becomes a satisfied obligation.

**Coverage experiment:** one direct-versus-observed pair for each eligible input,
three workflows and two engines, with no warmup. The selected-slot denominator
is 144 pairs before source exclusions. All eligible planned pairs are enumerated
before execution. Execution order is deterministically selected by the harness;
this experiment does not estimate audit overhead. A 300-second timeout applies
to each complete subprocess, including input loading, extraction and checking.

**Timing experiment:** the first four selected ranks in each collection, identity
and cubic 2 mm, both engines, four measured pairs per input/workflow/engine (128
planned measured pairs before source exclusions). No substitute is selected if
a rank is excluded. Every measured pair has its own subprocess and one separate
warmup pair, giving 128 additional warmup pairs. Within each input/workflow/engine,
two measured orders are AB and two BA; the warmup uses the reverse order. Each
subprocess has a 300-second timeout. Run timing workers serially on the host,
without simultaneously running coverage, tests, document rendering or downloads.
Record uncontrolled background-load limitations; do not claim a dedicated host.

Use the [operational harness](operational_benchmark.md). Preserve all attempted,
completed and interrupted slots. Do not automatically retry an unsuccessful
pair. The first execution does not resume: after a controller interruption,
retain its complete planned-slot ledger, attempt-start ledger and available
records. Distinguish an attempted slot without a final record from an unstarted
slot. Any later run requires a separately labelled phase/deviation and cannot
replace the first attempt or silently retry incomplete slots.
Any later development amendment requires a new phase, and cannot
replace this first frozen evaluation.

## Endpoints and analysis

Co-primary computational endpoints are completion of the planned native pairs
and exact native-output preservation among all completed pairs. Compare every
non-diagnostic PyRadiomics key/value and each complete native MIRP DataFrame,
including its metadata columns, within that pair. Nonfinite equality establishes
preservation only. Report affected keys/columns as counts without leaking metadata.

For each collection, engine and workflow, report selected slots, source-eligible
slots, attempted pairs, completed pairs, exact-preservation pairs, pair-level
satisfied/violated/indeterminate/unavailable outcomes and failed/incomplete pairs.
Checkpoint counts and coverage/reuse obligations are separate denominators.
Describe unexpected violations with retained evidence; do not tune them away.

Timing endpoints are matched audited-minus-native seconds and log(audited/native),
with exact-output preservation also checked on warmup and measured pairs. Compute
each input/workflow/engine's median across its four measured repeats, then
summarize those volume-level medians by collection/workflow/engine with median and
range. Provide all raw paired times and first/third quartiles. Do not treat repeats,
checkpoints or features as independent participants. No hypothesis tests or
population-effect confidence intervals are prespecified for this feasibility sample.

The process peak working set covers both arms, warmup and checking and is reported
as a process memory requirement. It cannot estimate incremental audit memory.
External wall-clock timing encloses construction/execution for each arm equally;
source loading and input copying are outside those arm durations. Process startup
and total worker duration are reported separately.

## Constructed error and correction experiment

Once per source and engine in the coverage phase, evaluate a correctly copied
identity control, a shared 7-mm origin shift and a 2-unit decoded intensity offset,
then explicitly restore the retained source. The task uses decoded float64 values
and a label-1 binary mask. Independent task construction defines the expected
error and correction, rather than using RadAccord to assign ground truth.
Paired image-mask geometry, source-aware geometry and the numerical operation
check receive the same retained source and candidates. Record fault activity,
control/fault/correction states and acceptance obligations. If a task cannot be
evaluated, retain it without counting detection. Engine duplicates of a source
are repeated observations, not independent incidents.

These constructed tasks test the computational error-to-correction decision;
they do not measure human diagnosis time, spontaneous defect prevalence or
clinical benefit. The historical MIRP export incident remains a separately
labelled retrospective case, and the external-user protocol remains unexecuted.

## Public evidence and deviations

Retain the public source/code freeze, complete selection ledger, raw-source and
crop hashes, crop-verification receipt, operational plans/freezes, planned slots,
sanitized attempt records and deterministic summaries. Preserve the initial
development results and every amendment as separate artifacts. Keep raw native
logs and private manifests outside the repository. Document every departure from
this protocol with timing relative to outcome inspection and its analytical effect.

## Plan realization and deterministic aggregation

`scripts/build_prospective_plans.py build` verifies the published source/code
freeze and requires that it binds this protocol, the builder, source eligibility
and `protocol/prospective_environments.json`. It compares every public crop
receipt with its selected source and hashes the private crop files without
decoding or evaluating them. Every selected rank remains in the plan's
`selected_inputs` ledger. Only prepared, verified sources enter `inputs` for
native execution. A first-four-rank exclusion never causes rank five to enter
timing. The plans retain intention-to-evaluate denominators 144 and 128, and
report native-planned and not-native-planned pairs separately. Source-excluded
records can retain unavailable hashes when the source could not be read.

The builder writes two operational plans and two new internal freezes. Each
binds the general freeze, source eligibility, crop receipt, environment inventory
and private manifest digest. No private filenames or raw logs are copied into
the public plans. Example commands use the final actual receipt/manifest paths:

```sh
python scripts/build_prospective_plans.py build --crop-receipt protocol/sources/heldout_clinical/crop_receipt.json --private-inputs PRIVATE_CROP_MANIFEST --eligibility protocol/sources/heldout_clinical/selected_source_eligibility.json --general-freeze protocol/prospective_freeze.json --environments protocol/prospective_environments.json --output-dir protocol/prospective_operational
```

For execution, use `protocol/prospective_operational/coverage_plan.json` and
`coverage_freeze.json`, or their `timing` counterparts, with the operational
harness. Each mode/engine has its own new public output and private log directory.
The controller writes its complete planned slots and run metadata before the
first pair, then persists each attempt start before launching its worker.

After retaining all four first-execution directories, summarize without native
extraction or source images:

```sh
python scripts/build_prospective_plans.py summarize --plan protocol/prospective_operational/coverage_plan.json --plan protocol/prospective_operational/timing_plan.json --run results/prospective_coverage/pyradiomics --run results/prospective_coverage/mirp --run results/prospective_timing/pyradiomics --run results/prospective_timing/mirp --output results/prospective_aggregate.json
```

The summary verifies each run's plan/freeze binding, planned-slot and attempt
identities, engine versions and the six checking-source hashes in completed
native reports. It rejects duplicate runs, altered slots and pooled coverage
and timing records. It reports selected, eligible, prepared, attempted,
completed, unchanged, failed, started-without-record and unstarted denominators
by collection/configuration/engine. Pair/checkpoint states, coverage obligations,
reuse obligations and controlled correction tasks remain separate. Timing is
summarized first within volume, then across volume medians with median and range;
all within-volume quartiles and paired raw measurements remain available.
Summary JSON has no generated timestamp and reproduces byte for byte from the
same plans and ledgers. Reproduction uses a new output filename; it does not
overwrite the first summary.
