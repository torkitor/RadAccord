# MIRP 2.5.0 original-feature boundary profile

`mirp-native-original-3` is a research profile in the local validation candidate.
It has not yet been evaluated on the forthcoming validation set. Earlier
published profiles and their archived results are unchanged.

## What is actually observed

The adapter decodes and promotes one source image and one selected mask before
declaring any expected processing. For sequential MIRP 2.5.0 execution, it uses
the same native workflow factory and `StandardWorkflow.standard_extraction`
loop as the public `extract_features_and_images` function. A temporary wrapper
on each **workflow instance** copies the actual image and mask arguments at
`_compute_radiomics_features(image, mask)`, immediately before delegating to the
unchanged native generator. Neither a class nor a global MIRP function is
patched. The instance callable is restored in `finally`, including when native
extraction raises. Native feature generation, its feature objects, cache
handling, and table assembly remain native.

The report contains two distinct checkpoints:

1. `original_feature_input`: arguments at the original-image feature dispatch.
2. `original_image_export_after_extraction`: the later native image/ROI export.

Each checkpoint compares the actual state with the source/configuration
declaration and checks both `roi_intensity` and `roi_morphology` against the
selected ROI. A clean export does not override a violated dispatch checkpoint.
The observer is at the workflow-to-feature-generator boundary; it does not
observe every feature object's internal discretisation, cropping, or cache
state. It does not verify feature formulae or establish clinical validity.

The supported observation path requires the default sequential scheduler
(`num_cpus=None`, `parallel_backend=None` or `'none'`). Other scheduler choices
still execute the public native function and return its native tables, but
receive unavailable dispatch evidence. More than one workflow or original
dispatch cannot receive acceptance under this profile. No native warnings or
exceptions are silently converted into successful extraction.

## CT processing order and admissibility

The trusted source boundary is **after native decoding and modality promotion**.
`read_image_and_masks` invokes `to_object().promote()`. Promotion to `CTImage`
calls `set_voxel_grid`; `CTImage.update_image_data` applies `np.round` with zero
decimal places. The report explicitly records this boundary. Decoding and this
initial native promotion are not independently certified by RadAccord.

For the admitted configuration, the CT source values must already be integral.
This check depends on the retained source, not on the observed candidate.
The native CT pipeline is:

| Stage | Native operation | Declared independent operation |
|---|---|---|
| Source | Decode/promote; round to nearest even | Retained source boundary; initial rounding outside verification scope |
| Optional AA | Cast to float32, then all separable Gaussian axes | NumPy Gaussian reference with native axis order, boundary and float32 stage storage |
| Optional post-AA CT update | Round the complete Gaussian output, retaining float32 | `antialias_quantisation='nearest_even'` |
| Interpolation | `map_coordinates`, native output storage dtype | Declared nearest, linear or cubic B-spline sampling and storage conversion |
| Final CT update | Round stored interpolation output, retaining its dtype | `output_quantisation='nearest_even'` for floating output |

AA is applied when requested even for an upsampled target. Its Gaussian sigma,
axis order and intermediate dtype remain explicit in the declaration. The CT
round after AA is performed **after all Gaussian axes**, not between axes.
Without AA there is no intermediate quantiser. The final quantiser follows
storage conversion; rounding a binary64 interpolation result before float32
storage would implement a different operation near half-unit boundaries.

`CTImage.update_image_data` performs rounding, not clipping. Its default
lowest-intensity value of -1000 is used by relevant feature/discretisation
settings; it is not a clipping stage in this admitted image-processing graph.
Intensity normalisation, scaling, denoising, bias-field correction and
resegmentation remain outside the profile.

| CT source/storage and processing | Profile |
|---|---|
| float32/float64 identity or nearest without AA | Covered; further CT rounding is idempotent on integral source samples |
| float32/float64 linear or cubic, without AA | Covered with final stored-value quantisation and the conditional numerical envelope |
| float32/float64 or uint8/uint16/int16/int32 with AA and admitted interpolation | Covered; AA explicitly converts to float32, with intermediate and final quantisers |
| uint8/uint16/int16/int32 identity | Covered exactly |
| Those integer types with nearest image and nearest mask interpolation, no AA | Covered under the existing nearest-boundary policy |
| Weighted integer output without AA, unsupported storage, unsupported processing or multiple workflows | Unavailable; native execution is retained |

This CT extension does not expand the earlier integer MR processing profile.
Mask registration retains its independently declared path: nearest-boundary AA,
its native intermediate mask threshold, constant-boundary interpolation, and
the native six-decimal mask rounding followed by the 0.5 inclusion threshold.
Mask registration can be skipped only from source-derived matching geometry.

## Numerical uncertainty and decisions

The optional quantisers default to `None` for previous operation specifications.
For CT, the independent reference uses `np.rint` at the declared locations.
The numerical envelope propagates source/configuration-derived Gaussian
storage intervals through the monotone nearest-even quantiser, then propagates
the resulting field uncertainty through interpolation and the final storage
and quantisation stages. Bounds are never fitted to the observed output.

If possible endpoints quantise to different results, their compatibility with
the observed value does not imply satisfaction. The relationship remains
indeterminate, unless an independent component demonstrates a violation.
Incompatible values are violated. The CT image tolerance is zero: distinct
integral CT values are not accepted by increasing a tolerance. The declared
position tolerance remains 0.0001 mm and the engineering index-boundary band
remains 0.000000001 voxel. The latter and the floating-point envelope are
explicit engineering assumptions, not formal certificates of a native library.

Execution agreement, source-voxel-centre field-of-view coverage, and reuse policy
remain separate. Resampling agreement requires feature re-extraction and does
not establish invariance or safe reuse of previously computed feature values.
Unresolved checks, missing coverage, empty candidate ROIs, or unavailable
observations cannot produce relationship acceptance.

## Example and local verification

```python
from radaccord.mirp import audit_mirp

result = audit_mirp(
    "ct_image.nii.gz", "selected_mask.nii.gz", label=1,
    config={
        "image_modality": "ct",
        "new_spacing": 1.3,
        "spline_order": 3,
        "anti_aliasing": True,
        "base_feature_families": ["statistical"],
    },
)
native_table = result["features"]
report = result["report"]
```

The synthetic tests compare tables exactly against independent invocations of
the public native extraction function. They include negative CT values,
half-unit source values, values below -1000, oblique geometry, identity and
nearest sampling, twelve weighted CT dtype/order/AA combinations, multiple
feature families, an altered dispatch argument with a clean later export,
an altered export with a clean earlier dispatch, observer cleanup on a native
exception, and unavailable profiles. A separate native stage probe records
one CT update without AA and two with AA, checking dtype and rounding order.
These development fixtures are not clinical validation or detection-rate
estimates. They do not read the forthcoming validation set.

Run from the repository root with the MIRP optional dependencies installed:

```shell
python -B -m unittest discover -s tests -p test_mirp.py -v
```

The local verification environment was Windows, Python 3.13.5, MIRP 2.5.0,
NumPy 2.2.6, SciPy 1.15.3, pandas 2.3.3, SimpleITK 2.5.3 and nibabel 5.3.3.
Remote CI for this new candidate is not asserted by these local tests.

The inspected primary source is the installed MIRP 2.5.0 distribution:
`mirp/_data_import/read_data.py`, `mirp/_images/generic_image.py`,
`mirp/_images/ct_image.py`, `mirp/_image_processing/anti_aliasing.py`,
`mirp/_masks/base_mask.py`, `mirp/_workflows/standardWorkflow.py`, and
`mirp/extract_features_and_images.py`. Relevant methods are
`read_image_and_masks`, `GenericImage.promote`, `GenericImage._interpolate`,
`CTImage.update_image_data`, `gaussian_preprocess_filter`,
`StandardWorkflow.standard_extraction` and `_compute_radiomics_features`.
