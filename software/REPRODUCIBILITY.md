# Reproducing the verification benchmark

This document describes how to reconstruct the synthetic benchmark and interprets the completed PyRadiomics and MIRP evaluations. It preserves the initial profile and the subsequent, separately frozen PyRadiomics revision. The benchmark contains no clinical images or patient-derived masks.

## Runtime separation

Use three environments: a core Python environment with NumPy and NiBabel; a PyRadiomics environment; and a MIRP environment. An engine can require a different Python or NumPy version from the core. Keep them separate and supply their executable paths to `benchmark.py run` or the recommended `verify_refined.py`. The original `verify.py` reproduces the initial strict profile.

The recorded development environments provide the following version reference:

| Environment | Python | Principal packages |
|---|---|---|
| Core | 3.13.5 | NumPy 2.2.6; NiBabel 5.3.3 |
| PyRadiomics | 3.10.11 | PyRadiomics 3.0.1; NumPy 1.23.5; SimpleITK 2.2.1 |
| MIRP | 3.13.5 | MIRP 2.5.0; NumPy 2.2.6; SimpleITK 2.5.3; NiBabel 5.3.3 |

The MIRP environment also records SciPy 1.15.3, pandas 3.0.2 and scikit-image 0.26.0. This table identifies the measured environment; it is not a complete transitive dependency lock or an assertion that every platform supplies matching binary packages.

After creating the separate environments with the indicated Python versions, install the supplied requirements in the corresponding interpreter. With the core environment active, the Windows example is:

```text
python -m pip install -r requirements-core.txt
.venv-pyradiomics/Scripts/python.exe -m pip install -r requirements-pyradiomics.txt
.venv-mirp/Scripts/python.exe -m pip install -r requirements-mirp.txt
```

Use the corresponding `bin/python` executable paths on POSIX systems. The files pin the principal tested packages; retain each actual environment manifest as part of the run.

For each native environment, `adapters.py --environment` records Python, platform and installed package versions. The benchmark saves these as `pyradiomics_environment.json` and `mirp_environment.json`, together with worker settings. Literal reproduction requires matching the recorded versions and configurations. A run with different versions is a new compatibility evaluation, even if its outcomes agree.

The worker runner sets numerical-library and ITK thread limits to one per worker. The replication commands below use 12 worker processes for each engine. Running both engines simultaneously adds their resource demand; the commands are listed sequentially.

## Native extraction settings

Both adapters request original, unfiltered 3D morphology/shape, first-order/statistical, GLCM and GLRLM features. They request no image resampling, bias correction or intensity normalisation. The selected ROI is identified by its label.

PyRadiomics uses its native fixed bin width of 25 for the reference settings, symmetric GLCM, no distance weighting, and `voxelArrayShift=0`. MIRP uses its MR branch with fixed bin size 25 and a lower resegmentation bound of 0; the upper bound is unspecified. This fixes the intended lower discretisation anchor while preserving the ROI only when its intensities are nonnegative. The supplied phantom protocol is designed within that domain. Inputs containing negative selected-ROI intensities require a different, explicitly evaluated contract; this adapter must not silently be treated as a generic signed-intensity extractor.

The two engines need not discretise or name features identically. Each candidate is compared with its own engine's source extraction under the appropriate law. Cross-engine feature equality is not a criterion. Unsupported intensity or spatial laws and outputs needing an unimplemented axis-labelled relation are reported as not applicable.

## Fixed comparison limits

| Property | Implemented comparison |
|---|---|
| Index correspondence and selected ROI | Exact full-grid correspondence under a signed permutation and integral offset |
| Physical position | Maximum affine corner displacement ≤ 0.0001 mm |
| Decoded intensity | Maximum absolute discrepancy ≤ 0.0001 intensity unit |
| Assigned scalar relations and anchors | Absolute tolerance 0.000001 plus relative tolerance 0.00001 against the expected value |

The position comparison bounds affine displacement throughout the rectangular grid. It does not establish geometric truth of the retained source. Intensity tolerances are in the input's declared units and are not a clinical error threshold. Source arrays are handled in float64; the supplied NIfTI writer encodes floating image samples as float32 and labels as int16. Encoding calibration is applied through the NIfTI slope and intercept.

These are the released implementation's fixed limits. Changing them, the generators or the extraction settings changes the evaluation protocol and must be recorded.

## Development replication

From the `software/` directory containing `benchmark.py`, with the core environment active:

```text
python benchmark.py prepare runs/development --first 0 --count 12
python benchmark.py run runs/development --engine pyradiomics --python .venv-pyradiomics/Scripts/python.exe --workers 12
python benchmark.py run runs/development --engine mirp --python .venv-mirp/Scripts/python.exe --workers 12
python benchmark.py evaluate runs/development
```

On POSIX systems replace the two engine executable paths with the corresponding `bin/python` paths. A case manifest or completed native output is not overwritten. Use a fresh output directory for a new run.

Development uses seeds 0–11. Each seed produces an asymmetric synthetic field with oblique, anisotropic geometry, the full 48-element signed-permutation orbit, equivalent encoding/relabel controls, known covariant transformations and a changed-bin-width control for abstention. The orbit includes identity, and a separate source extraction supplies the reference.

## Phase 1: initial reserved evaluation

The initial reserved protocol uses exactly seeds 1000–1063 and the eight fault definitions supplied with the package. It requires `protocol/final_freeze.json`, whose SHA256 entries bind 16 protocol, implementation, requirements and test files. The guard refuses a different seed range or a file-hash mismatch. A missing final freeze is an incomplete evaluation package, not permission to create a replacement freeze after inspecting outcomes.

Run the reserved evaluation only with that published, unchanged protocol:

```text
python benchmark.py prepare runs/heldout --first 1000 --count 64 --heldout
python benchmark.py run runs/heldout --engine pyradiomics --python .venv-pyradiomics/Scripts/python.exe --workers 12
python benchmark.py run runs/heldout --engine mirp --python .venv-mirp/Scripts/python.exe --workers 12
python benchmark.py evaluate runs/heldout
```

The fault modules alter owned adapter payloads: slice order, contiguous-buffer interpretation, ROI indexing/interpolation, direction convention, voxel origin convention, calibration order and premature integer conversion. The engines themselves are not modified. Each fault has an activation precondition; preserve attempted cases that are inapplicable or fail to produce an extractable input. Do not replace a seed or omit a fault because it produces little downstream feature drift.

The reserved seeds are unseen instances from the specified synthetic generator. They are not new patient cohorts or an external validation population. Faults are applied to the specified primary representation rather than to every possible product of fault and orientation. Additional orbit and repeat executions are dependent evaluations of a base phantom.

The initial strict PyRadiomics profile flagged 36 of 3200 equivalent representations, all in one phantom and involving MeshVolume, SurfaceArea, SurfaceVolumeRatio and Sphericity. These alerts and the original frozen decisions remain part of the evidence. They are not retrospectively replaced by revised-profile decisions. MIRP uses the original, unchanged measurement profile; the refinement below does not modify it. Its completed 4608-call evaluation had no native extraction, schema or finiteness failures. There were no alerts among 3200 equivalent representations; 256 covariant controls satisfied assigned laws and 64 changed-bin-width controls abstained. The physical witness detected all 512 injected transport violations, feature relations detected 384 and anchors 320. All 512 repeated feature mappings were identical, so repeat comparison detected no transport violations. These counts were independently audited against the complete native output and unchanged input manifest.

## Phase 2: new-input follow-up of the revised profile

`validation_refinement.py` implements the revision without editing the initial files. For PyRadiomics transformations whose kind is `reindex`, the four mesh-derived comparisons become `not_applicable` with the explicit reason that they are not assigned in this acceptance profile. Their initial comparison records remain available. This is a restriction of checked obligations, not a claim that their geometric definitions cease to be invariant or that a third-party implementation is defective. Scaling laws for these measures, other transformation kinds, native values, all tolerances, anchors, geometry and the physical witness remain unchanged.

The follow-up was fixed after observing the initial PyRadiomics alerts and before generating its new inputs. `protocol/refinement_freeze.json` binds the same 16 original files plus `validation_refinement.py`, `verify_refined.py` and `protocol/refinement_protocol.json`: 19 files in total. Both manifests' file hashes remain valid. The additional freeze does not replace the initial freeze or make the first evaluation independent of the profile-selection decision.

Preparation uses the fixed seeds 2000–2031; it accepts no seed-range arguments. Sixteen even-numbered seeds use the original generator. Sixteen odd-numbered seeds add two diagonally selected samples in a verified background patch to create an alternating binary face. This enrichment defines the intended source phantom; it is not an injected transport fault. All eight transport-fault families are already known at this stage.

Run the published follow-up with PyRadiomics in a fresh directory:

```text
python validation_refinement.py prepare runs/refinement
python benchmark.py run runs/refinement --engine pyradiomics --python .venv-pyradiomics/Scripts/python.exe --workers 12
python validation_refinement.py evaluate runs/refinement --engine pyradiomics
```

Use `validation_refinement.py evaluate` for the revised-profile summary, not `benchmark.py evaluate`. Preparation verifies the follow-up manifest against the actual files. Do not regenerate either freeze after inspecting results. Running the same inputs with another engine is an additional compatibility evaluation, not the reported PyRadiomics follow-up.

### Observed follow-up counts

| Quantity | Count and interpretation |
|---|---|
| New base phantoms | 32: 16 original-generator and 16 enriched |
| Planned and retained cases | 2048: 32 references, 1600 equivalent representations, 128 covariant changes, 32 changed-bin-width controls and 256 fault cases |
| Planned native calls | 2304, including one extra extraction for each fault case |
| Scheduled and completed native calls | 2302; the two boundary rejections were not submitted for extraction |
| Equivalent representations | 1598 analysable of 1600 attempted; 2 unavailable |
| Original strict relation alerts on the analysable equivalents | 384/1598 |
| Revised relation and combined-verifier alerts on the analysable equivalents | 0/1598 |
| Injected transport violations detected by the combined revised verifier | 256/256 |

The unavailable equivalents are `2015_R06` and `2015_R07`. Their coded qform and sform matrices disagree beyond the frozen input-consistency tolerance. They remain recorded among attempted controls and are not accepted equivalents, successful feature comparisons or failures of native extraction. No headers or thresholds were changed to admit them. Thus the result is zero revised alerts among 1598 analysable equivalents, not 1600 successful comparisons. The initial and follow-up alert rates have different sample construction and must not be pooled or interpreted as clinical false-positive rates.

The revised follow-up summary reports 128/128 covariant controls without violations. Changed-bin-width controls concern explicit abstention; a summary count of zero violations does not turn their feature relations into passed obligations. Detecting all injected transport violations in this constructed set does not establish that every associated scalar was wrong or estimate sensitivity in a clinical pipeline.

## Output files and denominators

| File | Contents |
|---|---|
| `input_manifest.json` | Seed range, protocol role and manifest hash |
| `cases.jsonl` | Intended transformations, activation states, boundary checks and direct references |
| `jobs.jsonl` | Explicit file inputs, labels and extraction settings |
| `pyradiomics.jsonl`, `mirp.jsonl` | Native outputs, failures, warnings and per-job durations |
| `*_environment.json`, `*_run.json` | Engine versions, worker count and run-level duration |
| `decisions.jsonl` | Decisions for each engine and case |
| `feature_diagnostics.jsonl` | Per-feature expected values, discrepancies, reasons and repeat comparisons |
| `summary.json` | Group counts; interpret alongside activation and error records |
| `pyradiomics_refined_decisions.jsonl` | Follow-up case decisions, retaining initial and revised relation status and boundary exclusions |
| `pyradiomics_refined_summary.json` | Follow-up attempted/analysable counts and separate original/revised alert counts |

Report base phantoms, representations, fault families and extraction jobs separately. A control for not-applicable relations is not an accepted invariant transformation. Report absent references, boundary/reader errors, native extraction failures and nonfinite required outputs according to their recorded states. A missing result must not be converted into a favourable comparison.

Native feature values remain in the engine JSONL outputs for both profiles. The follow-up decisions retain the initial and revised status; the released comparison functions can regenerate the individual comparisons from those native outputs. For a single source/candidate verification, `verify_refined.py` additionally stores the complete `initial_relations` and each withheld feature's `initial_obligation` in its report.

The report's `io_and_witness_seconds` includes writing, reading and checking. It is not the isolated computational cost of the witness. A fault and its repeated job can be assigned to different worker processes; the repeat result concerns two executions of the same saved input and does not necessarily describe consecutive calls within one process.

## Adapting the protocol

For an existing source/candidate pair, use `verify_refined.py` as shown in the README. Use `verify.py` only when the original strict profile is intended. For a new synthetic experiment, create a separate generator/configuration and output directory, document its permitted transformations and activation conditions, and preserve its protocol before evaluating reserved cases. Do not relabel a changed study as a reproduction of the frozen one.

A trusted source and transformation record remain essential. The file-boundary check cannot detect a geometrical error already present in that source, guarantee every internal backend state, certify arbitrary interpolation or deformation, or determine biological relevance. The direct anchors cover selected discrete measurements; passing them does not establish correctness of every returned feature. Clinical models and patient-management effects require separate evaluation.

## Privacy when reproducing or sharing a run

The distributed commands use example-relative paths. Benchmark input manifests store image and mask paths relative to the run directory, and environment summaries omit host names and interpreter paths. The native adapter removes known input paths from recorded warning and error text; the verification CLI uses a generic unavailable message instead of an exception traceback. These measures do not make arbitrary user inputs or third-party messages anonymous. Raw worker `.log` files capture library stdout/stderr and may contain environment paths: retain them privately, and review reports before sharing a run made from your own images. Do not include local environments, caches or worker logs in a public reproduction archive.

The reproducibility materials are distributed with the manuscript's Supplementary Software 1 ZIP under the package's Apache License 2.0 terms. Its source and protocol manifests identify the supplied version. An optional later archive deposit is a separate publication step; no unpublished or unrelated DOI is a substitute for the identifier of that deposit.
