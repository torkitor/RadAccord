# Scientific archive guide

**RadAccord: software for physical consistency testing before radiomic feature reuse in research**

Software release 1.0.0, 7 September 2026. RadAccord is a proper name, not an acronym.

This scientific supplement contains the frozen verification method, the complete final native feature outputs and decision records, and independent audits. It contains synthetic data only. Large generated NIfTI volumes are omitted; six small synthetic example files are included. No clinical datasets are included. `LICENSE` retains the source repository's Apache 2.0 terms. External dependencies retain their own licences.

This guide describes the original scientific archive, available in
[data/RadAccord-1.0.0.zip](../data/RadAccord-1.0.0.zip). Commands run from its
extracted `RadAccord/` root unless stated otherwise. For the GitHub checkout,
run `python -B scripts/restore_records.py` before commands that read JSONL records.
The archive's validation inventories are retained under
[release_history/radaccord_1_0_0/](../release_history/radaccord_1_0_0/).

## Historical archives and the prospective validation candidate

The original archives remain immutable when the active implementation evolves.
From the current validation checkout, verify both native archives and their
retained provenance pointers with:

```shell
python -B scripts/verify_native_freeze.py --archives-only
```

This explicit mode checks the pinned archive bytes, every manifested payload,
the archived 15-file calibration and 27-file refinement freezes, and the bound
analysis correction. It reports **zero active scientific files verified**;
archive integrity does not certify the new implementation. The default command
without `--archives-only` is unchanged in purpose: it also requires the active
seven-source scientific union to match historical rc2 and rejects changed
sources. Do not change historical hashes to make an evolved implementation pass.

After the prospective freeze has been created, separately verify its declared
active implementation and protocol files with:

```shell
python -B scripts/verify_prospective_freeze.py
```

The default input is `protocol/prospective_freeze.json`, with schema
`prospective-validation-1`, phase `prospective-native-validation-1`, and a
nonempty `files` map from canonical relative paths to lowercase SHA-256 values.
The map must include the 17 required scientific implementation, package,
preparation/controller and prospective protocol/environment/host files listed
in `verify_prospective_freeze.py`; omitting one is rejected.
An alternative freeze uses `--freeze` with a relative path inside `--root`.
Duplicate JSON keys, case-colliding paths, symlinks, path traversal, invalid
hashes and modified or missing files are rejected. This verifies the declared
file map; it does not establish completeness of a scientific protocol, completed
clinical evaluation or remote CI success. Input-realisation attestations must
retain their link to this general freeze, rather than replacing it.

## Start here

Run from this directory with your core Python environment:

```text
python -B radaccord.py --version
python -B radaccord.py --help
```

`radaccord.py` selects the revised profile and forwards the existing verifier arguments unchanged. It adds no measurement or acceptance logic. The original strict profile remains available as `python -B software/verify.py --help`. See [USAGE.md](../USAGE.md) for the two packaged examples and for reporting your own use. This folder is distributed as an archive; no PyPI installation or published software DOI is claimed.

## Contents and outcomes

- `software/`: unchanged scientific modules, both freeze manifests, protocol, requirements, tests, native-engine adapters and working CLI examples. The original profile and the subsequent restriction remain distinct.
- `work/development_final/`: 12 development phantoms, complete outputs from both engines, all decisions and two explicitly owned output mutations.
- `work/heldout/`: 64 initial reserved phantoms; 4096 cases and 4608 extraction jobs per engine, with all raw feature outputs, warnings, durations, full per-feature diagnostics and decisions.
- `work/refinement/`: 32 new-input follow-up phantoms, including 16 prescribed checkerboard enrichments. All 2048 cases are retained; two qform/sform boundary rejections leave 2302 completed native jobs from 2304 planned. All 256 faults and repeats remain.
- `work/independent_*.json*`: independent arithmetic and coverage audits. Their integrity success flags do not imply every original feature obligation passed.
- `work/shape_*.json` and related scripts: bounded post hoc geometry and lookup-table reconstruction. No third-party C source is redistributed.
- `radaccord.py`: the branded entry point, delegating to the unchanged revised verifier.
- `USAGE.md`: runnable commands, decision interpretation and an adaptable Methods reporting template.
- `MANIFEST.sha256`: the final release file inventory, excluding the manifest itself. `PRIVACY_SCAN.json`, `RELEASE_VALIDATION.json` and `software_branding_audit.json` identify the checks performed for this final distribution. Any subsequent edit invalidates this inventory.
- `release_history/supplementary_software_1/`: byte-identical checks from the source distribution, clearly labelled historical; they do not certify a newly packaged archive.

The initial PyRadiomics profile produced 36 alerts among 3200 equivalent representations. All remain visible. The unchanged MIRP profile produced no equivalent alerts among 3200 cases. Each engine completed all 4608 jobs; each detected 512/512 constructed transport faults using physical correspondence, 384/512 using feature laws and 320/512 using anchors. All 512 repeated mappings were identical. Covariant controls (256 per engine) satisfied assigned laws; changed-bin-width controls (64 per engine) abstained. The revised PyRadiomics follow-up has 0/1598 equivalent alerts, while its original comparisons retain 384 alerts. Two other equivalent attempts were outside domain, not approved. This follow-up concerns new inputs after a known restriction, not unseen mechanisms or clinical sensitivity.

## Recompute every archived decision without image volumes

From this directory, use a Python environment with the core dependencies:

```text
python -m pip install -r software/requirements-core.txt
python -B reproduce_archived.py --output reproduced
```

The command first verifies both frozen manifests, then copies the required raw outputs and case records to a fresh directory and recomputes development, initial reserved and revised follow-up decisions, including the output mutations. It compares all ten generated decision/diagnostic/summary files byte for byte against the archive and writes `reproduced/validation.json`. Existing destinations are refused. Neither native engine nor generated images are needed. This validates archived comparison arithmetic; it does not rerun native extraction or freshly validate physical input correspondence.

The independent held-out comparator can also run from this archive with `python -B work/independent_results_audit.py --engine mirp --reuse-input-audit` or `--engine pyradiomics --reuse-input-audit`. It recomputes scalar decisions and reuses the archived decoded-input audit only after matching case/job hashes. Run this on a working copy because it replaces its audit report with the new invocation. It does not pretend omitted input images were freshly inspected.

## Regenerate images and audit inputs afresh

Run `python -B regenerate_inputs.py` on a working copy of this package. It calls the unchanged frozen generators into temporary directories and moves only their newly generated `inputs/` directories alongside the archived run records. Existing input directories are refused, and the original cases, jobs, timestamps, raw results and decisions are preserved. Expect several gigabytes of local storage. Use the recorded core versions for literal decoded-input comparisons.

Then run:

```text
python -B work/independent_results_audit.py --engine pyradiomics
python -B work/independent_results_audit.py --engine mirp --reuse-input-audit
python -B work/independent_refinement_audit.py
```

These commands freshly decode all inputs and compare their recorded digests and geometry, recompute independent anchors, and recompute relation decisions. Their generated audit reports may contain new run durations; keep the original archive separately. The two retained boundary rejections are documented by `work/refinement_qform_edge_audit.json`; they do not acquire native outputs during regeneration.

To rerun native extraction rather than compare archived measurements, follow `software/REPRODUCIBILITY.md`, from the `software/` directory, using fresh run directories and the separate recorded PyRadiomics and MIRP environments. Timings and new manifests are execution-dependent. Different dependency versions constitute a new compatibility evaluation. Do not replace freeze hashes to force acceptance.

## Tests, examples and figures

From `software/`, run `python -B -m unittest discover -s tests -v` with NumPy, NiBabel and SimpleITK installed. Core tests include independent SimpleITK geometry reading, signed permutations, input rejection and relation controls. `software/examples/README.md` documents the packaged valid reindexing and undeclared-origin-fault examples and their actual native reports.

Figure scripts `work/build_fig1.py`, `work/build_fig2.py`, and `work/build_fig3_4.py` use the shared `work/figure_style.py` and write 600 dpi PNG/TIFF and vector PDF/SVG to `figures/`. Install Matplotlib, Pillow and scikit-image if needed. Locally installed Arial regular and bold are required; the scripts stop if Arial is unavailable. No font files are redistributed in this software archive. The scripts use a development phantom or archived result files and do not need omitted image volumes. Figure styling was revised before publication without changing version 1.0.0, feature outputs, numerical decisions or frozen scientific modules.

The optional mesh investigation additionally needs regenerated held-out inputs and SimpleITK. Obtain the official source from https://raw.githubusercontent.com/AIM-Harvard/pyradiomics/v3.0.1/radiomics/src/cshape.c and save it as `work/pyradiomics_v3_0_1_cshape.c`. The SHA-256 must equal `e8d56aec5b7daa1777d97d91be942952949150c058eb817582ca80d37cd1f14e`; the reconstruction script checks this. Then run `work/inspect_shape_alert_geometry.py` and `work/reproduce_shape_lookup.py`. The archived reconstruction localises the observed variation in one binary configuration and does not establish a universal upstream defect.

## Provenance and limits

AI tools assisted software development, debugging and documentation. Automated checks and archived evidence do not replace author responsibility and scientific review. The package preserves the initial outcomes, scope refinement and negative controls rather than presenting a retrospectively perfect result. The physical correspondence check requires a trustworthy source and transformation record; it cannot establish clinical validity or recover geometry already mislabelled in the source. No release DOI is invented; use `CITATION.cff` and the manifest to identify this version.
