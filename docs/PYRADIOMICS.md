# Native PyRadiomics integration

`radaccord.pyradiomics.audit_pyradiomics(image, mask, *, config=None, label=1)`
runs native PyRadiomics and returns its scientific feature values unchanged,
with a separate evidence report and native diagnostics:

```python
from radaccord.pyradiomics import audit_pyradiomics

result = audit_pyradiomics(
    "image.nii.gz", "segmentation.nii.gz", label=1,
    config={
        "setting": {"binWidth": 25.0, "resampledPixelSpacing": [1.3, 1.3, 1.3]},
        "imageType": {"Original": {}},
        "featureClass": {"shape": ["VoxelVolume"], "firstorder": ["Mean", "Variance"]},
    },
)
features = result["features"]
report = result["report"]
```

Inputs are filenames or scalar SimpleITK images. The configuration is the normal
PyRadiomics dictionary with `setting`, `imageType` and `featureClass` sections.
The explicit `label` argument selects the label used for this execution. Native
`diagnostics_*` entries are available in `result["diagnostics"]`; their separation
does not modify any scientific feature value.

## Exact profile and observed boundaries

Profile `pyradiomics-native-original-1` is scoped to PyRadiomics **3.0.1** and
three-dimensional, scalar segment-based extraction. Source image and mask must
have exactly equal size, spacing, origin and direction on orthogonal axes in
millimetres. Source intensities must be finite and the selected ROI nonempty.
Distinct source grids, including merely close grids, are unavailable in this
single-affine profile; native PyRadiomics can support additional configurations.

Before `execute`, RadAccord retains the decoded source, resolves the extractor
settings and declares the expected image/ROI relationships. The declaration
includes native ROI padding, source/target spacing, centre alignment and the
selected interpolation. Original-image extraction without resampling, pre-crop,
and nearest, linear or cubic B-spline resampling are supported. Omitting an
interpolator retains PyRadiomics' resolved default B-spline. Zero target-spacing
components and single-slice ROI dimensions follow the native spacing rules.
The expected feature-input crop is derived from independently sampled ROI
membership; its dimensions are not learned from the observed candidate.

A local subclass delegates the native methods unchanged and observes these
boundaries when PyRadiomics dispatches them:

| Checkpoint | What is observed | What remains unobserved |
| --- | --- | --- |
| `loaded_input` | Image and selected labelmap returned by native loading/preprocessing | File decoding and earlier internal operations |
| `shape_dispatch` | Image, labelmap and bounding box passed to shape dispatch | The shape class's subsequent internal crop and numerical feature implementation |
| `feature_input:original` | Cropped original image and labelmap passed to feature dispatch, plus runtime settings | Feature-class buffers and numerical feature formulae |

No global method is replaced. The adapter neither recomputes native features nor
substitutes preprocessing. It returns evidence after native extraction finishes;
it does not halt a bad operation before feature computation. Checkpoints absent
from the native execution are not invented. The expected/runtime setting
comparison detects both changed and missing declared settings at observed
dispatch boundaries.

Normalization, intensity resegmentation, forced two-dimensional processing,
vector masks and unassigned filtered images are outside this profile. Native
execution retains the requested configuration and values while the relevant
checks abstain. Filtered images are recorded at their actual dispatch boundaries
with unavailable relationship evidence. Different feature formulas and settings
can produce the same observed physical inputs: input consistency never establishes
feature correctness or equivalent discretization.

## Reading the report

Each relationship is `satisfied`, `violated`, `indeterminate` or `unavailable`.
An indeterminate numerical boundary is not a pass. If nearest-neighbour ROI
membership is ambiguous, the subsequent crop is unavailable rather than being
declared from the actual result. Position tolerance is 0.0001 mm and intensity
tolerance 0.0001 source units; the reported index/cast ambiguity bands are
engineering parameters, not certified floating-point or clinical error bounds.

Inspect each checkpoint's **coverage** separately from its operation status.
A correct sampling operation can lose source ROI support or yield an empty ROI.
Those outcomes block feature reuse even if the operation relationship itself is
satisfied. A requirement to re-extract refers to features from the previous
representation; the adapter's returned features come from the current execution.
No status certifies clinical utility, unseen pipeline stages or feature formulas.

The report binds decoded source samples/ROI, configuration, scientific feature
values, checker source hashes and actual native dependency versions. Input
decoding and unit interpretation are trusted. File-backed inputs are read for the
source snapshot and again by PyRadiomics; keep them immutable during the call.
Do not reuse a previous report as evidence of a new, unobserved execution.

## JSON, HTML and methods artifacts

The installed CLI saves only evidence, without exporting images or native
diagnostics. A JSON configuration uses the dictionary structure shown above.

```text
radaccord native --engine pyradiomics --image image.nii.gz --mask segmentation.nii.gz --label 1 --config parameters.json --report evidence.json --html evidence.html --methods methods.txt
```

CLI exit codes describe the aggregate relationship status: `0` satisfied,
`1` violated or indeterminate, and `2` unavailable. They do not replace the
coverage and scope assessment. The standalone HTML report makes no network
requests. The generated methods paragraph is factual to that report and must be
checked against the study; it does not supply acquisition, segmentation, ethics
or statistical details.

The separate evidence JSON avoids local filenames and raw native exception
messages. Native diagnostics, feature metadata and native console logging can
contain private information; handle those separately. Evidence hashes bind
records without exposing those source strings.

After installing RadAccord with its PyRadiomics dependencies, run
`python examples/native_pyradiomics.py --output synthetic_evidence` for a small
synthetic demonstration with JSON, HTML and methods files in a new directory.
Run `python -m unittest discover -s tests -p test_native_pyradiomics.py` for native
development checks, including exact scientific-value agreement with an unmodified
extractor and intentionally altered inputs/settings. These checks are not a
clinical validation study.

Primary documentation: [feature extractor interface](https://pyradiomics.readthedocs.io/en/latest/radiomics.html#module-radiomics.featureextractor),
[customization and preprocessing settings](https://pyradiomics.readthedocs.io/en/latest/customization.html),
and [PyRadiomics 3.0.1 source](https://github.com/AIM-Harvard/pyradiomics/tree/v3.0.1).
The adapter's equations are scoped to the installed 3.0.1 source; online latest
documentation may describe another version.
