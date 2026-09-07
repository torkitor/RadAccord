"""Read-only held-out audit independent of benchmark.evaluate.

Recomputes decisions with scalar arithmetic, verifies case/job/output coverage,
and checks decoded-input digests. It neither generates nor changes study data.
Run --engine pyradiomics first; --engine mirp --reuse-input-audit can reuse the
completed input audit when the same case/job manifests are still present.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import nibabel as nib
import numpy as np

WORK = Path(__file__).resolve().parent
SOFTWARE = WORK.parent / "software"
sys.path.insert(0, str(SOFTWARE))
from adapters import INTENSITY_LAWS, SPATIAL_DEGREES, PYRADIOMICS_AXIS_SPECIFIC


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def mapping(records, what):
    counts = Counter(row["job_id"] for row in records)
    duplicates = [key for key, count in counts.items() if count > 1]
    if duplicates:
        raise AssertionError(f"Duplicate {what}: {duplicates[:8]}")
    return {row["job_id"]: row for row in records}


def close(x, y):
    return x is not None and y is not None and math.isfinite(x) and math.isfinite(y) and abs(x-y) <= 1e-6 + 1e-5*abs(y)


def independent_digest(image, mask):
    digest = hashlib.sha256()
    for array in (image.get_fdata().astype("<f8"), np.asanyarray(mask.dataobj).astype("<i2"), image.affine.astype("<f8")):
        digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def relation(engine, reference, observed, case, force_identity=False):
    """Independent scalar implementation of the locked conditional obligations."""
    law = INTENSITY_LAWS[engine]
    kind = "identity" if force_identity else case["spec"]["kind"]
    assessed, violated, abstained = 0, [], 0
    worst = {"scaled_error": 0.0, "job_id": case["job_id"], "feature": None}
    for key, value in reference.items():
        if (not force_identity and not case["settings_equal"]) or key in PYRADIOMICS_AXIS_SPECIFIC:
            abstained += 1
            continue
        if kind in ("identity", "reindex", "encoding", "label"):
            expected = value
        elif kind == "scale" and key in SPATIAL_DEGREES[engine]:
            expected = None if value is None else value * case["spec"]["parameters"]["scale"] ** SPATIAL_DEGREES[engine][key]
        elif kind == "intensity" and key in law["affine"]:
            expected = None if value is None else case["spec"]["intensity_gain"]*value + case["spec"]["intensity_offset"]
        elif kind == "intensity" and key == law["variance"]:
            expected = None if value is None else case["spec"]["intensity_gain"] ** 2 * value
        elif kind == "intensity" and key == law["energy"]:
            a, b = case["spec"]["intensity_gain"], case["spec"]["intensity_offset"]
            n, mean = case["anchors"]["n_voxels"], reference.get(law["mean"])
            expected = None if value is None or mean is None else a*a*value + 2*a*b*n*mean + b*b*n
        else:
            abstained += 1
            continue
        assessed += 1
        actual = observed.get(key)
        if not close(actual, expected):
            violated.append(key)
        if actual is not None and expected is not None and math.isfinite(actual) and math.isfinite(expected):
            error = abs(actual-expected)/max(1.0, abs(expected))
            if error > worst["scaled_error"]:
                worst = {"scaled_error": error, "job_id": case["job_id"], "feature": key,
                         "actual": actual, "expected": expected}
    return {"assessed": assessed, "abstained": abstained, "violated_features": violated,
            "violation": bool(violated) or not reference, "worst": worst}


def input_audit(directory, cases, jobs, reuse):
    cache = WORK / "independent_input_audit.json"
    fingerprints = {"cases_sha256": sha(directory/"cases.jsonl"), "jobs_sha256": sha(directory/"jobs.jsonl")}
    if reuse:
        prior = json.loads(cache.read_text(encoding="utf-8"))
        assert prior["manifest_hashes"] == fingerprints and prior["checks_passed"]
        return dict(prior, reused=True)
    checked, byte_total = 0, 0
    source_digests = defaultdict(set)
    errors = []
    sample_anchors = {}
    for case in cases.values():
        if case["activation"] != "applicable" or "boundary_error" in case:
            continue
        source_digests[case["seed"]].add(case["source_digest"])
        for key in ("source_digest", "observed_digest"):
            if len(case[key]) != 64 or any(c not in "0123456789abcdef" for c in case[key]):
                errors.append([case["job_id"], "invalid_digest_field", key])
        job = jobs[case["job_id"]]
        ip, mp = directory/job["image_path"], directory/job["mask_path"]
        assert ip.is_file() and mp.is_file()
        byte_total += ip.stat().st_size + mp.stat().st_size
        image, mask = nib.load(ip), nib.load(mp)
        if independent_digest(image, mask) != case["observed_digest"]:
            errors.append([case["job_id"], "decoded_digest_mismatch"])
        raw_geometry = image.shape == mask.shape and np.allclose(image.affine, mask.affine, rtol=0, atol=1e-4)
        if bool(raw_geometry) != bool(all(case["geometry"].values())):
            errors.append([case["job_id"], "geometry_summary_mismatch"])
        if case["seed"] in (1000, 1021, 1042, 1063) and case["group"] == "reference":
            values = image.get_fdata()[np.asanyarray(mask.dataobj) == job["label"]]
            n = len(values)
            mean = math.fsum(float(x) for x in values)/n
            energy = math.fsum(float(x)*float(x) for x in values)
            variance = math.fsum((float(x)-mean)**2 for x in values)/n
            volume = n*abs(float(np.linalg.det(image.affine[:3,:3])))
            sample_anchors[str(case["seed"])] = {"n_voxels": n, "mean": mean, "energy": energy,
                                                  "variance": variance, "voxel_volume": volume,
                                                  "minimum": float(min(values)), "maximum": float(max(values))}
            for anchor, actual in sample_anchors[str(case["seed"])].items():
                if not close(actual, case["anchors"][anchor]):
                    errors.append([case["job_id"], "independent_anchor_mismatch", anchor])
        checked += 1
        if checked % 512 == 0:
            print(json.dumps({"decoded_inputs_checked": checked}), flush=True)
    assert all(len(value) == 1 for value in source_digests.values())
    assert len({next(iter(value)) for value in source_digests.values()}) == 64
    out = {"checks_passed": not errors, "manifest_hashes": fingerprints, "cases_decoded": checked,
           "image_mask_files_checked": 2*checked, "bytes_read_inputs": byte_total,
           "source_digest_consistent_per_seed": True, "distinct_source_digests": 64,
           "independent_anchor_samples": sample_anchors, "errors": errors,
           "digest_scope": "Decoded data, integer mask, affine and array shapes; not a hash of original encoded file bytes.",
           "source_digest_scope": "Pre-serialization source digests checked for completeness and per-seed consistency, not equated to quantised NIfTI affines.",
           "reused": False}
    save(cache, out)
    assert out["checks_passed"], errors[:8]
    return out


def audit(engine, reuse=False):
    started = time.perf_counter()
    directory = WORK/"heldout"
    final = directory/f"{engine}.jsonl"
    if not final.is_file():
        raise FileNotFoundError(f"The completed {engine} output is not available; partial shards are not audited as complete")
    case_rows, job_rows, native_rows = rows(directory/"cases.jsonl"), rows(directory/"jobs.jsonl"), rows(final)
    cases, jobs, native = mapping(case_rows, "cases"), mapping(job_rows, "jobs"), mapping(native_rows, "outputs")
    frozen = json.loads((SOFTWARE/"protocol"/"final_freeze.json").read_text(encoding="utf-8"))
    for filename, expected in frozen["sha256"].items():
        assert sha(SOFTWARE/filename) == expected, ("Frozen file changed", filename)
    manifest = json.loads((directory/"input_manifest.json").read_text(encoding="utf-8"))
    assert sha(directory/"cases.jsonl") == manifest["cases_sha256"]
    assert len(cases) == manifest["cases"] == 4096
    assert len(jobs) == len(native) == manifest["jobs_per_engine"] == 4608
    assert set(jobs) == set(native)
    for key, row in native.items():
        assert row["engine"] == engine
        assert row["settings"] == {field: jobs[key][field] for field in ("label", "bin_width", "spatial_mode")}
        if row["status"] == "extracted":
            assert row["feature_count"] == len(row["features"])
            assert set(row["nonfinite_features"]) == {name for name, value in row["features"].items()
                                                        if value is None or not math.isfinite(value)}
    assert sorted({row["seed"] for row in cases.values()}) == list(range(1000, 1064))
    assert Counter(row["seed"] for row in cases.values()) == Counter({seed: 64 for seed in range(1000, 1064)})
    groups = Counter(row["group"] for row in cases.values())
    assert groups == Counter(reference=64, equivalent=3200, covariant=256, not_applicable=64, fault=512)
    assert all(row["activation"] == "applicable" and "boundary_error" not in row for row in cases.values())
    repeat_ids = {key for key in jobs if key.endswith("_repeat")}
    assert repeat_ids == {row["job_id"]+"_repeat" for row in cases.values() if row["group"] == "fault"}
    for key in repeat_ids:
        a, b = dict(jobs[key]), dict(jobs[key[:-7]])
        a.pop("job_id"); b.pop("job_id")
        assert a == b
    inputs = input_audit(directory, cases, jobs, reuse)
    schema = set(json.loads((SOFTWARE/"protocol"/"feature_schema.json").read_text(encoding="utf-8"))[engine])
    by_group, by_fault, decisions = defaultdict(Counter), defaultdict(Counter), []
    alerts, alert_seed_counts, alert_feature_counts = [], Counter(), Counter()
    worst = {}
    source_domains = {row["seed"]: row["anchors"] for row in cases.values() if row["group"] == "reference"}
    assert all(d["mean"] != 0 and d["variance"] > 0 and d["n_voxels"] > 1 and d["full_rank_roi"] for d in source_domains.values())
    anchor_map = ({"mean": "original_firstorder_Mean", "minimum": "original_firstorder_Minimum",
                   "maximum": "original_firstorder_Maximum", "variance": "original_firstorder_Variance",
                   "energy": "original_firstorder_Energy", "voxel_volume": "original_shape_VoxelVolume"}
                  if engine == "pyradiomics" else
                  {"mean": "stat_mean", "minimum": "stat_min", "maximum": "stat_max", "variance": "stat_var",
                   "energy": "stat_energy", "voxel_volume": "morph_vol_approx"})
    for case in cases.values():
        row, ref = native[case["job_id"]], native[f"{case['seed']}_reference"]
        values, reference = row.get("features", {}), ref.get("features", {})
        required = {key.replace("_fbs_w25.0", "_fbs_w50.0") for key in schema} if engine == "mirp" and not case["settings_equal"] else schema
        native_bad = row["status"] != "extracted" or bool(row.get("nonfinite_features"))
        actual_nonfinite = [key for key, value in values.items() if value is None or not math.isfinite(value)]
        schema_bad = set(values) != required or bool(actual_nonfinite)
        assert ref["status"] == "extracted" and set(reference) == schema and not ref.get("nonfinite_features")
        conditional = relation(engine, reference, values, case)
        naive_values = {key.replace("_fbs_w50.0", "_fbs_w25.0"): value for key, value in values.items()}
        naive = relation(engine, reference, naive_values, case, force_identity=True)
        anchor_bad = [key for anchor, key in anchor_map.items() if not close(values.get(key), case["anchors"][anchor])]
        w_bad = case["witness"]["status"] == "violated"
        geometry_bad = not all(case["geometry"].values())
        repeat_bad, repeat_identity = None, None
        if case["group"] == "fault":
            other = native[case["job_id"]+"_repeat"]
            repeat_bad = relation(engine, values, other.get("features", {}), case, force_identity=True)["violation"]
            repeat_identity = values == other.get("features", {}) and row["status"] == other["status"]
        full = native_bad or schema_bad or w_bad or geometry_bad or conditional["violation"] or bool(anchor_bad)
        decision = {"job_id": case["job_id"], "group": case["group"], "name": case["name"],
                    "native_failure": native_bad, "schema_failure": schema_bad, "geometry_violation": geometry_bad,
                    "witness_violation": w_bad, "conditional_violation": conditional["violation"],
                    "conditional_assessed": conditional["assessed"], "conditional_abstained": conditional["abstained"],
                    "anchor_violation": bool(anchor_bad), "naive_invariance_violation": naive["violation"],
                    "repeat_violation": repeat_bad, "repeat_numeric_identity": repeat_identity, "full_violation": full}
        decisions.append(decision)
        if case["group"] != "fault" and full:
            alerts.append({"job_id": case["job_id"], "seed": case["seed"], "group": case["group"],
                           "violated_features": conditional["violated_features"], "worst": conditional["worst"],
                           "witness_violation": w_bad, "anchor_violation": bool(anchor_bad)})
            alert_seed_counts[str(case["seed"])] += 1
            alert_feature_counts.update(conditional["violated_features"])
        for counter in (by_group[case["group"]], by_fault[case["name"]] if case["group"] == "fault" else None):
            if counter is None: continue
            counter["cases"] += 1
            for key, value in decision.items():
                if isinstance(value, bool): counter[key] += int(value)
            counter["conditional_assessed_features"] += conditional["assessed"]
            counter["conditional_abstained_features"] += conditional["abstained"]
        group = case["group"]
        if conditional["worst"]["scaled_error"] > worst.get(group, {}).get("scaled_error", -1):
            worst[group] = conditional["worst"]
    # Direct arithmetic check of sampled extracted anchors, independent of NumPy reductions.
    math_checks = []
    for seed, anchor_values in inputs["independent_anchor_samples"].items():
        reference = native[f"{seed}_reference"]["features"]
        for anchor, feature in anchor_map.items():
            math_checks.append({"seed": int(seed), "anchor": anchor,
                                "satisfied": close(reference.get(feature), anchor_values[anchor])})
    assert all(check["satisfied"] for check in math_checks)
    summary = {"engine": engine, "checks_passed": True, "cases": len(cases), "native_jobs": len(native),
               "duplicate_or_missing_case_job_output_ids": False, "frozen_hashes_unchanged": True,
               "case_manifest_hash_matches": True, "input_audit_reused": reuse,
               "activation_not_applicable": 0, "boundary_errors": 0,
               "groups": dict(by_group), "fault_families": dict(by_fault),
               "correctly_transported_case_alerts": alerts,
               "correctly_transported_alerts_by_seed": dict(alert_seed_counts),
               "correctly_transported_alerts_by_feature": dict(alert_feature_counts),
               "worst_conditional_scaled_errors": worst, "direct_native_anchor_checks": math_checks,
               "native_statuses": dict(Counter(row["status"] for row in native.values())),
               "all_output_feature_counts": dict(Counter(str(row.get("feature_count")) for row in native.values())),
               "native_output_sha256": sha(final), "seconds": time.perf_counter()-started,
               "notes": ["The source-aware witness and geometry counts are read from the frozen case log; decoded file digests and geometry are independently rechecked.",
                         "checks_passed describes audit completeness and integrity; it does not mean all native feature obligations were satisfied.",
                         "Conditional decisions are independently computed with abs error <= 1e-6 + 1e-5*abs(expected). No thresholds are altered.",
                         "The four sampled source anchor sets are independently recomputed using math.fsum and decoded physical affine.",
                         "Counts are synthetic software cases nested within 64 phantoms and eight fault mechanisms, not clinical sensitivity or independent patients."]}
    save(WORK/f"independent_results_audit_{engine}.json", summary)
    (WORK/f"independent_decisions_{engine}.jsonl").write_text("".join(json.dumps(row, allow_nan=False)+"\n" for row in decisions), encoding="utf-8")
    report = [f"# Independent held-out results audit: {engine}", "",
              "All case IDs, jobs and completed outputs were retained: 4096 cases and 4608 extraction jobs. "
              "There were no duplicate/missing IDs, no inactive fault cases and no boundary failures. "
              "The frozen software hashes and case-manifest hash match. All 8192 input files were decoded for the input audit; "
              "the observed digests and raw geometry match the case log. "
              + ("This run reused that verified input audit against unchanged case/job manifest hashes." if reuse else "The input audit was run in this invocation."), "",
              "The four independently recomputed source anchor sets use `math.fsum` for mean, energy and population variance, "
              "plus physical voxel volume from the decoded affine. All 24 comparisons to the sampled native outputs satisfy the frozen tolerances.", "",
              "## Injected faults", "",
              "Counts below are detections among 64 cases per mechanism. Repetition compares the same corrupted input with itself.", "",
              "| Mechanism | Native/schema | Pair geometry | Repeat | Feature relation | Anchors | Witness | Combined |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, counter in by_fault.items():
        report.append(f"| {name} | {counter['native_failure']}/{counter['schema_failure']} | {counter['geometry_violation']} | "
                      f"{counter['repeat_violation']} | {counter['conditional_violation']} | {counter['anchor_violation']} | "
                      f"{counter['witness_violation']} | {counter['full_violation']} |")
    report += ["", "## Correctly transported and context controls", "",
               "| Group | Cases | Witness alerts | Conditional feature alerts | Anchor alerts | Combined alerts | Unconditional invariance alerts |",
               "|---|---:|---:|---:|---:|---:|---:|"]
    for name in ("reference", "equivalent", "covariant", "not_applicable"):
        counter = by_group[name]
        report.append(f"| {name} | {counter['cases']} | {counter['witness_violation']} | {counter['conditional_violation']} | "
                      f"{counter['anchor_violation']} | {counter['full_violation']} | {counter['naive_invariance_violation']} |")
    report += ["", f"Correctly transported cases with combined alerts: **{len(alerts)}**. "
               "These are preserved as observed output-level alerts; they must not be relabelled as injected input corruption. "
               "No tolerance, feature inclusion or case selection was changed after observing these outcomes.", "",
               "Alert counts by phantom: " + json.dumps(dict(alert_seed_counts)) + ".", "",
               "Alert counts by feature: " + json.dumps(dict(alert_feature_counts)) + ".", "",
               "Detailed per-case decisions, worst numerical discrepancies and raw-output hashes are retained in the companion JSON/JSONL audit files.", "",
               "These are synthetic software cases nested within 64 phantoms and eight mechanisms. They are not clinical sensitivity, fault prevalence, "
               "or thousands of independent patient observations. The source-aware witness's counts are derived from the frozen case log; "
               "this audit additionally rechecks all decoded-input digests/geometry and independently computes scalar decisions."]
    (WORK/f"independent_results_audit_{engine}.md").write_text("\n".join(report)+"\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("engine", "checks_passed", "cases", "native_jobs", "groups", "fault_families", "worst_conditional_scaled_errors", "seconds")}, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["pyradiomics", "mirp"], required=True)
    parser.add_argument("--reuse-input-audit", action="store_true")
    args = parser.parse_args()
    audit(args.engine, args.reuse_input_audit)
