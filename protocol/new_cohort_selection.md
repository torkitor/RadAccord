# Selection of previously unused clinical volumes

## Prospective input selection

This protocol is specified before running RadAccord on either collection. The
new collections are Medical Segmentation Decathlon Task02_Heart (MRI) and
Task06_Lung (CT). They contribute different released anatomical volumes from
the earlier Hippocampus and Spleen evaluations. This is an independently selected
input set, not an externally conducted study or independent operator evaluation.

Use the official AWS MSD mirror, verify its complete archive against the MD5
published in MONAI commit `20df60253d364be69601114adae3bd609e0cb6f6`, and retain a
locally calculated SHA-256. Enumerate only the released `training` image/label
pairs in each original `dataset.json`; the unlabelled test partition is unused.
No annotation or demographic variable affects selection.

For every released training image, compute the lower-case hexadecimal SHA-256
of the UTF-8 string `RadAccord-new-cohort-v1|TASK|BASENAME`, substituting the exact
task directory name and image basename, including `.nii.gz`. Sort ascending by
that hash, breaking any tie by basename. Fix the first **12** volumes from each
collection before examining content eligibility. If fewer than 12 training
pairs exist, use all and retain the shortfall. This is a prespecified feasibility
sample, with no statistical power or prevalence claim. Image and label file
SHA-256 values then bind the selected inputs to their released bytes.

The 24 selected slots form the intention-to-evaluate denominator. Eligibility
exclusions, unreadable inputs, unavailable operations, failed extraction,
timeouts and interrupted runs remain recorded against their original slots.
Do not replace any selected volume, retune a threshold or select an alternative
configuration in response to its RadAccord output. Any prespecified technical
retry uses identical inputs, configuration and code; retain the first attempt
and label the retry separately. The root study protocol determines whether
retries are permitted and which attempt is used for each summary.

## Source-domain eligibility, assessed without RadAccord

Inspect only the released metadata and selected source images/masks. Require:

- A readable, scalar, real numeric three-dimensional image and label mask,
  each dimension at least two; matching array shapes; explicit millimetre units.
- Finite, invertible affine matrices; strictly positive finite voxel spacings;
  orthogonal voxel axes, with maximum absolute deviation of the normalized
  affine-column Gram matrix from identity at most `1e-5`.
- At least one active qform or sform per file. If both are active, their maximum
  voxel-centre corner separation must be at most `1e-4` mm. The image/mask affine
  corner separation must also be at most `1e-4` mm. No metadata repair is made.
- Finite decoded image and mask values; integral mask labels. The declared
  foreground is label `1`, as documented by each release, with at least eight
  voxels and a bounding-box extent of at least two voxels along every axis.

Classify exclusions using fixed reason codes, recording every applicable reason
where inspection can complete. No intensity normalization, resampling, orientation
change or feature extraction is allowed during selection. Decoded source dtype
and foreground voxel count may be retained for eligibility and planning, but no
RadAccord decisions or feature comparisons are inspected before the study freeze.
Eligibility is not a guarantee that every native configuration is supported;
operation-level abstentions remain study outcomes.

## Units of analysis and reporting

Each released image/label pair is one source-volume unit. Repeated operations,
engines, feature families and checkpoints are paired repeated measurements of
that unit, not independent subjects. Report denominators by collection and
operation, together with all selected, source-eligible, attempted, completed and
unavailable counts. Do not infer unique participant identities from filenames
or combine the two collections into a clinical prevalence estimate.

The frozen challenge protocol must specify configurations, primary endpoints,
numeric tolerances, failures and statistical comparisons before evaluation.
The acquisition/selection procedure does not select the challenge according to
observed outcomes. No clinical prediction model or patient outcome is evaluated.

## Provenance and sharing

The official [AWS MSD registry](https://registry.opendata.aws/msd/) states
CC-BY-SA 4.0. Dataset attribution and any applicable share-alike obligations
remain separate from the software's Apache-2.0 licence. Raw volumes, private
input manifests and execution logs remain outside the software repository.
Only provenance, code, selection identifiers/hashes and appropriate derived
summaries may be included publicly. No personal filesystem paths are exported.

References: [MONAI pinned download and hash definitions](https://github.com/Project-MONAI/MONAI/blob/20df60253d364be69601114adae3bd609e0cb6f6/monai/apps/datasets.py);
[Medical Segmentation Decathlon publication](https://doi.org/10.1038/s41467-022-30695-9).
