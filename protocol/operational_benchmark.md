# Controlled operational benchmark protocol

Status: implemented harness; no new clinical challenge has been executed by preparing this protocol. The input set, configurations, number of repeats, environments and source hashes must be fixed in a separate plan/freeze before execution. This is an author-run controlled benchmark, not independent-user validation or a survey of spontaneous real errors.

## Separate coverage and timing modes

Each plan declares `mode: coverage` or `mode: timing`, and each mode has its own freeze and output directory. Coverage requires `repeats: 1` and `warmup_pairs_per_worker: 0`: one baseline/audited pair per input/configuration, preserving native outputs and recording applicable, violated, indeterminate and unavailable relationships. Coverage records worker wall time only for execution accounting; it deliberately emits no per-arm durations, absolute overhead or log-ratio estimates. Its summary cannot be combined with timing records by the summarizer.

Timing requires an even number of repeats, at least two, and `warmup_pairs_per_worker: 1`. The intended larger design can therefore use 24 inputs × 3 configurations × 2 engines = 144 coverage pairs, and a separately identified 8-input subset × 2 configurations × 2 engines × 4 repeats = 128 measured timing pairs, plus 128 within-process warmup pairs. These are proposed plan counts, not completed observations. Reusing an input across those components does not create an independent image or validation set. Controlled correction tasks occur only in coverage; their two-engine observations must not be pooled as independent incidents.

## Native paired experiment

For each declared input/configuration and extractor, run an even number of measured pairs, at least two. The plan chooses the number before evaluation. AB denotes native extraction followed by audited native extraction; BA reverses that order. A deterministic input/workflow hash chooses the starting order, with exactly equal AB and BA counts within each input/workflow. Each pair has its own subprocess and timeout. The controller retains all slots, including timeout, process exit, failed warmup and unsuccessful extraction, without replacing them with easier cases.

Each subprocess sets native/BLAS thread counts to one, verifies source-file hashes and loads one source image/mask pair. Native in-memory inputs are prepared once. Before measurement, it warms each arm once in the reverse of the measured order; warmup durations are recorded separately and excluded from measured durations. Fresh input copies precede each timed call. Both measured calls include native extractor construction and execution; the audited call additionally includes its checking and report construction. Disk loading, output serialization, HTML rendering and input copies are outside those measured durations. Worker wall time, including startup, input loading, warmup and any constructed tasks, is recorded separately. This controls cache order within the experiment without asserting that operating-system cache or unrelated host load is fixed.

The native baseline uses exactly the frozen configuration used by its audited counterpart. No settings are silently changed to achieve completion. PyRadiomics compares all returned non-diagnostic keys and values with exact array equality; MIRP compares complete native DataFrames exactly. Both the completed warmup pair and the measured pair retain separate exact-output comparisons and value digests. A warmup value discrepancy is retained and does not silently cancel or replace the measured attempt. Matching nonfinite values mean preservation, not validity. Original-image exports are requested in both MIRP arms so that the baseline includes the same native export workload. Feature extraction and checking remain confined to the native adapter's explicitly observed boundaries.

Report baseline time, audited time, their paired absolute difference and log(audited / baseline). Summarize repeats by input/workflow with median and first/third quartiles and both order counts. Do not treat repetitions as independent images or patients, calculate a ratio of unmatched aggregate medians, or turn these descriptive times into an uncontrolled cross-extractor ranking. External-user report review time requires real independent users and is not simulated here.

Peak memory uses Windows GetProcessMemoryInfo/PeakWorkingSetSize or Unix resource.getrusage(RUSAGE_SELF).ru_maxrss with platform-correct units. This is a process-lifetime high-water mark, including warmup and both arms. Report it as a pair memory requirement; it is not audited-minus-native peak overhead and cannot be reset or attributed to the second arm. Separate per-arm processes would be required for a defensible differential peak-memory experiment.

## Constructed error and correction tasks

Once per input per engine in coverage mode, a separate experiment declares an identity relationship on decoded float64 intensities and the binary selected label-1 mask before candidate creation. A correct copied control, a shared 7-mm origin shift and a 2-unit decoded intensity offset are evaluated. These faults are introduced by this harness, not found in native packages. Correction restores the retained identity source. The same candidate, trusted source and declaration are supplied to paired image–mask geometry, source-aware geometry and RadAccord's numerical operation check. Activity, all checker states and corrected-state decisions remain in the output. Inactive or unavailable tasks must not be counted as detected errors.

This tests whether an observed discrepancy and a known restoration produce the expected computational decision. It does not measure spontaneous error prevalence, human adjudication, repair of a clinical system, feature or patient benefit. The historical MIRP oblique-export regression remains a separately labelled retrospective reproduction of a known incident. Timing repeats, the two engine observations of one constructed task and the same source's control/fault/correction states are correlated, not independent incidents.

## Public plan and private inputs

The JSON plan uses schema_version `operational-benchmark-1`, explicit `mode`, mode-appropriate `repeats` and `warmup_pairs_per_worker`, `native_threads: 1`, `timeout_seconds_per_pair`, `inputs` and `workflows`. Input entries contain only a public id, modality (`mr`, `ct` or `generic`) and either `kind: synthetic` with an integer seed, or `kind: image` with image/mask SHA-256 values. Numeric label 1 is selected consistently. Workflow entries have a public id, applicable modalities and a `configs` mapping containing explicit `pyradiomics` and/or `mirp` native parameter dictionaries. A workflow can be limited to one modality or extractor; no cross-modality defaults are inferred.

A private JSON manifest maps public input ids to `image` and `mask` filenames. It stays outside the public repository and is bound by hash in the freeze. The freeze contains the schema version, plan SHA-256, optional private-manifest SHA-256, and required scientific/harness files with hashes. Freeze native package/environment versions as an additional public field before starting the experiment. The driver verifies the plan and sources for every pair. It never bypasses a missing freeze for clinical inputs.

Minimal **synthetic demonstration plan**, not the proposed clinical evaluation configuration:

```json
{
  "schema_version": "operational-benchmark-1",
  "mode": "coverage",
  "repeats": 1,
  "warmup_pairs_per_worker": 0,
  "native_threads": 1,
  "timeout_seconds_per_pair": 300,
  "inputs": [{"id": "synthetic_demo", "kind": "synthetic", "seed": 987654, "modality": "mr"}],
  "workflows": [{
    "id": "identity_mr", "modalities": ["mr"],
    "configs": {
      "pyradiomics": {
        "setting": {"binCount": 16}, "imageType": {"Original": {}},
        "featureClass": {"firstorder": ["Mean"]}
      },
      "mirp": {"base_feature_families": ["statistics"]}
    }
  }]
}
```

The timing counterpart changes `mode` to `timing`, `repeats` to `4` and `warmup_pairs_per_worker` to `1`; all configurations and input hashes remain explicitly specified. A clinical input entry instead has this shape, with actual frozen SHA-256 values:

```json
{"id": "study_mr_001", "kind": "image", "modality": "mr", "image_sha256": "ACTUAL_IMAGE_SHA256", "mask_sha256": "ACTUAL_MASK_SHA256"}
```

Create `protocol/operational_environments.json` as a mapping keyed by engine. Each value contains the exact `python` version and a `packages` mapping for the engine, NumPy, SimpleITK and all additional packages used in that environment (including NiBabel; SciPy and pandas for MIRP). Record versions from each engine's own interpreter; do not infer them from another environment. `create_freeze` requires these pins and captures only existing repository files. It refuses to overwrite a freeze.

From the repository root, after the plans, configurations and implementation are final, create the two new internal freezes with the appropriate private manifest for each plan:

```python
import json
from pathlib import Path
from scripts.run_operational_benchmark import create_freeze

environments = json.loads(Path("protocol/operational_environments.json").read_text())
create_freeze(
    "protocol/operational_coverage_plan.json", environments,
    "protocol/operational_coverage_freeze.json",
    private_inputs="PRIVATE_COVERAGE_MANIFEST",
    extra_files=("protocol/operational_environments.json",),
)
create_freeze(
    "protocol/operational_timing_plan.json", environments,
    "protocol/operational_timing_freeze.json",
    private_inputs="PRIVATE_TIMING_MANIFEST",
    extra_files=("protocol/operational_environments.json",),
)
```

For synthetic-only plans omit `private_inputs`. Source images prepared before extraction, such as a declared ROI-support crop, must have their own retained preparation provenance and hashes; this harness does not infer a crop or claim full-volume equivalence. Include its preparation protocol/scripts as additional freeze files when used.

Run each engine with its documented native Python environment:

```sh
python scripts/run_operational_benchmark.py --engine pyradiomics --plan protocol/operational_coverage_plan.json --freeze protocol/operational_coverage_freeze.json --private-inputs PRIVATE_COVERAGE_MANIFEST --output results/operational_coverage/pyradiomics --private-log-dir PRIVATE_COVERAGE_PYRADIOMICS_LOGS
python scripts/run_operational_benchmark.py --engine mirp --plan protocol/operational_coverage_plan.json --freeze protocol/operational_coverage_freeze.json --private-inputs PRIVATE_COVERAGE_MANIFEST --output results/operational_coverage/mirp --private-log-dir PRIVATE_COVERAGE_MIRP_LOGS
python scripts/run_operational_benchmark.py --engine pyradiomics --plan protocol/operational_timing_plan.json --freeze protocol/operational_timing_freeze.json --private-inputs PRIVATE_TIMING_MANIFEST --output results/operational_timing/pyradiomics --private-log-dir PRIVATE_TIMING_PYRADIOMICS_LOGS
python scripts/run_operational_benchmark.py --engine mirp --plan protocol/operational_timing_plan.json --freeze protocol/operational_timing_freeze.json --private-inputs PRIVATE_TIMING_MANIFEST --output results/operational_timing/mirp --private-log-dir PRIVATE_TIMING_MIRP_LOGS
```

Use new output and private-log directories. Native stdout/stderr is redirected into the private logs. Public stdout is JSON progress/error codes without input paths or exception text. Results contain hashes and derived evidence, not clinical arrays, native metadata tables or raw traces. Private manifests and logs require an independent privacy check before any sharing.
