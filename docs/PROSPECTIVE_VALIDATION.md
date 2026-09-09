# Prospective native validation: results and limits

The 1.3.0rc1 evaluation used 24 previously unused public source volumes: twelve
Medical Segmentation Decathlon Heart MRI and twelve Lung CT image/label pairs.
Selection, the numerical profile, preparation and analysis were frozen before
checking these collections. All selected slots were eligible and prepared, with
no exclusion or replacement. This was an author-run software evaluation using
new inputs; independent-site validation and external-user effectiveness were
not evaluated. Public volume identifiers do not establish independent patients.

Label-1 bounding boxes with outward-rounded 10 mm context defined the evaluated
inputs. Direct and observed calls received the same prepared source. The
[crop receipt](../protocol/sources/heldout_clinical/crop_receipt.json) retains
decoded-array and dtype equality, selected-voxel support and world-coordinate
checks within the declared 0.0001 mm tolerance. These checks do not establish
full-volume/cropped feature equivalence or complete support for every native filter.

## Native coverage

All **144/144** planned native pairs completed and preserved their native outputs
exactly: 24 sources × three workflows × two engines. PyRadiomics completed 72/72
with 39 satisfied and 33 unavailable sampling-relationship pairs; MIRP completed
72/72 with 49 satisfied and 23 indeterminate sampling-relationship pairs. There
were no violated sampling-relationship pairs. These states do not combine the
separate source-coverage and feature-reuse obligations into an overall acceptance.
Completion and exact preservation also have different meanings from these checks.

Each table row has 12 completed, exactly preserved pairs; its states describe
the sampling relationship. Workflow names identify
the declared image sampling; full engine-specific settings, including mask and
anti-aliasing operations, remain in the frozen plans.

| Collection | Engine | Workflow | Satisfied | Violated | Indeterminate | Unavailable |
|---|---|---|---:|---:|---:|---:|
| Heart MRI | PyRadiomics | Identity | 12 | 0 | 0 | 0 |
| Heart MRI | PyRadiomics | Linear 1.5 mm | 0 | 0 | 0 | 12 |
| Heart MRI | PyRadiomics | Cubic 2 mm | 0 | 0 | 0 | 12 |
| Lung CT | PyRadiomics | Identity | 12 | 0 | 0 | 0 |
| Lung CT | PyRadiomics | Linear 1.5 mm | 8 | 0 | 0 | 4 |
| Lung CT | PyRadiomics | Cubic 2 mm | 7 | 0 | 0 | 5 |
| Heart MRI | MIRP | Identity | 12 | 0 | 0 | 0 |
| Heart MRI | MIRP | Linear 1.5 mm | 1 | 0 | 11 | 0 |
| Heart MRI | MIRP | Cubic 2 mm | 0 | 0 | 12 | 0 |
| Lung CT | MIRP | Identity | 12 | 0 | 0 | 0 |
| Lung CT | MIRP | Linear 1.5 mm | 12 | 0 | 0 | 0 |
| Lung CT | MIRP | Cubic 2 mm | 12 | 0 | 0 | 0 |

The sampling-relationship pair status prioritises a demonstrated violation, then
unavailable evidence, then indeterminate evidence; satisfaction requires every
observed sampling checkpoint to satisfy its obligation. Checkpoint counts have
separate denominators. The 33
PyRadiomics unavailable pairs have the final `feature_input:original` reason
`roi_crop_depends_on_ambiguous_membership`: an unresolved membership decision
prevents a definite downstream crop declaration. This includes all 24 resampled
Heart MRI pairs and nine resampled Lung CT pairs. Earlier loaded/shape checks
can be indeterminate while the overall pair is unavailable. The 23 MIRP
indeterminate pairs were resampled Heart MRI inputs. None of these outcomes is
counted as a demonstrated producer defect or converted to a satisfied result.

Exact preservation concerns the native values returned within a pair. It does
not establish finiteness, feature correctness, cross-engine agreement or clinical
validity. An input relationship satisfying its contract also does not establish
feature invariance: the reported feature-reuse obligation remains separate.

**Source coverage is a separate endpoint.** Across the 360 checkpoints in the
144 coverage pairs, 327 emitted a source-coverage field: 315 satisfied and 12
violated. The remaining 33 checkpoints emitted no coverage field; absence is
not satisfaction. Six violated fields occurred in Lung CT PyRadiomics linear
1.5 mm workflows and six in cubic 2 mm workflows. These count source-coverage
fields, not 12 independent volumes or 12 violated sampling pairs. The 327 emitted
feature-reuse decisions were 203 `requires_reextraction` and 124 `blocked`, with
33 absent fields. A correct declared sampling operation can still lose source
ROI support. Neither the 88 satisfied sampling pairs nor a `requires_reextraction`
decision authorizes reuse of existing measurements.

## Paired execution cost

Timing used the first four selected ranks in each collection, identity and cubic
2 mm workflows, both engines and four repeats. All **128/128 measured pairs** and
**128/128 additional warmup pairs** completed with exact native-output preservation.
No ranks were excluded or replaced. These repeat observations do not add new
independent source volumes to the coverage experiment. AB/BA order was balanced
within each source/workflow/engine, with reverse-order warmup in each fresh process.

Each row below summarizes four source volumes, each with four measured repeats.
Time columns are medians of source-level medians in seconds. Added time is the
paired difference, with the minimum–maximum of the four source-level medians;
it is not calculated by subtracting the two displayed aggregate medians.
Log ratio is the median of source-level median `log(audited/native)` values.
S/V/I/U counts concern the 16 measured sampling-relationship pair outcomes in
each row.

| Collection | Engine | Workflow | Native, s | Audited, s | Added, s (range) | Log ratio | S/V/I/U |
|---|---|---|---:|---:|---:|---:|---:|
| Heart MRI | PyRadiomics | Identity | 0.255 | 0.652 | 0.390 (0.226–0.453) | 0.920 | 16/0/0/0 |
| Heart MRI | PyRadiomics | Cubic 2 mm | 0.144 | 13.965 | 13.821 (7.926–19.316) | 4.576 | 0/0/0/16 |
| Lung CT | PyRadiomics | Identity | 0.065 | 0.175 | 0.109 (0.026–1.933) | 0.965 | 16/0/0/0 |
| Lung CT | PyRadiomics | Cubic 2 mm | 0.053 | 0.703 | 0.658 (0.473–30.446) | 2.791 | 8/0/0/8 |
| Heart MRI | MIRP | Identity | 6.371 | 6.658 | 0.366 (0.214–0.838) | 0.064 | 16/0/0/0 |
| Heart MRI | MIRP | Cubic 2 mm | 4.230 | 14.785 | 10.606 (5.578–11.723) | 1.114 | 0/0/16/0 |
| Lung CT | MIRP | Identity | 3.542 | 3.631 | 0.087 (0.037–1.307) | 0.036 | 16/0/0/0 |
| Lung CT | MIRP | Cubic 2 mm | 0.639 | 1.803 | 1.158 (0.329–18.260) | 1.021 | 16/0/0/0 |

The timing experiment separately emitted 296 source-coverage fields across 320
checkpoints: 288 satisfied and eight violated, with 24 absent. The eight violated
fields occurred in Lung CT PyRadiomics cubic workflows. Its 296 emitted
feature-reuse decisions were 208 `requires_reextraction` and 88 `blocked`, with
24 absent. These fields include repeated observations of the timing sources;
they are not independent volumes and do not replace the sampling-pair states.

Cost depends strongly on the source and workflow. Heart MRI cubic PyRadiomics
had a median additional 13.821 seconds while all 16 measured outcomes were
unavailable. The largest source-level median addition in Lung CT cubic
PyRadiomics was 30.446 seconds. A resolved or unresolved check can therefore
carry substantial cost; these results do not support a general claim of
negligible overhead.

Measured calls include native construction/execution and, in the observed arm,
checking and report construction. Both MIRP arms request the same native image
export. Source loading, input copies, output serialization and HTML rendering
are outside arm durations. Process peak memory, retained in the aggregate,
includes both arms and warmup and cannot estimate incremental checking memory.
These are descriptive costs on the recorded host, not a population-effect
estimate or an uncontrolled speed ranking between engines. No patient-level
inference or confidence interval treats timing repeats as independent samples.

## Constructed restoration

The harness separately applied a shared 7 mm origin shift and a 2-unit decoded
intensity offset to every prepared source. All 48 source/fault configurations
were active. They were observed once per engine, yielding 96 task records; the
two-engine observations are not independent incidents. Per engine, RadAccord
flagged **48/48** active tasks, source-aware geometry flagged **24/48**, and paired
image–mask geometry flagged **0/48**. All recorded correct controls and restored
states were satisfied, with no task error or unavailable task. The same correct
control is recorded for each fault and must not be counted as a new independent
control image.

Correction restores the retained source. This tests a computational transition
under a known declaration; it does not measure spontaneous defect prevalence,
human diagnosis or repair time, or benefit to patients. The documented MIRP
2.4.1/2.4.2 NIfTI writer reproduction remains a separate historical experiment
in [INCIDENTS.md](INCIDENTS.md).

## Observation boundaries and reproducibility

MIRP's current profile observes original-feature dispatch arguments and a later
native image/ROI export. PyRadiomics observes loaded, shape-dispatch and original
feature inputs. Initial decoding/modality promotion, unobserved feature-class
internals and feature formulae remain outside these checks. Reports provide
bounded evidence for reviewing an execution; unresolved obligations require
investigation under an appropriate profile rather than conversion to a pass.

From the repository root, this replays retained plans and ledgers without clinical
images or native extraction. Use a new output filename:

```sh
python -B scripts/verify_prospective_freeze.py
python -B scripts/build_prospective_plans.py summarize --plan protocol/prospective_operational/coverage_plan.json --plan protocol/prospective_operational/timing_plan.json --run results/prospective_coverage/pyradiomics --run results/prospective_coverage/mirp --run results/prospective_timing/pyradiomics --run results/prospective_timing/mirp --output outputs/prospective_aggregate_reproduced.json
```

The generated JSON must match the retained
[aggregate](../results/prospective_aggregate.json) byte for byte. See the frozen
[evaluation protocol](../protocol/prospective_native_validation.md),
[operational protocol](../protocol/operational_benchmark.md),
[source provenance](../protocol/sources/heldout_clinical/SOURCE.md), and
[MIRP profile](MIRP_PROFILE.md). Earlier calibration/refinement records retain
their own archives and [reproduction instructions](NATIVE_EVIDENCE.md).
Raw clinical files, crops, path-bearing manifests and logs remain outside the
public repository. Dataset CC-BY-SA 4.0 terms are separate from the software's
Apache-2.0 licence.
