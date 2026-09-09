# Verify spatial preprocessing before reusing radiomic measurements

This development extension checks a **declared sampling operation** between a retained source and its candidate image/ROI. It supports integral crop, padding and reorientation, plus nearest-neighbour and trilinear resampling with explicit grid, support and fill conventions.

The scientific 1.0.0 release and its original full-grid contracts remain available unchanged. The new sampling profile is a separate implementation and evaluation; the original study counts do not validate its additional operators.

## Two different questions

1. Did the operation produce the intended grid, sampled intensities and selected ROI?
2. Does an applicable obligation support reuse of earlier measurements?

A correct resampling operation can change intensities, voxel membership and radiomic values. Its successful execution therefore requires new feature extraction. For an integral operation that preserves the selected input samples, RadAccord reports **input ROI preserved**; reuse still depends on the feature, configuration and required surrounding context. This is not a universal feature-equivalence certificate.

## Declare the operation before running it

Let A map source voxel centres to RAS millimetres. The declaration supplies B, mapping candidate indices to source indices, and an optional intended physical map L. Expected candidate geometry is **L A B**. B must come from the intended preprocessing specification, not from the observed candidate affine: reconstructing intent from a faulty output can hide its error.

The declaration includes:

- `index_map`: a finite, nonsingular 4 × 4 destination-to-source affine.
- `candidate_shape`: the three intended dimensions.
- `interpolation`: `nearest` or `linear` for image values; the selected ROI always uses nearest-neighbour sampling.
- `outside_value`: the image fill in final decoded intensity units; the mask fill is background.
- `position_atol_mm` and `intensity_atol`: explicit absolute tolerances for this profile. Intensity relative tolerance is zero.
- Optional `world_map`, `intensity_gain` and `intensity_offset`, defaulting to identity, one and zero.

The discrete source support is `[-0.5, size-0.5)` along each axis. Nearest selects `floor(index+0.5)`; linear interpolation clamps to edge centres within the exterior half-voxel rim. These are declared operator conventions, not a model of continuous anatomy. Numerical boundary ambiguity is reported separately under the frozen profile; it is not converted into a passed obligation.

## Use as a library

From the repository root, after installing the core requirements:

```python
from radaccord_sampling import verify_sampling

report = verify_sampling(
    "source_image.nii.gz", "source_mask.nii.gz",
    "candidate_image.nii.gz", "candidate_mask.nii.gz",
    sampling=planned_sampling,
    source_label=1, candidate_label=1,
)
```

`planned_sampling` is the declaration prepared before generating the candidate. Source inputs retain the original finite 3D, orthogonal-axis, millimetre NIfTI domain. Conflicting coded spatial forms are unavailable. The candidate may have an empty ROI so that disappearance can be reported rather than silently removed from evaluation. No native radiomics engine is required for this input-level check.

## Audit files or a sequence of checkpoints

```text
python radaccord_sampling.py --plan plan.json --report report.json --html report.html
```

The plan has `schema_version: "1.0"` and a `steps` list. Each step supplies `source` and `candidate` objects with `image`, `mask` and optional `label`, plus its `sampling` declaration. File paths are resolved relative to the plan. Reports contain role-based hashes rather than input paths; the standalone HTML contains no external scripts or network requests.

For multiple steps, each input must match the preceding retained output and selected label. Reports distinguish the first violated checkpoint, the first unverified checkpoint and the first checkpoint requiring review. This observes supplied boundaries and does not identify an unobserved internal error or automatically diagnose the cause. The first source and the declarations remain trusted.

## Interpret the evidence

| Outcome | Meaning and next action |
|---|---|
| `input_roi_preserved` | Integral selected-input preservation was checked. Apply a feature/configuration contract before reusing measurements. |
| `sampling_satisfied_reextract` | The declared sampling passed. Extract features on the candidate again. |
| `roi_support_lost` | The candidate field of view excludes selected source voxel centres. Review the ROI and intended coverage. |
| `sampled_roi_empty` | Sampling leaves no selected candidate voxel. Review the grid before attempting feature extraction. |
| `violated` | An observed component contradicts the declaration. Review that component before extraction or reuse. |
| `indeterminate` | The specified numerical profile cannot establish the relevant obligation. It is not accepted. |
| `unavailable` | Inputs, declaration or checkpoint linkage could not be evaluated. It is not accepted. |

Coverage is explicitly defined using **source ROI voxel centres** mapped into the declared destination field of view. It does not prove preservation of continuous anatomical support, volume or an unspecified filtering halo. Mask correspondence and geometric coverage are separate: a correctly executed crop can still remove the ROI, and a correctly executed resampling can change its discrete voxel count.

The frozen evaluation uses an index-boundary ambiguity band of `1e-9` source-index units. This engineering policy is not a universal floating-point error bound. Distinct discrete alternatives near a nearest-neighbour or support boundary yield indeterminacy; a value incompatible with every alternative yields a violation. Nominal discrepancies are retained. This is not a relaxed acceptance tolerance. The position and intensity tolerances (`1e-4` mm and `1e-4` decoded units in the study) are numerical limits, not clinical equivalence margins.

Image–mask agreement at the file interface also checks the maximum physical corner displacement. Small matrix-element differences alone do not establish agreement throughout a large field of view.

## Runnable synthetic examples

```text
python scripts/demo_sampling.py --output outputs/my_sampling_demo
```

Open `resample_reextract.html` in that output folder. A correctly executed crop preserves the input ROI; subsequent grid resampling requires re-extraction. The separate shared-origin example blocks the sequence at checkpoint 3. All image files are generated synthetic arrays. Prepared examples and plans are also available in `examples/sampling`.

A Methods statement, after actually running the checks:

> We used RadAccord's declared-sampling profile to compare retained source and candidate images and segmentations with the prespecified preprocessing operations. Sampling fidelity, source ROI voxel-centre coverage and unverified obligations were recorded separately; radiomic features were re-extracted after changes in sampling.

Report the software version and commit or source hash, the saved checkpoints, interpolation and outside-value policies, position/intensity/boundary tolerances, selected labels and counts of satisfied, violated, indeterminate and unavailable obligations. State which features were re-extracted and which, if any, were reused under a separate applicable feature contract.

## Reproduce the development evaluation

The study driver uses unmodified SimpleITK operations as producers and a NumPy witness that does not call those interpolation routines. Run synthetic development independently of any clinical data:

```text
python scripts/run_sampling_study.py --synthetic --output results/development
```

Clinical execution requires separately downloaded, appropriately cited source datasets and the corresponding evaluation freeze. Clinical inputs are not included in this repository. Preserve all attempted cases, inactive perturbations, boundary indeterminacy and unsupported inputs when interpreting the reports. Constructed errors in study wrappers are not observations of defects in their underlying libraries.
