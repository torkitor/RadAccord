# Changelog

## 1.2.0rc3 — 2026-09-09 (unpublished CLI compatibility candidate)

- Convert CLI image/mask filenames to strings before native dispatch. An actual
  MIRP CLI test exposed that `pathlib.Path` arguments raised `NotImplementedError`
  even when the same supported files succeeded through the string-based API.
- Add a regression comparing the CLI with the string-based API, including exact
  native features and equivalent evidence when MIRP is installed. Engine-free
  test environments exercise the same filename contract using a strict stand-in.
- Preserve the rc2 wheel and completed scientific evaluation in its
  [immutable refinement archive](data/RadAccord-native-refinement-2.zip).
  Scientific adapter, operator, numerical and evidence modules are unchanged;
  version metadata and the CLI dispatch correction do not imply a new cohort
  evaluation or independent validation.

## 1.2.0rc2 — 2026-09-09 (unpublished source candidate)

- Pin the MIRP 2.5.0 extra to pandas 2.3.3 after reproducing a uint8 MR IVH
  extraction incompatibility with pandas 3.0.2. The dependency warning is
  documented; no MIRP source is modified.
- Admit uint8, uint16, int16 and int32 original-image identity checks when image
  interpolation is disabled, no anti-aliasing is active and ROI registration is
  skipped. Identity intensities are checked exactly. Integer resampling and
  uncovered integer types retain unavailable evidence and native feature values.
- Add synthetic IVH and integer-scope regressions with exact native DataFrame
  comparisons. Eight MIRP source tests passed in the isolated compatibility
  environment; this does not constitute an installed-rc2-wheel verification.
- Introduce conditional source-derived numerical envelopes in the second native
  profiles, retaining the original nominal reference and decision. Unresolved
  rounding remains indeterminate; the engineering assumptions are not a
  certification of native arithmetic or clinical validity.
- Invalidate previous JSON/HTML/methods results before native execution and
  replace report files atomically. Process failures and incomplete sampling
  reports cannot reuse a previous positive HTML report. New regressions cover
  native exceptions/aborts and child launch/crash/inconsistent-exit cases.
- Add separate installed-wheel/native CI specifications for Ubuntu and Windows,
  with explicit test-execution requirements and optional historical writer
  regression jobs. No completed remote run is asserted by this entry.

The rc1 wheel and first native calibration remain preserved. The completed rc2
evaluation and source freeze are retained in the refinement archive. Installed
unit and API checks passed; an additional real MIRP CLI check exposed the filename
dispatch issue corrected in rc3. No result from the first calibration is
retrospectively replaced by these changes.

## 1.2.0rc1 — 2026-09-09 (retained native calibration candidate)

- Introduce an installable package, deferred native-engine imports, PyRadiomics
  and MIRP entry points, declared preprocessing relationships and observed
  native image/ROI reports.
- Retain the initial native source freeze and evaluation outcomes in the
  [native calibration archive](data/RadAccord-native-calibration-1.zip), including
  numerical-boundary alerts and the MIRP/pandas extraction incompatibility.
- Record the separately verified Windows wheel and its bounded installation
  checks in [WHEEL_VERIFICATION.md](docs/WHEEL_VERIFICATION.md).

## 1.1.0rc1 — 2026-09-09 (local candidate)

- Add an independent NumPy witness for declared crop, padding, reorientation and
  nearest/linear sampling, with an explicit boundary-indeterminate state.
- Separate sampling fidelity, source ROI voxel-centre coverage and measurement
  reuse; retain empty candidates, failed checkpoints and unavailable cases.
- Add file/plan verification, standalone HTML reports and generated synthetic demos.
- Retain the first evaluation: 448 cases from 32 reserved synthetic volumes and
  4,214 cases from 301 public anatomical volumes. The 11 clinical control
  abstentions and all 203 inactive perturbations across both evaluations remain
  explicit; constructed faults are not attributed to native-library defects.
- Include the fixed six-volume PyRadiomics subset, 30 extractions and 24 contrasts,
  with complete derived values and explicit numerical-comparison denominators.
- Add audited, traceable CSV/JSON summaries, the relocated sixteen-file sampling
  freeze and candidate CI steps for its checks, demos and exact summary replay.

This is an unpublished local release candidate. Updated remote CI has not run.
The scientific 1.0.0 ZIP, full-grid/scalar implementations, original alerts,
revised profile and their freezes are unchanged. The retained `radaccord.py`
entry point still identifies its historical full-grid profile as 1.0.0;
`radaccord_sampling.py` is the new sampling entry point.

## 1.0.0 — 2026-09-07

- Named RadAccord entry point for the revised physical-consistency profile.
- Original and revised protocols, unmodified engine adapters, synthetic examples
  and complete archived study evidence.
- GitHub distribution with a physical-correspondence demo, exact record
  restoration, repository checks and documentation for use and citation.

The GitHub presentation and onboarding additions preserve the frozen scientific
modules and the complete original scientific archive. They do not add feature
obligations, revise numerical tolerances or retrospectively change the study.
The original strict PyRadiomics profile and its alerts remain available.
