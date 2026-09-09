"""Prespecified native PyRadiomics subset; prepare/extract privately, publish only numeric fields.

No imaging or native-engine package is imported by this script. Extraction is
delegated to the unchanged, hash-pinned adapters.py in a supplied Python runtime.
"""
from collections import Counter
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

FAMILIES = {
    "shape": "Elongation Flatness LeastAxisLength MajorAxisLength Maximum2DDiameterColumn Maximum2DDiameterRow Maximum2DDiameterSlice Maximum3DDiameter MeshVolume MinorAxisLength Sphericity SurfaceArea SurfaceVolumeRatio VoxelVolume",
    "firstorder": "10Percentile 90Percentile Energy Entropy InterquartileRange Kurtosis Maximum MeanAbsoluteDeviation Mean Median Minimum Range RobustMeanAbsoluteDeviation RootMeanSquared Skewness TotalEnergy Uniformity Variance",
    "glcm": "Autocorrelation ClusterProminence ClusterShade ClusterTendency Contrast Correlation DifferenceAverage DifferenceEntropy DifferenceVariance Id Idm Idmn Idn Imc1 Imc2 InverseVariance JointAverage JointEnergy JointEntropy MCC MaximumProbability SumAverage SumEntropy SumSquares",
    "glrlm": "GrayLevelNonUniformity GrayLevelNonUniformityNormalized GrayLevelVariance HighGrayLevelRunEmphasis LongRunEmphasis LongRunHighGrayLevelEmphasis LongRunLowGrayLevelEmphasis LowGrayLevelRunEmphasis RunEntropy RunLengthNonUniformity RunLengthNonUniformityNormalized RunPercentage RunVariance ShortRunEmphasis ShortRunHighGrayLevelEmphasis ShortRunLowGrayLevelEmphasis",
}
FEATURES = tuple(sorted(f"original_{family}_{name}" for family, names in FAMILIES.items() for name in names.split()))
LANDMARKS = ("original_shape_VoxelVolume", "original_firstorder_Mean", "original_firstorder_Variance")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n")


def emit(handle, value):
    handle.write(json.dumps(value, allow_nan=False, sort_keys=True) + "\n")


def read_lines(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def planned(plan):
    return [{"job_id": f"native_{number:02d}", "dataset": dataset, "volume_id": volume, "role": role}
            for number, (dataset, volume, role) in enumerate(
                (dataset, volume, role) for dataset, group in sorted(plan["datasets"].items())
                for volume in group["volume_ids"] for role in plan["roles"])]


def checked_path(root, relative):
    part = PurePosixPath(relative)
    if part.is_absolute() or ".." in part.parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe manifest path")
    path = root.joinpath(*part.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Manifest path escapes input root")
    return path


def prepare(args, plan):
    args.private_output.mkdir(parents=True, exist_ok=False)
    rows = read_lines(args.manifest)
    expected = planned(plan)
    allowed = {(r["dataset"], r["volume_id"], r["role"]) for r in expected}
    lookup = {}
    for row in rows:
        key = (row["dataset"], row["volume_id"], row["role"])
        if key not in allowed or key in lookup:
            raise ValueError("Unexpected or duplicate native input assignment")
        lookup[key] = row
    ledger = []
    with (args.private_output / "jobs.jsonl").open("x", encoding="utf-8", newline="\n") as jobs:
        for item in expected:
            row = lookup.get((item["dataset"], item["volume_id"], item["role"]))
            entry = {**item, "input_status": "not_available", "input_sha256": {}}
            if row is None:
                entry["reason"] = "planned_input_not_materialized"
            else:
                files = {f["role"]: f for f in row["files"]}
                if len(row["files"]) != 2 or set(files) != {"image", "mask"}:
                    raise ValueError("Native assignment must contain one image and one mask")
                paths = {kind: checked_path(args.manifest.parent, f["path"]) for kind, f in files.items()}
                if not all(p.is_file() for p in paths.values()):
                    entry["reason"] = "input_file_missing"
                else:
                    observed = {kind: sha(path) for kind, path in paths.items()}
                    if any(observed[k] != files[k]["sha256"] for k in paths):
                        entry["reason"] = "input_hash_mismatch"
                    else:
                        entry.update(input_status="ready", input_sha256=observed)
                        emit(jobs, {"job_id": item["job_id"], **plan["settings"],
                                    **{kind + "_path": str(path) for kind, path in paths.items()}})
            ledger.append(entry)
    save(args.private_output / "state.json", {"plan_sha256": sha(args.plan),
         "jobs_sha256": sha(args.private_output / "jobs.jsonl"),
         "input_manifest_sha256": sha(args.manifest), "assignments": ledger})


def extract(args, plan):
    state = json.loads((args.private_output / "state.json").read_text(encoding="utf-8"))
    if state["plan_sha256"] != sha(args.plan) or sha(args.adapter) != plan["adapter_sha256"]:
        raise ValueError("Frozen plan or adapter hash differs")
    if state["jobs_sha256"] != sha(args.private_output / "jobs.jsonl"):
        raise ValueError("Private native jobs changed after preparation")
    lookup = {r["job_id"]: r for r in state["assignments"]}
    for job in read_lines(args.private_output / "jobs.jsonl"):
        for kind in ("image", "mask"):
            if sha(Path(job[kind + "_path"])) != lookup[job["job_id"]]["input_sha256"][kind]:
                raise ValueError("Native input changed after preparation")
    output = args.private_output / "native_raw.jsonl"
    if output.exists() or (args.private_output / "execution.json").exists():
        raise FileExistsError("Existing native run is never overwritten")
    # Fixed one-process/one-native-thread policy bounds memory for clinical crops.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    environment = subprocess.run([str(args.python), "-B", str(args.adapter), "--environment"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, check=True)
    native_environment = json.loads(environment.stdout)
    if native_environment["packages"]["pyradiomics"] != plan["expected_engine_version"]:
        raise ValueError("Native PyRadiomics version differs from prespecified version")
    save(args.private_output / "environment.json", native_environment)
    execution = {"native_threads": 1, "processes": 1, "timeout_seconds": args.timeout_seconds}
    with (args.private_output / "native_process.log").open("x", encoding="utf-8") as log:
        try:
            result = subprocess.run([str(args.python), "-B", str(args.adapter), "--engine", "pyradiomics",
                "--jobs", str(args.private_output / "jobs.jsonl"), "--output", str(output), "--threads", "1"],
                stdout=log, stderr=log, env=env, timeout=args.timeout_seconds, check=False)
            execution.update(status="completed" if result.returncode == 0 else "process_failed",
                             returncode=result.returncode)
        except subprocess.TimeoutExpired:
            execution.update(status="timed_out", returncode=None)
    save(args.private_output / "execution.json", execution)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def scalar(candidate, reference, atol, rtol):
    if not finite(candidate) or not finite(reference):
        return {"status": "not_comparable", "candidate": candidate if finite(candidate) else None,
                "reference": reference if finite(reference) else None}
    delta = candidate - reference
    absolute = abs(delta)
    limit = atol + rtol * abs(reference)
    relative = absolute / abs(reference) if reference != 0 else None
    # A finite pair can still overflow a derived arithmetic quantity; preserve its status.
    if not finite(delta) or not finite(absolute) or not finite(limit) or (relative is not None and not finite(relative)):
        return {"status": "derived_arithmetic_unavailable", "candidate": candidate, "reference": reference}
    return {"status": "comparable", "candidate": candidate, "reference": reference,
            "signed_difference": delta, "absolute_difference": absolute, "relative_absolute_difference": relative,
            "reference_zero": reference == 0, "tolerance": limit, "beyond_tolerance": absolute > limit}


def cleaned(item, native):
    result = {key: item[key] for key in ("job_id", "dataset", "volume_id", "role", "input_status", "input_sha256")}
    result.update(status="not_available", features={}, warning_count=0)
    if item["input_status"] != "ready":
        allowed = {"planned_input_not_materialized", "input_file_missing", "input_hash_mismatch"}
        result["reason"] = item.get("reason") if item.get("reason") in allowed else "input_not_available"
        return result
    if native is None:
        result["reason"] = "native_record_missing"
        return result
    result["warning_count"] = len(native.get("warnings", []))
    result["seconds"] = native.get("seconds") if finite(native.get("seconds")) else None
    if native.get("status") != "extracted":
        result["reason"] = "native_extraction_failed"
        return result
    values = native.get("features")
    if not isinstance(values, dict) or not values or set(values) - set(FEATURES):
        result["reason"] = "native_feature_schema_mismatch"
        return result
    result.update(status="extracted", features={name: values[name] if finite(values[name]) else None
                                                 for name in FEATURES if name in values})
    result["finite_feature_count"] = sum(finite(v) for v in result["features"].values())
    result["nonfinite_feature_count"] = sum(v is None for v in result["features"].values())
    result["missing_feature_count"] = len(FEATURES) - len(values)
    return result


def analyze(args, plan):
    state = json.loads((args.private_output / "state.json").read_text(encoding="utf-8"))
    if state["plan_sha256"] != sha(args.plan):
        raise ValueError("Analysis plan differs from the job-generation plan")
    expected = planned(plan)
    if [(x["job_id"], x["dataset"], x["volume_id"], x["role"]) for x in state["assignments"]] != [
            (x["job_id"], x["dataset"], x["volume_id"], x["role"]) for x in expected]:
        raise ValueError("Private assignment ledger differs from the fixed plan")
    raw_path = args.private_output / "native_raw.jsonl"
    raw, malformed = {}, 0
    if raw_path.exists():
        with raw_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if row.get("job_id") not in {x["job_id"] for x in expected} or row["job_id"] in raw:
                    raise ValueError("Unexpected or duplicate native extraction record")
                if row.get("engine") != "pyradiomics" or row.get("settings") != plan["settings"]:
                    raise ValueError("Native record settings differ from the fixed profile")
                raw[row["job_id"]] = row
    records = [cleaned(item, raw.get(item["job_id"])) for item in state["assignments"]]
    lookup = {(r["dataset"], r["volume_id"], r["role"]): r for r in records}
    args.public_output.mkdir(parents=True, exist_ok=False)
    with (args.public_output / "native_features.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        for record in records:
            emit(handle, record)
    comparisons = []
    with (args.public_output / "native_differences.jsonl").open("x", encoding="utf-8", newline="\n") as differences:
        for dataset, group in sorted(plan["datasets"].items()):
            for volume in group["volume_ids"]:
                for role, references in plan["comparison_references"].items():
                    for reference_role in references:
                        candidate, reference = (lookup[(dataset, volume, r)] for r in (role, reference_role))
                        identity = {"dataset": dataset, "volume_id": volume, "candidate_role": role,
                                    "reference_role": reference_role}
                        rows = {name: scalar(candidate["features"].get(name), reference["features"].get(name),
                                             plan["scalar_atol"], plan["scalar_rtol"]) for name in FEATURES}
                        for name, row in rows.items():
                            emit(differences, {**identity, "feature": name, **row})
                        comparable = [r for r in rows.values() if r["status"] == "comparable"]
                        summary = {**identity, "planned_features": len(FEATURES),
                            "finite_pair_count": sum(finite(candidate["features"].get(n)) and finite(reference["features"].get(n)) for n in FEATURES),
                            "comparable_features": len(comparable), "beyond_tolerance": sum(r["beyond_tolerance"] for r in comparable),
                            "not_comparable_features": len(FEATURES) - len(comparable),
                            "status": "fully_analyzed" if len(comparable) == len(FEATURES) else "partially_analyzed" if comparable else "not_available",
                            "candidate_extraction_status": candidate["status"], "reference_extraction_status": reference["status"],
                            "landmarks": {name: rows[name] for name in LANDMARKS},
                            "interpretation": "processing_associated_change" if reference_role == "source_working_crop" else "controlled_kernel_mismatch_change"}
                        comparisons.append(summary)
    with (args.public_output / "native_comparisons.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        for row in comparisons:
            emit(handle, row)
    environment_path = args.private_output / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8")) if environment_path.exists() else {}
    native_environment = {"python": environment.get("python"), "platform": environment.get("platform"),
        "packages": {name: environment.get("packages", {}).get(name) for name in ("pyradiomics", "SimpleITK", "numpy", "scipy")}}
    summary = {"schema": "native-sampling-feature-results-1.0", "plan_sha256": sha(args.plan),
        "script_sha256": sha(Path(__file__)), "adapter_sha256": plan["adapter_sha256"],
        "input_manifest_sha256": state["input_manifest_sha256"], "raw_numeric_record_sha256": sha(raw_path) if raw_path.exists() else None,
        "planned_extractions": plan["planned_extractions"], "planned_comparisons": plan["planned_comparisons"],
        "feature_names": list(FEATURES), "settings": plan["settings"], "scalar_atol": plan["scalar_atol"],
        "scalar_rtol": plan["scalar_rtol"], "native_environment": native_environment,
        "malformed_native_record_lines": malformed, "datasets": {},
        "scope": "Fixed six-volume descriptive subset. Correct resampling may change features. Numerical tolerances are not clinical equivalence margins; no patient inference or extractor-defect claim."}
    for dataset in plan["datasets"]:
        subset = [r for r in records if r["dataset"] == dataset]
        paired = [r for r in comparisons if r["dataset"] == dataset]
        summary["datasets"][dataset] = {"planned_volumes": 3, "planned_extractions": 15, "planned_comparisons": 12,
            "extraction_status": dict(Counter(r["status"] for r in subset)),
            "comparison_status": dict(Counter(r["status"] for r in paired))}
    if len(records) != plan["planned_extractions"] or len(comparisons) != plan["planned_comparisons"]:
        raise ValueError("Planned denominator mismatch")
    save(args.public_output / "native_summary.json", summary)
    print(json.dumps({"planned_extractions": len(records), "planned_comparisons": len(comparisons),
                      "extraction_status": dict(Counter(r["status"] for r in records))}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "extract", "analyze", "all"), default="all")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    for key in ("plan", "manifest", "private_output", "public_output", "adapter", "python"):
        setattr(args, key, getattr(args, key).resolve())
    repository = args.adapter.parent.parent
    if args.private_output.is_relative_to(repository):
        parser.error("Private jobs and logs must remain outside the adapter's software repository")
    if args.public_output.is_relative_to(args.private_output) or args.private_output.is_relative_to(args.public_output):
        parser.error("Public and private output directories must be separate, non-nested locations")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if args.phase in ("prepare", "all"):
        prepare(args, plan)
    if args.phase in ("extract", "all"):
        extract(args, plan)
    if args.phase in ("analyze", "all"):
        analyze(args, plan)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        # Detailed native messages remain private; never print paths/tracebacks.
        print(json.dumps({"status": "stopped", "error_type": type(error).__name__,
                          "reason": "Inspect the private run state; no prior records were replaced."}), file=sys.stderr)
        raise SystemExit(2)
