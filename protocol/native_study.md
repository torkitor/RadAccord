# Native integration study: execution plan

This protocol concerns development candidate 1.2.0rc1. The preceding sampling
study and its frozen sources remain unchanged. A local, timestamped hash freeze
precedes these native evaluations; this is not public preregistration. The
historical MIRP writing regression is a separate, targeted retrospective
reproduction of a documented defect, not a blinded discovery experiment.

## Question and primary endpoint

Can a separately declared physical operation be checked at native observation
boundaries while returning the exact feature values produced by the original
extractor? Primary endpoints are completion and exact native-value preservation
for every planned pair. Record satisfied, violated, indeterminate and unavailable
relationships without excluding abstentions. Distinguish operator fidelity from
source-centre coverage and from feature or clinical validity.

## Inputs and fixed selection

- Eight previously unused synthetic seeds: 921101–921108, using the retained
  asymmetric phantom generator. The development seed 77881 is excluded.
- Twelve hippocampus MRI volumes and two spleen CT volumes from the existing
  public Medical Segmentation Decathlon downloads. Select the smallest
  SHA-256("RadAccord-native-1|"+filename) values within each dataset after excluding
  the six previously used native subset images (hippocampus 001/003/004,
  spleen 10/12/13). The exact public identifiers and input hashes are in the plan.
- These public images already contributed to the preceding sampling study.
  They are not a new independent clinical cohort. Neither image identifiers nor
  operation counts establish independent patients.
- Select numeric ROI label 1. Input image decoding is performed with SimpleITK;
  The earlier sampling study used the union of positive hippocampus labels;
  these native checks do not reuse that union and must not be described as the
  same selected ROI.
  the MIRP arm receives explicitly converted in-memory native objects. This
  experiment does not validate either file decoder. Native NIfTI API smoke tests
  and the historical writing regression address different boundaries.

## Planned workflows

Each engine executes identity/no resampling, default cubic resampling to 1.3 mm,
and linear resampling to 1.3 mm for the eight synthetic and twelve MRI inputs.
The two CT inputs receive identity only: a bounded applicability control that
also retains MIRP's unavailable CT profile. Total: 62 planned pairs per engine,
124 pairs across engines; a completed pair contains one baseline extraction and
one audited extraction.

PyRadiomics 3.0.1 uses all default original-image feature classes, bin width 25,
and otherwise unchanged native settings. Enabling resampling without overriding
its interpolator selects its default B-spline. MIRP 2.5.0 uses all base feature
families, fixed bin number 32 (valid for unnormalised MRI without a prescribed
lower intensity bound), and its default antialiasing and mask policy. Linear
changes only the requested image spline order. These configurations are not
intended to establish cross-engine numerical feature equivalence.

Compare all PyRadiomics feature keys/values with exact NumPy equality, treating
matching NaN values explicitly; compare complete MIRP DataFrames with exact
pandas equality. Preserve each native output unchanged. Only hashes and derived
evidence are released. MIRP numeric-column counts include numeric metadata and
must not be reported as counts of radiomic features.

## Observation and inference boundaries

PyRadiomics observes loadImage, the shape dispatcher input and original-image
computeFeatures inputs. Its internal shape crop is not observed. MIRP observes
the exported original image and morphology/intensity ROI memberships after
extraction; this is not a direct observation of each feature class's internal
input. Both declarations are made before their native execution and use the
retained source plus resolved processing settings. Distinct source image/mask
grids abstain in these single-grid profiles.

Spatial tolerance is 1e-4 mm; absolute intensity tolerance 1e-4, relative
tolerance zero; index/threshold/cast ambiguity bands are 1e-9 unless a declared
native rounding rule is present. These are engineering bands, not clinically
validated margins or certified floating-point error bounds. Unsupported
normalisation, resegmentation, filters, modalities and versions remain explicit.

## Analysis and reporting

Retain all attempts and exceptions using fixed path-free error codes. Report
counts by engine, source kind, modality and operation. Use the pair as the unit
for preservation/completion, and the observed checkpoint as a separate unit for
relationship outcomes; do not mix denominators. Enumerate the reasons for every
violation, abstention or failure without changing the frozen profile after
looking at its results. Any correction requires an identified amendment and
retention of the first execution.

Timing is descriptive: baseline executes before audited extraction, without
counterbalanced order, warm-up control or isolated hardware load. Report wall
times and their limitations; do not infer a causal runtime multiplier. No
diagnostic accuracy, clinical benefit, user adoption or inter-centre validation
is estimated. The external evaluation protocol remains prospective.
