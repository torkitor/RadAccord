"""Packaging boundaries, public dispatch and command reports; no native engine required."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile


class PackagingTests(unittest.TestCase):
    def test_import_is_lazy_and_legacy_does_not_change_public_imports(self):
        code = """
import sys, types
before = list(sys.path)
import radaccord
from importlib.metadata import version
assert radaccord.__version__ == version('radaccord')
assert 'numpy' not in sys.modules and 'radiomics' not in sys.modules and 'mirp' not in sys.modules
sentinel = types.ModuleType('physical_contracts')
sys.modules['physical_contracts'] = sentinel
from radaccord.legacy import Frame, physical_contracts, sampling_contracts
assert sys.path == before
assert sys.modules['physical_contracts'] is sentinel
assert 'sampling_contracts' not in sys.modules
assert Frame is physical_contracts.Frame is sampling_contracts.Frame
"""
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_public_api_forwards_configuration_and_label(self):
        import radaccord
        for engine in ("pyradiomics", "mirp"):
            def audit(image, mask, *, config=None, label=1):
                return image, mask, config, label
            module = types.ModuleType("radaccord." + engine)
            setattr(module, "audit_" + engine, audit)
            with patch.dict(sys.modules, {module.__name__: module}):
                actual = getattr(radaccord, "audit_" + engine)("image", "mask", config={"test": True}, label=3)
            self.assertEqual(actual, ("image", "mask", {"test": True}, 3))

    def test_demo_and_sampling_violation_use_installed_entrypoint(self):
        import nibabel as nib
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            completed = subprocess.run([sys.executable, "-m", "radaccord", "demo", "--output", str(output)],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["feature_reuse"], "input_roi_preserved")
            image_path = output / "candidate_image.nii.gz"
            image = nib.load(image_path)
            changed = nib.Nifti1Image(image.get_fdata() + 1, image.affine, image.header)
            nib.save(changed, image_path)
            completed = subprocess.run([sys.executable, "-m", "radaccord", "verify", "--plan", str(output / "plan.json"),
                                        "--report", str(output / "changed.json")], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            report = json.loads((output / "changed.json").read_text())
            self.assertEqual(report["first_failed_checkpoint"], 1)
            self.assertEqual(report["checkpoints"][0]["decision"], "violated")
            self.assertNotIn(directory, json.dumps(report))

    def test_invalid_plan_gets_current_unavailable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            plan = output / "plan.json"
            plan.write_text("private-path-invalid-json")
            report = output / "report.json"
            report.write_text('{"decision": "sampling_satisfied"}')
            completed = subprocess.run([sys.executable, "-m", "radaccord", "verify", "--plan", str(plan),
                                        "--report", str(report)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(report.read_text())["decision"], "unavailable")
            self.assertNotIn("private-path", report.read_text() + completed.stdout + completed.stderr)

    def test_native_error_report_hides_exception_and_inputs(self):
        from radaccord.cli import main
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            with patch("radaccord.audit_pyradiomics", side_effect=RuntimeError("private patient-path secret")):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = main(["native", "--engine", "pyradiomics", "--image", "private_image.nii.gz",
                                   "--mask", "private_mask.nii.gz", "--report", str(report)])
            text = report.read_text()
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(text)["status"], "unavailable")
            self.assertNotIn("private", text)
            self.assertNotIn("secret", text)

    def test_native_cli_filenames_match_the_string_api(self):
        from importlib.util import find_spec
        import nibabel as nib
        import numpy as np
        import radaccord
        from radaccord.cli import main
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            image, mask = output / "synthetic_image.nii.gz", output / "synthetic_mask.nii.gz"
            data = np.arange(125, dtype=np.float64).reshape(5, 5, 5)
            membership = np.zeros(data.shape, dtype=np.uint8)
            membership[1:4, 1:4, 1:4] = 1
            for path, values in ((image, data), (mask, membership)):
                volume = nib.Nifti1Image(values, np.eye(4))
                volume.header.set_xyzt_units("mm")
                nib.save(volume, path)
            config = {"image_modality": "mr", "base_feature_families": ["statistical"]}
            config_path = output / "settings.json"
            config_path.write_text(json.dumps(config))
            native_available = find_spec("mirp") is not None
            if native_available:
                api = radaccord.audit_mirp
            else:
                # Core-only runs protect the filename contract with a strict
                # stand-in; the MIRP CI environment executes the actual API.
                def api(image, mask, *, config=None, label=1):
                    if not isinstance(image, str) or not isinstance(mask, str):
                        raise NotImplementedError("The filename interface requires strings.")
                    selected = nib.load(mask).get_fdata() == label
                    features = {"mean": float(nib.load(image).get_fdata()[selected].mean())}
                    return {"features": features, "report": {
                        "status": "satisfied", "selected_voxels": int(selected.sum())}}
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                reference = api(str(image), str(mask), config=config, label=1)
            observed = {}

            def retain(*args, **kwargs):
                result = api(*args, **kwargs)
                observed.update(result)
                return result

            report_path = output / "report.json"
            with patch("radaccord.audit_mirp", side_effect=retain):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = main(["native", "--engine", "mirp", "--image", str(image),
                                 "--mask", str(mask), "--config", str(config_path),
                                 "--report", str(report_path)])
            self.assertEqual(code, 0)
            if native_available:
                import pandas as pd
                pd.testing.assert_frame_equal(reference["features"], observed["features"], check_exact=True)
            else:
                self.assertEqual(reference["features"], observed["features"])
            actual = json.loads(report_path.read_text())
            expected = dict(reference["report"])
            actual.pop("elapsed_seconds", None)
            expected.pop("elapsed_seconds", None)
            self.assertEqual(actual, expected)
            self.assertNotIn(directory, report_path.read_text())

    def test_verify_child_failure_replaces_previous_positive_html(self):
        from radaccord.cli import main
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            plan, report, html = (output / name for name in ("plan.json", "report.json", "report.html"))
            plan.write_text('{"schema_version": "1.0", "steps": []}')
            for failure_mode in ("signal", "exit", "launch"):
                with self.subTest(failure_mode=failure_mode):
                    report.write_text('{"decision": "sampling_satisfied"}')
                    html.write_text("STALE_POSITIVE_REPORT")
                    observed = {}

                    def fail(command, **kwargs):
                        observed["report"] = json.loads(report.read_text())
                        observed["html"] = html.read_text()
                        if failure_mode == "launch":
                            raise OSError("private process-launch trace")
                        Path(command[command.index("--html") + 1]).write_text("INCOMPLETE_POSITIVE_CHILD_REPORT")
                        if failure_mode == "exit":
                            Path(command[command.index("--report") + 1]).write_text('{"decision": "sampling_satisfied"}')
                        return subprocess.CompletedProcess(command, 1 if failure_mode == "exit" else -9,
                                                           b"", b"private child trace")

                    with patch("radaccord.cli.subprocess.run", side_effect=fail):
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            code = main(["verify", "--plan", str(plan), "--report", str(report), "--html", str(html)])
                    self.assertEqual(code, 2)
                    self.assertEqual(observed["report"]["decision"], "unavailable")
                    self.assertIn("unavailable", observed["html"].lower())
                    self.assertNotIn("STALE_POSITIVE", observed["html"])
                    self.assertEqual(json.loads(report.read_text())["decision"], "unavailable")
                    self.assertIn("unavailable", html.read_text().lower())
                    self.assertNotIn("POSITIVE", html.read_text())
                    self.assertNotIn("private", report.read_text() + html.read_text())

    def test_native_failure_replaces_all_reports_before_engine_execution(self):
        from radaccord.cli import main
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report, html, methods = (output / name for name in ("report.json", "report.html", "methods.txt"))
            for interrupted in (False, True):
                with self.subTest(interrupted=interrupted):
                    report.write_text('{"status": "satisfied", "marker": "STALE_POSITIVE_REPORT"}')
                    html.write_text("STALE_POSITIVE_REPORT")
                    methods.write_text("STALE_POSITIVE_REPORT")
                    observed = {}

                    def fail(*args, **kwargs):
                        observed.update(report=json.loads(report.read_text()), html=html.read_text(),
                                        methods=methods.read_text())
                        if interrupted:
                            raise SystemExit(23)
                        raise RuntimeError("private engine trace")

                    command = ["native", "--engine", "mirp", "--image", "synthetic_image.nii",
                               "--mask", "synthetic_mask.nii", "--report", str(report),
                               "--html", str(html), "--methods", str(methods)]
                    with patch("radaccord.audit_mirp", side_effect=fail):
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            if interrupted:
                                with self.assertRaises(SystemExit):
                                    main(command)
                            else:
                                self.assertEqual(main(command), 2)
                    self.assertEqual(observed["report"]["status"], "unavailable")
                    self.assertEqual(observed["report"]["reason_code"], "native_execution_not_completed")
                    self.assertNotIn("STALE_POSITIVE", json.dumps(observed))
                    current = json.loads(report.read_text())
                    self.assertEqual(current["status"], "unavailable")
                    reason = "native_execution_not_completed" if interrupted else "native_operation_could_not_be_evaluated"
                    self.assertEqual(current["reason_code"], reason)
                    self.assertIn("unavailable", html.read_text().lower())
                    self.assertIn("could not be evaluated", methods.read_text())
                    self.assertNotIn("STALE_POSITIVE", report.read_text() + html.read_text() + methods.read_text())
                    self.assertNotIn("private", report.read_text() + html.read_text() + methods.read_text())
                    self.assertFalse(list(output.glob("*.tmp")))

    def test_report_cannot_overwrite_native_input(self):
        from radaccord.cli import main
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "input.nii"
            image.write_bytes(b"preserve-original")
            with patch("radaccord.audit_mirp") as audit:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = main(["native", "--engine", "mirp", "--image", str(image),
                                   "--mask", "mask.nii", "--report", str(image)])
                audit.assert_not_called()
            self.assertEqual(result, 2)
            self.assertEqual(image.read_bytes(), b"preserve-original")

    def test_native_exit_codes_and_optional_reports_preserve_scope(self):
        from radaccord.cli import main
        renderer = types.ModuleType("radaccord.reporting")
        renderer.render_html = lambda report: "<p>" + report["status"] + "</p>"
        renderer.methods_text = lambda report: "Observed input checks: " + report["status"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for status, code in (("satisfied", 0), ("violated", 1), ("indeterminate", 1), ("unavailable", 2)):
                result = {"features": {"private_feature_value": 123}, "report": {"status": status}}
                with patch("radaccord.audit_mirp", return_value=result), patch.dict(sys.modules, {renderer.__name__: renderer}):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        actual = main(["native", "--engine", "mirp", "--image", "input.nii", "--mask", "mask.nii",
                                       "--report", str(output / "report.json"), "--html", str(output / "report.html"),
                                       "--methods", str(output / "methods.txt")])
                self.assertEqual(actual, code)
                self.assertEqual(json.loads((output / "report.json").read_text()), {"status": status})
                self.assertEqual((output / "methods.txt").read_text(), "Observed input checks: " + status)
                self.assertIn(status, (output / "report.html").read_text())

    @unittest.skipUnless(os.environ.get("RADACCORD_TEST_WHEEL"), "Set RADACCORD_TEST_WHEEL for built-artifact verification.")
    def test_wheel_preserves_frozen_sources_and_excludes_study_data(self):
        root = Path(__file__).resolve().parents[1]
        with zipfile.ZipFile(os.environ["RADACCORD_TEST_WHEEL"]) as archive:
            names = archive.namelist()
            for source in (root / "software").glob("*.py"):
                actual = archive.read("radaccord/_frozen/" + source.name)
                self.assertEqual(hashlib.sha256(actual).digest(), hashlib.sha256(source.read_bytes()).digest())
            self.assertEqual(archive.read("radaccord_sampling.py"), (root / "radaccord_sampling.py").read_bytes())
            self.assertFalse(any(name.endswith((".nii", ".nii.gz", ".jsonl", ".zip")) for name in names))
            self.assertFalse(any(name.startswith(("data/", "work/", "results/", "software/")) for name in names))


if __name__ == "__main__":
    unittest.main()
