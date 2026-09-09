# Native refinement: calibration-informed reevaluation

The immutable `data/RadAccord-native-calibration-1.zip` preserves candidate
1.2.0rc1, its original protocol, 113 recorded attempts, the interrupted run and
all initial summaries. Of 124 planned pairs, 112 completed with exactly unchanged
native outputs. Seven pairs violated the nominal floating-point reference, one
was indeterminate and two CT profiles were unavailable. MIRP had one baseline
exception; the PyRadiomics process stopped after 51 records, leaving one next
slot without a record and ten not reached. The cause of termination is unknown.

## Amendments and justification

Candidate 1.2.0rc2 retains nominal checks and additionally propagates a
source/configuration-derived, conditional numerical envelope before storage
conversion. Compatible alternatives that cannot be resolved within the original
absolute tolerance are indeterminate, even when the nominal candidate agrees.
The tolerance is not enlarged and observed candidate errors do not set bounds.
The envelope has explicit arithmetic assumptions and is not a formal certificate
for an entire backend. Synthetic tests precede this second freeze.

MIRP 2.5.0 is paired with pandas 2.3.3 instead of 3.0.2. A uint8 synthetic
intensity-volume-histogram regression reproduces the former baseline exception
and verifies the compatible dependency profile. Exact identity sampling of
supported integer inputs is declared separately from weighted integer sampling.

PyRadiomics synthetic and MRI workflows use fixed bin count 32 instead of bin
width 25. MRI has no universal physical intensity scale; the initial high-dynamic
inputs imply dense texture matrices exceeding a gigabyte per direction. That
estimate motivates a bounded configuration but does not establish the cause of
the earlier interrupted process. CT retains bin width 25. This is a changed
extraction configuration, not a numerical comparison with initial feature values.

## Retained design and execution

Use exactly the same 22 inputs and 62 ordered pairs per engine as
`native_study_plan.json`. This is post-development reevaluation on reused inputs,
not an independent clinical validation or prospectively unseen test set. All
settings not amended above follow `native_study.md`. Every pair compares a
baseline extraction with its audited extraction under the same rc2 settings.
All native keys/values or complete tables must be exactly preserved; cross-engine
or cross-phase feature equivalence is not an endpoint.

Each pair runs in a new subprocess with a prespecified 300-second timeout.
OpenBLAS, OpenMP and ITK thread counts are set to one within these study processes.
The controller records every planned slot, including exceptions, timeout and
nonzero termination, and continues to the next pair. Public ledgers contain no
raw native warnings, filesystem paths or clinical image arrays. Reports and
source/configuration hashes are retained. Timings remain descriptive and
uncontrolled; process startup is included only in total pair time.

The second internal freeze binds the implementation, tests, protocol, plan,
runner and original archive before execution. It is not public preregistration.
No source changes are allowed during reevaluation. Any subsequent correction
requires another identified version and retention of these results. Summaries
must preserve both calibration and refinement denominators, explicit numerical
abstentions, unsupported profiles, and any unfinished attempts. External-user
evaluation remains prospective.
