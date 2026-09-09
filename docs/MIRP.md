# Native MIRP integration

`radaccord.mirp.audit_mirp(image, mask, *, config=None, label=1)` executes MIRP
once and returns `{"features": native_table, "report": evidence}`. The feature
DataFrame is returned unchanged, including native metadata columns. The separate
report contains hashes and numerical geometry, without filenames, sample names,
ROI names or native exception messages. Native MIRP logging and feature tables
can contain identifying metadata; only the report is designed for sharing.

Pass file-backed inputs as string filenames, for example `str(image_path)` and
`str(mask_path)`. MIRP 2.5.0 does not accept `pathlib.Path` through this import
interface. The rc3 CLI normalizes filenames before dispatch; native `GenericImage`
and `BaseMask` objects remain supported through the unchanged Python API.

```python
from radaccord.mirp import audit_mirp

result = audit_mirp(
    "image.nii.gz", "segmentation.nii.gz", label=1,
    config={"image_modality": "mr", "new_spacing": 1.3,
            "base_feature_families": ["statistical"]},
)
features = result["features"]
relationship_accepted = result["report"]["relationship_acceptance"]
```

The configuration contains ordinary MIRP keyword arguments. The adapter requests
in-memory native image/mask and feature exports, without writing files. It maps
`label` to MIRP's numeric `roi_name` selector. A supplied native `BaseMask` is
already selected and uses binary label 1. Multiple native workflows retain their
tables as a list, with unavailable evidence for this single-workflow profile.
XML/SettingsClass configuration files and output-writing options are not part of
this interface. `extract_with_evidence` is an alias of `audit_mirp`.

## What is checked

The `mirp-native-original-2` profile is version-scoped to MIRP **2.5.0**. It snapshots the decoded source
image/ROI and resolves settings before extraction. The expected target size,
centre alignment, physical coordinates, interpolation and ROI policy follow
from that retained source and configuration. They are never reconstructed from
the observed output. A separate NumPy operator checks the actual native export
after extraction. This is **post-extraction evidence**: it identifies violated,
ambiguous or unsupported observed relationships after features have been computed.
It does not interrupt MIRP before feature computation or make a global decision
about feature reuse.
The relationship flag requires satisfied operator checks, source-centre coverage
and a nonempty candidate ROI; it does not certify numerical feature validity.

The supported profile is an original three-dimensional MR or generic image on
orthogonal axes in millimetres, one selected ROI and one target grid. Float32 and
float64 source storage are supported. Integer `uint8`, `uint16`, `int16` and
`int32` storage is admitted only for an exact identity grid with image
interpolation disabled, no active anti-aliasing and skipped ROI registration.
This integer identity check uses zero intensity tolerance; the declared physical
coordinate tolerance is retained. Integer resampling, including anti-aliasing
that would convert it to float32, and other integer storage types remain outside
the profile. The adapter keeps the native source dtype and requested features.
Source image and ROI must have exactly the same
geometry; merely close source grids abstain because the single-affine profile
does not model their distinct registrations. Export comparison retains its
declared physical tolerance. It retains MIRP's default cubic spline image
interpolation, Gaussian anti-aliasing, linear ROI interpolation and rounding to
six decimals before the 0.5 membership threshold. Image edges extend the nearest
sample; ROI interpolation uses constant zero outside the domain of voxel centres.
ROI anti-aliasing extends nearest samples and thresholds before interpolation.
When native registration is skipped on an identical grid, the ROI stays unchanged.
Linear and nearest image interpolation and nearest ROI interpolation are also
covered. Ambiguous numerical boundaries prevent acceptance rather than counting
an alternative label as a satisfied check.

The second native profile retains the nominal NumPy reference and its original
decision, then assesses a source-derived conditional numerical envelope.
Rounding ambiguity remains indeterminate even if the candidate matches that
nominal reference. The model does not estimate its budget from the observed
candidate or certify the whole backend; the numerical assumptions and reused-input
reevaluation are documented in the [refinement protocol](../protocol/native_refinement.md).

The grid size is `ceil(source_size * source_spacing / target_spacing)` and its
source-index origin is `(source_size-1)/2 - (target_size-1)*ratio/2`, where
`ratio = target_spacing/source_spacing`. Native spacing values are retained to
avoid changing a ceiling through reconstruction of floating metadata. Gaussian
sigma is `sqrt(-8 * ratio**2 * log(smoothing_beta))`, with float32 intermediate
storage and MIRP's native ZYX axis order. Anti-aliasing is retained for upsampling
when the resolved native settings request it. The two exported feature ROIs
(intensity and morphology) must agree with the checked original ROI.

CT's intermediate integer rounding, PET conversion, filtered images, intensity
normalization/scaling, resegmentation, perturbations, ROI adaptation and two-
dimensional processing are outside this profile. Native execution still runs and
returns its requested features; evidence is `unavailable`. The adapter never
changes a modality or disables an operation to obtain acceptance. Unknown engine
versions also abstain. No native feature formula is independently certified.

## Compatibility and candidate status

The `1.2.0rc2` and `1.2.0rc3` MIRP extras pin pandas **2.3.3**. The preceding `1.2.0rc1`
environment combined MIRP 2.5.0 with pandas 3.0.2 and raised a `TypeError` for a
small synthetic uint8 MR intensity-volume-histogram (IVH) extraction. This is
an extraction/dependency incompatibility, not evidence of a spatial discrepancy.
The original calibration sources and outcomes remain in the
[native calibration archive](../data/RadAccord-native-calibration-1.zip).

The same synthetic IVH extraction completed with pandas 2.3.3 in a newly created
environment. That version can still emit a warning about assignment to an
incompatible dataframe dtype; the pin is a tested compatibility choice, not an
upstream code correction or a claim about future pandas releases. The rc2 source
tests compare the entire native feature table exactly for supported integer
identities and retain the limits on feature formulae and unobserved states.
They also require integer resampling and uncovered integer types to abstain
without changing the requested native features. The rc2 native reevaluation is
retained separately from the rc3 filename-dispatch fix. Source and installed-wheel
checks are distinguished in [the artifact verification record](WHEEL_VERIFICATION.md);
neither substitutes for independent validation.

## Boundaries and reproducibility

Input decoding is trusted and observed after MIRP's native reader; DICOM/NIfTI
decoding, unit interpretation and source identification are not independently
certified. File-backed sources are read for the snapshot and again by the native
workflow; keep them immutable for the duration of the call. Exported original
images and intensity/morphology ROIs are observed, while hidden feature-class
buffers and earlier internal states are not. Source and table digests bind this
evidence to its inputs and native outputs without reproducing private metadata.

Run `python examples/native_mirp.py` after installing RadAccord and its MIRP
optional dependencies. Run `python -m unittest discover -s tests -p test_mirp.py` for
small native tests of grid declaration, unchanged DataFrames, integer identity
and IVH compatibility, unsupported processing, and a deliberately altered paired
output origin. All examples are
synthetic; they do not measure clinical performance.

Sources: [MIRP public extraction API](https://oncoray.github.io/mirp/quantitative_image_analysis.html),
[configuration reference](https://oncoray.github.io/mirp/configuration.html), and
[MIRP 2.5.0 release](https://pypi.org/project/mirp/2.5.0/).
Implementation equations and threshold order are scoped to the installed 2.5.0
source, rather than assuming that the online documentation's latest version is
identical.
