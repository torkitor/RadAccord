"""Verify the relocated sampling freeze and historical archive without clinical inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = "protocol/sampling_freeze.json"
MAPPING_PATH = "protocol/sampling_freeze_locations.json"
ARCHIVE_PATH = "data/RadAccord-1.0.0.zip"
FREEZE_SHA256 = "1618ecf0b48772dead25256a68049e6f9cae5fb5a1996b6ac8d8b89576a23059"
MAPPING_SHA256 = "3a9d1d9bea8516a36a7fccb5dfc49bae4c7ae3c53caf96ed29c507d75d990418"
ARCHIVE_SHA256 = "43ff30b546e1904b1f119c6349747d3e6289b273f2b4ee18c80dc57d0b2970bd"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_file(root, relative):
    """Accept regular repository files through canonical, non-symlink paths."""
    if not isinstance(relative, str):
        raise ValueError("Invalid relative path")
    parts = relative.split("/")
    if (any(p in ("", ".", "..") or p.endswith((" ", ".")) for p in parts)
            or any(c in relative for c in '\\:<>"|?*')
            or any(ord(c) < 32 or ord(c) == 127 for c in relative)):
        raise ValueError("Invalid relative path")
    root = root.resolve()
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlink path rejected")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Path escapes repository")
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Regular file missing")
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def verify(root):
    root = Path(root).resolve()
    failures = []
    checked = 0
    for name, expected in ((FREEZE_PATH, FREEZE_SHA256), (MAPPING_PATH, MAPPING_SHA256)):
        try:
            if digest(safe_file(root, name)) != expected:
                failures.append({"file": name, "reason": "pinned_hash_mismatch"})
        except (OSError, ValueError):
            failures.append({"file": name, "reason": "regular_file_unavailable"})
    # Never interpret a changed freeze or mapping as an updated authority.
    if not failures:
        try:
            freeze = json.loads((root / FREEZE_PATH).read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            mapping = json.loads((root / MAPPING_PATH).read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            frozen = {entry["path"]: entry["sha256"] for entry in freeze["files"]}
            locations = {entry["frozen_path"]: entry["repository_path"] for entry in mapping["files"]}
            if (len(frozen) != 16 or len(freeze["files"]) != 16 or len(locations) != 16
                    or len(mapping["files"]) != 16 or set(frozen) != set(locations)
                    or len({p.casefold() for p in locations.values()}) != 16
                    or mapping["freeze_file"] != FREEZE_PATH or mapping["freeze_sha256"] != FREEZE_SHA256
                    or mapping["historical_archive"] != ARCHIVE_PATH
                    or freeze["historical_scientific_archive_sha256"] != ARCHIVE_SHA256):
                raise ValueError("Freeze-to-repository mapping differs")
            for original, expected in frozen.items():
                name = locations[original]
                try:
                    if not re.fullmatch("[0-9a-f]{64}", expected) or digest(safe_file(root, name)) != expected:
                        failures.append({"file": name, "reason": "frozen_payload_hash_mismatch"})
                    else:
                        checked += 1
                except (OSError, ValueError):
                    failures.append({"file": name, "reason": "regular_file_unavailable"})
        except (OSError, ValueError, KeyError, TypeError):
            failures.append({"file": MAPPING_PATH, "reason": "invalid_freeze_mapping"})
    try:
        archive_ok = digest(safe_file(root, ARCHIVE_PATH)) == ARCHIVE_SHA256
    except (OSError, ValueError):
        archive_ok = False
    if not archive_ok:
        failures.append({"file": ARCHIVE_PATH, "reason": "historical_archive_hash_mismatch_or_unavailable"})
    return {"status": "passed" if not failures else "failed", "verified_frozen_files": checked,
            "expected_frozen_files": 16, "freeze_sha256": FREEZE_SHA256,
            "location_mapping_sha256": MAPPING_SHA256, "historical_archive_sha256": ARCHIVE_SHA256,
            "historical_archive_verified": archive_ok, "clinical_images_required": False,
            "byte_normalization_applied": False, "failures": failures,
            "scope": "Checks the retained internal pre-evaluation freeze, its relocated bytes and historical scientific archive; not an independent public preregistration or fresh scientific validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository directory (default: parent of this script directory)")
    args = parser.parse_args()
    report = verify(args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
