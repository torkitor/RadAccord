"""Integrity changes must fail without requiring any clinical image input."""
import importlib.util
import json
from pathlib import Path
import shutil

REPOSITORY = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("sampling_freeze_verifier", REPOSITORY / "scripts/verify_sampling_freeze.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture_copy(tmp_path):
    mapping = json.loads((REPOSITORY / MODULE.MAPPING_PATH).read_text())
    names = [MODULE.FREEZE_PATH, MODULE.MAPPING_PATH, MODULE.ARCHIVE_PATH]
    names.extend(entry["repository_path"] for entry in mapping["files"])
    for name in names:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / name, destination)
    return tmp_path


def test_relocated_files_and_original_archive_pass(tmp_path):
    report = MODULE.verify(fixture_copy(tmp_path))
    assert report["status"] == "passed"
    assert report["verified_frozen_files"] == 16
    assert report["historical_archive_verified"]
    assert not report["clinical_images_required"]


def test_modified_payload_fails_without_newline_normalization(tmp_path):
    root = fixture_copy(tmp_path)
    target = root / "protocol/native_feature_plan.json"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    report = MODULE.verify(root)
    assert report["status"] == "failed"
    assert any(item["file"] == "protocol/native_feature_plan.json" and item["reason"] == "frozen_payload_hash_mismatch" for item in report["failures"])


def test_changed_freeze_cannot_redefine_authority(tmp_path):
    root = fixture_copy(tmp_path)
    target = root / MODULE.FREEZE_PATH
    target.write_bytes(target.read_bytes() + b" ")
    report = MODULE.verify(root)
    assert report["status"] == "failed"
    assert report["verified_frozen_files"] == 0
    assert {"file": MODULE.FREEZE_PATH, "reason": "pinned_hash_mismatch"} in report["failures"]


def test_mapping_tampering_fails_before_paths_are_followed(tmp_path):
    root = fixture_copy(tmp_path)
    target = root / MODULE.MAPPING_PATH
    mapping = json.loads(target.read_text())
    mapping["files"][0]["repository_path"] = "../outside.txt"
    target.write_text(json.dumps(mapping), encoding="utf-8")
    report = MODULE.verify(root)
    assert report["status"] == "failed"
    assert report["verified_frozen_files"] == 0
    assert {"file": MODULE.MAPPING_PATH, "reason": "pinned_hash_mismatch"} in report["failures"]


def test_archive_corruption_fails(tmp_path):
    root = fixture_copy(tmp_path)
    target = root / MODULE.ARCHIVE_PATH
    with target.open("r+b") as handle:
        first = handle.read(1)
        handle.seek(0)
        handle.write(bytes([first[0] ^ 1]))
    report = MODULE.verify(root)
    assert report["status"] == "failed"
    assert report["verified_frozen_files"] == 16
    assert not report["historical_archive_verified"]


def test_missing_payload_is_not_ignored(tmp_path):
    root = fixture_copy(tmp_path)
    (root / "protocol/native_feature_plan.json").unlink()
    report = MODULE.verify(root)
    assert report["status"] == "failed"
    assert report["verified_frozen_files"] == 15
    assert {"file": "protocol/native_feature_plan.json", "reason": "regular_file_unavailable"} in report["failures"]
