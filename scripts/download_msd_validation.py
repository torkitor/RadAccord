"""Download two licensed MSD archives, verify published MD5, and extract safely."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
import argparse
import hashlib
import json
import shutil
import tarfile

COMMIT = "20df60253d364be69601114adae3bd609e0cb6f6"
MONAI_SOURCE = f"https://raw.githubusercontent.com/Project-MONAI/MONAI/{COMMIT}/monai/apps/datasets.py"
TASKS = {
    "Task02_Heart": "06ee59366e1e5124267b774dbd654057",
    "Task06_Lung": "8afd997733c7fc0432f71255ba4e52dc",
}

def digest(path):
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    return md5.hexdigest(), sha256.hexdigest()

def download(task, expected, data, concurrency):
    archive = data / (task + ".tar")
    url = "https://msd-for-monai-eu.s3.eu-west-2.amazonaws.com/" + task + ".tar"
    headers = {}
    if not archive.exists():
        partial = archive.with_suffix(".tar.part")
        with urlopen(Request(url, method="HEAD"), timeout=30) as response:
            headers = {key: response.headers.get(key) for key in ("Content-Length", "Last-Modified", "ETag")}
            expected_size = int(headers["Content-Length"])
            if not 0 < expected_size <= 12 * 1024**3:
                raise ValueError("Unexpected archive size")
        read, next_report = 0, 256 * 1024**2
        with partial.open("xb") as output:
            output.truncate(expected_size)
        def transfer(start):
            end = min(start + 16 * 1024**2, expected_size) - 1
            for attempt in range(3):
                try:
                    request = Request(url, headers={"Range": f"bytes={start}-{end}", "If-Match": headers["ETag"]})
                    with urlopen(request, timeout=60) as response:
                        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{expected_size}":
                            raise ValueError("Unexpected byte-range response")
                        block = response.read(end-start+2)
                    if len(block) != end-start+1:
                        raise ValueError("Incomplete byte range")
                    with partial.open("r+b") as output:
                        output.seek(start)
                        output.write(block)
                    return len(block)
                except (TimeoutError, OSError):
                    if attempt == 2:
                        raise
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(transfer, start) for start in range(0, expected_size, 16 * 1024**2)]
            for future in as_completed(futures):
                read += future.result()
                if read >= next_report:
                    print(json.dumps({"task": task, "downloaded_MiB": round(read / 1024**2), "total_MiB": round(expected_size/1024**2)}), flush=True)
                    next_report += 256 * 1024**2
        if read != expected_size:
            raise ValueError("Download size mismatch")
        observed_md5, observed_sha = digest(partial)
        if observed_md5 != expected:
            raise ValueError("Published archive MD5 mismatch: " + task)
        partial.rename(archive)
    else:
        observed_md5, observed_sha = digest(archive)
        if observed_md5 != expected:
            raise ValueError("Existing archive MD5 mismatch: " + task)
        old = data / "download_provenance.json"
        if old.exists():
            for record in json.loads(old.read_text(encoding="utf-8"))["archives"]:
                if record["task"] == task and record["observed_sha256"] == observed_sha:
                    return record
        raise ValueError("Existing archive has no matching acquisition provenance")
    return {"task": task, "url": url, "bytes": archive.stat().st_size,
            "published_md5": expected, "observed_md5": observed_md5,
            "observed_sha256": observed_sha, "response_headers": headers}

def extract(task, data):
    archive, final = data / (task + ".tar"), data / task
    if final.exists():
        inventory = json.loads((data / (task + "_inventory.json")).read_text(encoding="utf-8"))
        if digest(final / "dataset.json")[1] != inventory["dataset_json_sha256"]:
            raise ValueError("Existing extraction metadata differs")
        if any(not (final / row[k]).is_file() for row in inventory["training"] for k in ("image", "label")):
            raise ValueError("Existing extraction is incomplete")
        return inventory
    staging = data / (task + ".extracting")
    if staging.exists():
        raise FileExistsError("Extraction staging already exists: " + task)
    selected, ignored, seen = [], [], set()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                    or ":" in member.name or "\x00" in member.name):
                raise ValueError("Unsafe archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Archive link or special member rejected")
            key = path.as_posix().casefold()
            if key in seen:
                raise ValueError("Duplicate archive destination")
            seen.add(key)
            if not path.parts:
                continue
            if any(part.startswith("._") or part in {".DS_Store", "__MACOSX"} for part in path.parts):
                ignored.append(path.as_posix())
                continue
            if path.parts[0] != task:
                raise ValueError("Unexpected archive root")
            selected.append((member, path))
        staging.mkdir()
        base = staging.resolve()
        for member, path in selected:
            dest = staging.joinpath(*path.parts[1:])
            if not dest.resolve().is_relative_to(base):
                raise ValueError("Extraction escaped staging")
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, dest.open("xb") as output:
                    shutil.copyfileobj(source, output, 4 * 1024 * 1024)
    staging.rename(final)
    metadata = json.loads((final / "dataset.json").read_text(encoding="utf-8"))
    entries = metadata["training"]
    for row in entries:
        for kind in ("image", "label"):
            rel = PurePosixPath(row[kind])
            if rel.is_absolute() or ".." in rel.parts or ":" in row[kind] or "\\" in row[kind]:
                raise ValueError("Unsafe dataset manifest path")
            if not (final / rel).is_file():
                raise ValueError("Missing training file")
    inventory = {
        "task": task, "dataset_json_sha256": digest(final / "dataset.json")[1],
        "metadata": {k: v for k, v in metadata.items() if k not in ("training", "test")},
        "training_pairs": len(entries), "test_images": len(metadata.get("test", [])),
        "image_files": sum(1 for p in final.rglob("*.nii.gz")),
        "training": entries, "test": metadata.get("test", []),
        "ignored_platform_metadata_count": len(ignored),
        "safe_extraction": {"all_paths_validated": True, "links_and_special_files_rejected": True,
                            "duplicate_destinations_rejected": True, "extractall_used": False},
        "inspection_scope": "Archive/member and dataset.json inventory only; no outcomes, labels or intensities analysed.",
    }
    (data / (task + "_inventory.json")).write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return inventory

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True,
                        help='Private destination outside the source repository.')
    parser.add_argument('--public-output', type=Path, required=True,
                        help='Provenance destination; no images or absolute input paths are copied.')
    parser.add_argument('--transport-concurrency', type=int, default=32,
                        help='Parallel 16 MiB requests per archive, 1-64; transport only.')
    args = parser.parse_args()
    data, public = args.data_dir.resolve(), args.public_output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if data.is_relative_to(repo) or repo.is_relative_to(data):
        parser.error('The private data directory must be outside, and not contain, the repository.')
    if data.is_relative_to(public) or public.is_relative_to(data):
        parser.error('Private data and public provenance must occupy separate directory trees.')
    if not 1 <= args.transport_concurrency <= 64:
        parser.error('Transport concurrency must be between 1 and 64.')
    data.mkdir(parents=True, exist_ok=True)
    public.mkdir(parents=True, exist_ok=True)
    with urlopen(MONAI_SOURCE, timeout=30) as response:
        provenance = response.read()
    for task, expected in TASKS.items():
        if task.encode() not in provenance or expected.encode() not in provenance:
            raise ValueError("Pinned MONAI source does not confirm expected digest")
    (data / "MONAI_datasets_source.py.txt").write_bytes(provenance)
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(download, task, expected, data, args.transport_concurrency): task for task, expected in TASKS.items()}
        for future in as_completed(futures):
            record = future.result()
            inventory = extract(record["task"], data)
            record.update({"training_pairs": inventory["training_pairs"], "test_images": inventory["test_images"]})
            results.append(record)
            (data / "download_provenance.json").write_text(json.dumps({
                "accessed_utc": datetime.now(timezone.utc).isoformat(),
                "registry_url": "https://registry.opendata.aws/msd/",
                "dataset_license": "CC-BY-SA-4.0",
                "monai_source_url": MONAI_SOURCE,
                "monai_source_sha256": hashlib.sha256(provenance).hexdigest(),
                "archives": results}, indent=2), encoding="utf-8")
            print(json.dumps({"ready": record["task"], "training_pairs": record["training_pairs"],
                              "test_images": record["test_images"], "sha256": record["observed_sha256"]}), flush=True)
    lines = [
        "# Medical Segmentation Decathlon source record",
        "",
        f"Accessed {datetime.now(timezone.utc).date().isoformat()}. These local research inputs are not part of the public RadAccord software repository.",
        "",
        "Origin: https://registry.opendata.aws/msd/ (managed by the MONAI Development Team); original project: https://medicaldecathlon.com/.",
        "Data licence: CC-BY-SA 4.0, as stated by the AWS registry and original project. Preserve data attribution and applicable share-alike terms separately from the Apache-2.0 software licence.",
        "Cite Antonelli M, Reinke A, Bakas S et al (2022), The Medical Segmentation Decathlon, Nature Communications 13:4128, https://doi.org/10.1038/s41467-022-30695-9; original dataset description: https://arxiv.org/abs/1902.09063.",
        "",
        "Published archive MD5 values were verified against the pinned MONAI source below. SHA-256 values are locally computed identification hashes, not publisher-supplied SHA-256 certificates.",
        MONAI_SOURCE,
        "",
        "| Archive | Bytes | Training pairs | Unlabelled test images | MD5 | SHA-256 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for record in sorted(results, key=lambda x: x["task"]):
        lines.append("| " + " | ".join(str(record[k]) for k in ("task", "bytes", "training_pairs", "test_images", "observed_md5", "observed_sha256")) + " |")
    lines += ["", "Use each task's original dataset.json and the adjacent inventory JSON as the released file census. Released file counts are source-volume counts; no filename-to-participant map is assumed. The original paper and released archive have different reported counts, so the downloaded release governs the file denominator.",
              "", "Extraction validated every member before writing, rejected traversal, absolute paths, links, special members and duplicate destinations, and copied regular files individually into a fresh staging directory. Apple metadata files were omitted and counted. No voxel intensities, features or outcome comparisons were inspected in this acquisition step.",
              "", "Direct archive URLs and HTTP size/date headers are in download_provenance.json. No credentials or private source paths are recorded."]
    (data / "SOURCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name in ('download_provenance.json', 'MONAI_datasets_source.py.txt', 'SOURCE.md'):
        shutil.copyfile(data / name, public / name)
    for task in TASKS:
        shutil.copyfile(data / task / 'dataset.json', public / (task + '_dataset.json'))
        shutil.copyfile(data / (task + '_inventory.json'), public / (task + '_inventory.json'))
    print(json.dumps({'archives_verified': len(results), 'private_images_exported': False}))

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'unavailable', 'reason': 'acquisition_failed',
                          'error_type': type(error).__name__}))
        raise SystemExit(2) from None
