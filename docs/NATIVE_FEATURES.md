# Reproduce the native PyRadiomics subset

This fixed descriptive subset measures native feature changes after the declared sampling operations. It uses six released volumes, not six established independent participants. The [plan](../protocol/native_feature_plan.json), [extraction/analysis script](../scripts/run_native_feature_subset.py) and unchanged [adapter](../software/adapters.py) are part of the verified pre-evaluation freeze. See [DATA_SOURCES.md](DATA_SOURCES.md) to obtain the source data and materialize the private native inputs.

## Fixed inputs and comparisons

The first three lexicographic IDs per collection are hippocampus_001, hippocampus_003, hippocampus_004, spleen_10, spleen_12 and spleen_13. Each has five planned roles: source_working_crop, isotropic_0p8mm, isotropic_1mm, isotropic_2mm and wrong_image_kernel. This fixes 30 extraction assignments, without replacement if any input or native operation is unavailable. All original positive annotation labels are combined as selected label 1.

For each volume, compare the three correct resampled representations with the working crop, and compare wrong_image_kernel with the correctly linearly interpolated 0.8 mm representation. There are **24 planned comparisons**: 18 resampling contrasts and six controlled-kernel contrasts. No additional comparison is selected after inspecting results.

The unchanged PyRadiomics 3.0.1 profile comprises 72 enabled, nondeprecated 3D shape, first-order, GLCM and GLRLM features from the original image type. Bin width is 25; normalization, internal image resampling and mask correction are disabled. `force2D=False`, `additionalInfo=False`, `voxelArrayShift=0`, `weightingNorm=None` and `symmetricalGLCM=True`. Native discretization is retained. Extraction uses one persistent adapter process and one native thread, with a default 7,200-second process timeout. This is a resource policy, not a feature-definition change.

## Install and run

Use a separate Python 3.10 environment for the tested native stack: PyRadiomics 3.0.1, NumPy 1.23.5 and SimpleITK 2.2.1. The recorded run used Python 3.10.11. On Windows, from the repository root:

```text
py -3.10 -m venv .venv-pyradiomics
.venv-pyradiomics/Scripts/python.exe -m pip install -r software/requirements-pyradiomics.txt
```

On POSIX, create the environment with `python3.10 -m venv .venv-pyradiomics` and use `.venv-pyradiomics/bin/python` as its executable. The orchestration script uses the standard library and accepts every location explicitly. The following Windows command assumes that clinical processing produced the private manifest described in [DATA_SOURCES.md](DATA_SOURCES.md):

```text
python -B scripts/run_native_feature_subset.py --phase all --plan protocol/native_feature_plan.json --manifest ../msd-private/native-inputs/manifest.jsonl --private-output ../msd-private/native-run --public-output results/reproduced_native --adapter software/adapters.py --python .venv-pyradiomics/Scripts/python.exe
```

For POSIX, replace only the final interpreter location with `.venv-pyradiomics/bin/python`. The script verifies the frozen adapter and plan, exact input assignments, image/mask hashes and PyRadiomics version. It does not infer intended settings from feature outcomes. Input files are checked again immediately before extraction. Private jobs and logs must be outside the software repository, and public/private outputs must be separate, non-nested directories.

`--phase all` runs `prepare`, `extract` and `analyze` in sequence. Each phase may also be invoked separately with identical arguments. Preparation requires a fresh private output directory; extraction refuses existing native output; analysis requires a fresh public output directory. Existing first results are never replaced.

To reproduce only the public numeric summaries from a retained private native run, use `--phase analyze` with that private directory and a new public output directory. This does not reopen images or rerun PyRadiomics. The historical private native records are not distributed, because their warning/error fields may contain local diagnostic messages. Fresh native reproduction therefore requires obtaining the external data and executing the frozen workflow; the published derived feature values and differences remain available for numerical inspection.

## Quantities and missingness

Each planned feature contrast reports its finite availability, signed difference, absolute difference and `abs(candidate-reference)/abs(reference)`. If the reference is exactly zero, the relative value is unavailable and explicitly flagged; the absolute comparison remains available. Nonfinite native values, missing features, absent inputs, native failures and derived arithmetic overflow remain explicit.

A numerical change exceeds the archived scalar rule when:

`abs(candidate-reference) > 1e-6 + 1e-5 * abs(reference)`.

The reference is the working crop for correct-resampling contrasts and the correct 0.8 mm output for the kernel contrast. This is a numerical descriptor, not a clinical threshold, statistical equivalence margin or proof of incorrect feature computation. Correct interpolation can change radiomic measurements.

Every contrast retains its planned 72-feature denominator and separately counts finite pairs, evaluable pairs, changes beyond tolerance and unavailable comparisons. Fully analyzed, partially analyzed and unavailable contrasts are distinguished. VoxelVolume, Mean and population Variance are also retained separately, in mm³, native intensity units and squared native intensity units. MRI intensity units are not HU. No feature rows are treated as independent patients, and no patient-level confidence intervals, prediction metrics or clinical-risk estimates are computed.

## Inspect the recorded results

The retained first run has 30/30 extractions, 2,160/2,160 finite feature values and 24/24 complete contrasts with 1,728 comparable feature pairs. MRI at 1 mm reproduced the source vector in all three selected volumes. The deliberately incorrect image kernel changed first-order and texture values while preserving the occupied-voxel volume. These observations concern the selected volumes and controlled operations; they are not a clinical effectiveness study or evidence of a defect in PyRadiomics.

The public numeric records are:

- [Native values](../results/native_feature_subset/native_features.jsonl): approved identifiers, input hashes and native feature values.
- [Per-feature differences](../results/native_feature_subset/native_differences.jsonl): all 24 × 72 planned feature contrasts.
- [Per-contrast summaries](../results/native_feature_subset/native_comparisons.jsonl): counts, availability and the three named volume/intensity quantities.
- [Run summary](../results/native_feature_subset/native_summary.json): frozen hashes, actual native versions, settings and collection-level availability.

An additional [independent arithmetic audit](../results/native_feature_subset/native_independent_audit.md) gives medians and ranges by collection/operation; its [complete JSON](../results/native_feature_subset/native_independent_audit.json) retains all 24 volume-level landmark rows and the source-record hashes. This audit recomputes the numerical comparisons and checks the published values against the retained native records without reopening images.

These files exclude paths, raw warnings, error messages and logs. Numerical equality after resampling is not an acceptance criterion. Review the sampling/support decisions separately, then extract features on the intended candidate whenever the sampling changed.
