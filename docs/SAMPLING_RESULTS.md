# Sampling evidence and exact summary replay

This page concerns the local **1.1.0rc1** declared-sampling extension. Its updated
GitHub workflow is prepared but has not run remotely. The source and declaration
are trusted; the study does not establish clinical utility or independent-patient
performance. [The sampling guide](SAMPLING.md) explains the API and decisions.

## Included records

`results/sampling_reserved/` and `results/sampling_clinical/` contain byte-identical
copies of the retained first evaluations. Each directory has:

- `cases.jsonl`: each executed case, declaration, comparison result, mutation
  activity, direct ROI statistics, timings and file-roundtrip status.
- `volumes.jsonl`: every attempted volume and its fourteen-case execution ledger.
- `checkpoint_demo.jsonl`: the deliberately constructed checkpoint demonstrations.
- `run_summary.json`: prespecified IDs, denominators, software/source hashes and
  recorded run metadata.
- `summary/summary.json` and eleven CSV tables: case counts, comparator strata,
  support/reuse, roundtrip agreement, operation/volume runtime, direct drift,
  case/volume/checkpoint rows and the complete execution ledger.
- `independent_audit.json` and `.md`: retained checks of hashes, record accounting,
  decision logic and numerical arithmetic.

Audit narratives retain original relative preparation-layout labels such as
`work/sampling_clinical_v1`. Their public counterparts are the result directories
above. The original freeze also retains its original relative paths; the pinned
`protocol/sampling_freeze_locations.json` maps every frozen payload to its public
location without changing those payload bytes. Raw clinical images, personal
paths and native process logs are not part of these records.

## Fixed results and limits

| Outcome | Reserved synthetic | Public clinical images |
|---|---:|---:|
| Volumes | 32 | 301 (260 MRI, 41 CT) |
| Planned/retained cases | 448/448 | 4,214/4,214 |
| Valid controls satisfied | 224 | 2,096 |
| Valid controls indeterminate | 0 | 11 |
| Active faults violated | 190/190 | 1,605/1,605 |
| Inactive faults retained | 2 | 201 |
| Correct sampling with deliberately lost ROI support | 32 | 301 |
| Comparable NIfTI roundtrips | 448 | 84 |
| Disagreements between memory and NIfTI assessed statuses | 0 | 0 |

The eleven clinical abstentions occur in five CT volumes and agree with nominal
sampling. Distinct NN membership alternatives within the fixed boundary band
leave them indeterminate and blocked. They are not observed SimpleITK defects.
They are outside the prespecified three-volume CT file subset, so the 84/84
agreement result does not assess serialization stability of those abstentions.
The other 4,130 clinical case records explicitly say `not_selected` for roundtrip.

On the 1,605 active clinical wrapper perturbations, paired QA detects none,
source-aware geometry violates 401, and the new sampling witness violates all
1,605. The original full-grid witness violates 301 and is inapplicable to 1,304;
inapplicability is not detection. The 201 inactive MRI stale-origin cases produce
no exact change and remain in the planned denominator.

Within valid clinical controls, 1,204 integral operations preserve selected
inputs, 892 resampling operations require reextraction and 11 remain blocked.
Every deliberate truncation satisfies its sampling operation but loses source
ROI centre coverage and blocks reuse. Neither input preservation nor an absence
of numerical drift establishes universal feature equality.

`results/native_feature_subset/` retains the fixed 30 extractions and 24 contrasts:
2,160 finite values, 1,728 comparable feature pairs and 1,418 pairs beyond the
fixed numerical tolerance. The correct resampling reference is the working crop;
the wrong-kernel reference is the correct 0.8-mm output. These differences are
neither clinical thresholds nor independent sample sizes. The original masks
were combined into the positive-label union; class-wise anatomy was not tested.

## Verify and regenerate the descriptive tables

From this repository, with the core dependencies installed:

```text
python -B scripts/verify_sampling_freeze.py
python -B scripts/summarize_sampling_study.py --input results/sampling_reserved --output reproduced/sampling_reserved
python -B scripts/summarize_sampling_study.py --input results/sampling_clinical --output reproduced/sampling_clinical
```

The output directories must not exist. The first command validates the pinned
freeze, location mapping, all sixteen frozen files and unchanged historical ZIP.
The summarizer refuses duplicate/unplanned IDs, incomplete ledgers, inconsistent
counts and altered direct-statistic arithmetic. It retains missing/nonexecuted
cases and records its own source hash. Its post-freeze implementation generates
descriptive summaries; it does not modify the frozen scientific decision rules.

Compare all twelve files in each generated directory with the corresponding
`results/sampling_*/summary/` directory. The included CI workflow requires literal
byte equality for every CSV and JSON. This checks replay of recorded arithmetic,
not new execution of interpolation, image loading or native feature extraction.
No images or extractor are needed for this replay. The separate historical
`restore_records.py` step is not needed for these sampling records.

To rerun the synthetic producer in a new directory, install SimpleITK 2.5.3 and
use the documented `run_sampling_study.py --synthetic` command. Clinical input
reruns require separately obtained source data and the frozen protocol; do not
replace failed inputs or change the preserved first evaluation.

## Numerical and reporting scope

Counts are descriptive, with operations nested within released volumes. Public
IDs do not establish independent participants. No patient-level confidence
interval, diagnostic sensitivity or clinical-risk estimate is produced.
Numerical tolerances are not clinical equivalence margins. The index boundary
band is a fixed engineering convention, not a certified floating-point bound.

Direct drift concerns selected voxel count, occupied volume, intensity mean and
population variance. Source and correct-operation references are separate;
controls compare with their own observed correct-operation output, so zero in
that particular comparison is by construction. Runtime distributions include
recorded input/operation costs and subset-specific I/O, not native extraction,
and do not guarantee performance on other data or hardware.
