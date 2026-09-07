# Reproduce RadAccord at the level you need

The repository supports three distinct checks. Choose one before interpreting a reproduction result.

| Level | Fresh work | Evidence it provides |
|---|---|---|
| 1. Archived decisions | Recalculate comparisons from stored native outputs and case records | Whether the released comparison arithmetic reproduces the archived decisions |
| 2. Fresh input audit | Regenerate synthetic files, decode them and check geometry, intensities, ROI and independent anchors | Whether newly generated inputs match the archived input specification and recorded measurements |
| 3. Native extraction | Generate fresh run directories and execute the pinned engines | A new execution of the synthetic experiment, including native measurements |

An integrity check and a satisfied scientific obligation are different results. Original alerts and unavailable cases must remain visible. See [scientific scope](SCIENCE.md), [usage](../USAGE.md), the [repository overview](../README.md) and the detailed [environment/protocol guide](../software/REPRODUCIBILITY.md).

## Start from the repository root

The root is the directory containing `radaccord.py`, `software/` and `work/`. Keep an untouched copy of the archive; use another copy for fresh audits because they write new reports.

Use an isolated core environment with the recorded Python 3.13.5, NumPy 2.2.6 and NiBabel 5.3.3 where available:

```text
python -m pip install -r software/requirements-core.txt
python -B radaccord.py --version
```

The browsable repository keeps summary JSON and scripts alongside the byte-identical [RadAccord 1.0.0 archive](../data/RadAccord-1.0.0.zip). Restore its large JSONL records locally before archived comparison, fresh-input auditing or figure regeneration:

```text
python -B scripts/restore_records.py
```

Restoration checks the release-archive hash and refuses conflicting existing records. It restores the original JSONL paths, without creating omitted image volumes or changing scientific results. The two small CLI examples do not require this step.

The two native engines have separate environments: PyRadiomics 3.0.1 used Python 3.10.11, NumPy 1.23.5 and SimpleITK 2.2.1; MIRP 2.5.0 used Python 3.13.5, NumPy 2.2.6 and SimpleITK 2.5.3. The engine requirements and archived environment records give the remaining measured versions. The principal-package pins are not complete platform-independent dependency locks.

## Level 1: archived comparisons

From the repository root, with the core environment active:

```text
python -B reproduce_archived.py --output reproduced
```

The destination must not exist. This verifies both scientific freeze manifests, copies the required archived records and recalculates development, initial and follow-up decisions, including the development output mutations. It compares ten generated files byte for byte and writes `reproduced/validation.json`. No large NIfTI volumes or native engines are required. It does not freshly inspect omitted images.

For the separate scalar audit, the following commands explicitly reuse the stored decoded-input audit after case/job-hash checks:

```text
python -B work/independent_results_audit.py --engine pyradiomics --reuse-input-audit
python -B work/independent_results_audit.py --engine mirp --reuse-input-audit
```

Run these on a working copy: they replace their audit reports. This is reuse of recorded input evidence, not a new input inspection.

## Level 2: fresh synthetic inputs

From the repository root of a working copy:

```text
python -B regenerate_inputs.py
python -B work/independent_results_audit.py --engine pyradiomics
python -B work/independent_results_audit.py --engine mirp --reuse-input-audit
python -B work/independent_refinement_audit.py
```

Regeneration refuses existing `inputs/` directories and preserves archived case records, jobs, raw measurements and decisions. Allow several gigabytes of storage. The first initial audit freshly decodes the generated input files; the MIRP audit then reuses that newly completed input audit for the same cases. The follow-up audit separately inspects its regenerated files. These checks still compare stored native measurements; they do not rerun either engine. The two qform/sform exclusions remain unavailable.

The scripts locate their modules relative to their own files; no custom `PYTHONPATH` is required. Invoke them as shown rather than pasting their internal imports into another working directory.

## Level 3: repeat native extraction

Use the separate engine environments and detailed installation instructions in [software/REPRODUCIBILITY.md](../software/REPRODUCIBILITY.md). For its bare `benchmark.py` and `validation_refinement.py` commands, **change from the repository root into `software/` first**:

```text
cd software
```

With the core interpreter active, begin with the 12-phantom development run:

```text
python -B benchmark.py prepare runs/development --first 0 --count 12
python -B benchmark.py run runs/development --engine pyradiomics --python "PYRADIOMICS_PYTHON" --workers 12
python -B benchmark.py run runs/development --engine mirp --python "MIRP_PYTHON" --workers 12
python -B benchmark.py evaluate runs/development
```

Replace the quoted engine placeholders with the absolute paths to those environments' Python executables. Keep runs in fresh directories. For the published initial phase, prepare with `--first 1000 --count 64 --heldout`; run both engines and evaluate using the same pattern. For the follow-up:

```text
python -B validation_refinement.py prepare runs/refinement
python -B benchmark.py run runs/refinement --engine pyradiomics --python "PYRADIOMICS_PYTHON" --workers 12
python -B validation_refinement.py evaluate runs/refinement --engine pyradiomics
```

Follow-up seeds 2000–2031 are fixed by the protocol. The original 16-file freeze and later freeze covering those files plus three additions remain separate. Never replace their hashes to force a changed implementation through the guards. Different settings, versions or inputs constitute a new compatibility evaluation.

From `software/`, the unit tests run with `python -B -m unittest discover -s tests -v`; the physical tests additionally require SimpleITK. Engine execution timings, new timestamps and worker logs are run-specific.

## Record and share the result

Report the software version, profile, freeze identifier, actual environments, component decisions and separate denominators for phantoms, transformations, faults and native calls. Preserve unavailable inputs, unassigned laws and the four withheld PyRadiomics reindexing obligations. Use the [Methods template](../USAGE.md#methods-reporting-template) only for procedures actually performed.

Share synthetic minimal examples and reviewed reports. Keep patient-derived inputs, raw worker logs, private paths and local environment directories out of public issues and archives. The source is distributed under [Apache License 2.0](../LICENSE); external libraries retain their own licences.
