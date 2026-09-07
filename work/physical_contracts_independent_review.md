# Independent development review of physical contracts

7 September 2026. Scope limited to development seeds 0–11. No held-out seed, generated case or manifest was read. P1 and the preceding manuscript/software were not modified.

**Outcome:** all 10 unittest methods passed in 22.896 seconds. The full signed-permutation orbit was checked for every development phantom: **576 representations**, each with inverse recovery, an independent SimpleITK array/physical-position comparison, NIfTI write/read, and the transport witness after decoding. These are software validation cases, not independent patient observations or a fault-detection sensitivity estimate.

Test file: `../tests/test_physical_contracts.py`. Invocation from repository root:

```powershell
& '.venv/Scripts/python.exe' -B -m unittest discover -s 'manuscript/er/p2_standalone_2026-09-07/tests' -p 'test_physical_contracts.py' -v
```

Additional independent checks cover two header calibrations × 12 seeds, relabelling to label 7, correct isotropic spatial and positive-affine intensity laws, full-interior voxel and ROI changes, numerical-tolerance boundaries, native image/mask affine mismatch reporting, unsupported units, conflicting qform/sform, shear, complex/nonfinite images, fractional/nonfinite masks, zero labels and incorrect sign-vector length. The coordinate oracle uses SimpleITK's own image transport and `TransformIndexToPhysicalPoint`, converted from LPS to RAS, rather than reusing the implementation's matrix constructor.

The read-only review reproduced an integer energy overflow in `analytic_anchors`: 125 uint16 voxels valued 100 gave 4816 instead of 1,250,000. It also identified silent acceptance of unsupported complex/mask domains and overlong sign vectors. These findings, plus the physical-unit/shear/qform limitations, were sent to the root before any core change. The root corrected `physical_contracts.py`; the passing tests include corresponding regressions. I did not edit that module.

The image/mask geometry return value must remain part of the combined acceptance policy. The Frame holds one affine for the image; the separate `same_affine` result conveys the mask's physical mismatch. A caller must not ignore it just because the voxel correspondence test alone passes.

## Native worker resource policy

`../software/adapters.py` now exposes `configure_worker_threads(threads=1)` and the JSONL CLI defaults to `--threads 1`. OpenMP/BLAS/ITK thread environment variables are set before engine imports and the SimpleITK global thread count is set through its public API. The direct extraction API does not silently reconfigure a host application's threads. MIRP's `ibsi_compliant=True` is explicit. The TotalEnergy comment now correctly says that sum of squares is multiplied by the volume of one voxel, not the ROI volume.

The preceding seven-job development pilot was repeated with one native thread in both engines. **All numeric feature values, status outcomes and captured warnings were identical** to the preceding pilot (maximum scaled feature difference zero). Warm success timings were 0.013–0.016 s for PyRadiomics and 0.318–0.502 s for MIRP. These small pilot timings are not the final benchmark runtime.

Evidence: `adapter_pilot_pyradiomics_threads1.jsonl`, `adapter_pilot_mirp_threads1.jsonl`, `check_adapter_thread_caps.py` and `adapter_thread_caps_check.json`. The latter reports `checks_passed: true`. No heavy extraction benchmark was started by this review.

## Later development revalidation

The root replaced the witness's call to its transformation generator with independent whole-grid source indexing `i = Bj`. The complete physical unittest suite passed again (10 methods; 576 representations; 21.072 seconds). Two file-level CLI probes on seed 0 passed: a legitimate identity is accepted, and an undeclared joint 11-mm origin change is rejected specifically by the spatial witness while native extraction and scalar obligations remain satisfied. See `verify_cli_probe_check.json`.

The MIRP CT branch used during initial feasibility rounds fractional intensities as part of its intended HU processing. The final MR/nonnegative-FBS context, its explicit guard and passing seed-0 analytic/representation checks are documented in `fractional_context_decision.md`. This correction was made during development, without relaxing tolerances or inspecting held-out data.

A bounded native profile on seeds 0 and 2 explains the unexpected runtime dependence on ROI size. Seed 2 has 1586 voxels; the native spatial-autocorrelation routine uses the N<2000 branch, invoking a Python distance lambda 1,256,905 times. `_spatial_distribution` consumed 13.16 of 14.46 profiled seconds (about 91%). Convex hull and principal-axis calculations took only about 0.0045 and 0.0025 seconds. Seed 0 has 3418 voxels and uses the N≥2000 vectorised-per-row branch. Smaller phantoms are therefore not necessarily faster. The package was not modified. Profiling overhead and concurrent workers make these unsuitable as final runtime estimates; `mirp_development_profile.json` establishes the code location responsible.
