"""Small installed command interface; reports exclude raw exception messages."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import __version__


def _write_json(path, report):
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    _write_text(path, text)


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _protect_outputs(outputs, inputs):
    resolved = [p.resolve() for p in outputs if p is not None]
    if len(set(resolved)) != len(resolved) or set(resolved) & {Path(p).resolve() for p in inputs}:
        raise ValueError("Report destinations must be distinct from inputs and one another.")


def _unavailable():
    return {"schema_version": "1.0", "decision": "unavailable",
            "reason": "The requested operation could not be evaluated. Check the inputs, configuration and installed engine environment."}


_SAMPLING_UNAVAILABLE_HTML = (
    '<!doctype html><html lang="en"><meta charset="utf-8">'
    '<title>RadAccord | Sampling audit unavailable</title>'
    '<h1>Sampling audit unavailable</h1>'
    '<p>This execution did not produce a completed sampling report. '
    'No input preservation or feature reuse is established by this report.</p></html>')


def _verify(args):
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        plan = None  # The historical CLI will record an unavailable plan.
    inputs = [args.plan]
    steps = plan.get("steps") if isinstance(plan, dict) else None
    for step in steps if isinstance(steps, list) else []:
        if isinstance(step, dict):
            for role in ("source", "candidate"):
                item = step.get(role)
                if isinstance(item, dict):
                    inputs.extend(args.plan.parent / item[key] for key in ("image", "mask")
                                  if isinstance(item.get(key), str))
    _protect_outputs([args.report, args.html], inputs)
    _write_json(args.report, _unavailable())
    if args.html:
        _write_text(args.html, _SAMPLING_UNAVAILABLE_HTML)
    with tempfile.TemporaryDirectory(prefix="radaccord-verify-") as directory:
        report_path = Path(directory) / "report.json"
        command = [sys.executable, "-m", "radaccord.legacy", "--plan", str(args.plan.resolve()),
                   "--report", str(report_path)]
        if args.html:
            command += ["--html", str(Path(directory) / "report.html")]
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, check=False)
        child_report_available = False
        if completed.returncode not in (0, 1, 2) or not report_path.is_file():
            report = _unavailable()
        else:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            expected_codes = {"sampling_satisfied": 0, "review_required": 1, "unavailable": 2}
            child_report_available = (isinstance(report, dict)
                                      and expected_codes.get(report.get("decision")) == completed.returncode)
            if not child_report_available:
                report = _unavailable()
        _write_json(args.report, report)
        if args.html:
            child_html = Path(directory) / "report.html"
            html = child_html.read_text(encoding="utf-8") if child_report_available and child_html.is_file() else _SAMPLING_UNAVAILABLE_HTML
            _write_text(args.html, html)
    print(report["decision"])
    return 0 if report["decision"] == "sampling_satisfied" else 2 if report["decision"] == "unavailable" else 1


def _native_unavailable(engine, reason_code):
    return {"schema_version": "radaccord-native-1", "profile": "native_adapter_unavailable",
            "engine": {"name": engine}, "status": "unavailable", "checkpoints": [],
            "reason_code": reason_code, "unverified_obligations": ["native_processing"],
            "scope": "The requested native operation could not be evaluated. No feature or processing acceptance is established."}


def _write_native_reports(args, report):
    _write_json(args.report, report)
    if args.html or args.methods:
        from .reporting import render_html, methods_text
        if args.html:
            _write_text(args.html, render_html(report))
        if args.methods:
            _write_text(args.methods, methods_text(report))


def _native(args):
    from . import audit_mirp, audit_pyradiomics
    inputs = [args.image, args.mask] + ([args.config] if args.config else [])
    _protect_outputs([args.report, args.html, args.methods], inputs)
    _write_native_reports(args, _native_unavailable(args.engine, "native_execution_not_completed"))
    try:
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
        audit = audit_pyradiomics if args.engine == "pyradiomics" else audit_mirp
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = audit(str(args.image), str(args.mask), config=config, label=args.label)
        report = result["report"]
    except Exception:
        report = _native_unavailable(args.engine, "native_operation_could_not_be_evaluated")
    _write_native_reports(args, report)
    status = report.get("status", "unavailable")
    codes = {"satisfied": 0, "violated": 1, "indeterminate": 1, "unavailable": 2}
    print(status if status in codes else "unavailable")
    return codes.get(status, 2)


def _demo(args):
    from .legacy import physical_contracts
    import numpy as np
    args.output.mkdir(parents=True, exist_ok=False)
    frame = physical_contracts.phantom(7)
    source = physical_contracts.write_frame(frame, args.output, "source")
    candidate = physical_contracts.write_frame(frame, args.output, "candidate")
    sampling = {"index_map": np.eye(4).tolist(), "candidate_shape": list(frame.data.shape),
                "interpolation": "nearest", "outside_value": 0,
                "position_atol_mm": 1e-4, "intensity_atol": 1e-4}
    plan = {"schema_version": "1.0", "steps": [{
        "source": {"image": source[0].name, "mask": source[1].name, "label": 1},
        "candidate": {"image": candidate[0].name, "mask": candidate[1].name, "label": 1},
        "sampling": sampling}]}
    _write_json(args.output / "plan.json", plan)
    return _verify(argparse.Namespace(plan=args.output / "plan.json", report=args.output / "report.json",
                                      html=args.output / "report.html"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Physical consistency checks for declared radiomics operations.")
    parser.add_argument("--version", action="version", version="RadAccord " + __version__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("version", help="Show the installed package version.")
    demo = commands.add_parser("demo", help="Generate and audit synthetic identity inputs; no engine required.")
    demo.add_argument("--output", type=Path, required=True, help="New directory for synthetic inputs, plan and reports.")
    verify = commands.add_parser("verify", help="Audit a declared sampling plan.")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--report", type=Path, required=True)
    verify.add_argument("--html", type=Path)
    native = commands.add_parser("native", help="Run an optional engine and save only its audit report.")
    native.add_argument("--engine", choices=("pyradiomics", "mirp"), required=True)
    native.add_argument("--image", type=Path, required=True)
    native.add_argument("--mask", type=Path, required=True)
    native.add_argument("--config", type=Path, help="JSON object containing engine-specific configuration.")
    native.add_argument("--label", type=int, default=1)
    native.add_argument("--report", type=Path, required=True)
    native.add_argument("--html", type=Path, help="Optional standalone audit report.")
    native.add_argument("--methods", type=Path, help="Optional methods text derived from this audit report.")
    args = parser.parse_args(argv)
    if args.command == "version":
        print("RadAccord " + __version__)
        return 0
    if not args.command:
        parser.print_help()
        return 0
    try:
        return {"demo": _demo, "verify": _verify, "native": _native}[args.command](args)
    except Exception:
        # Raw reader/engine exceptions can contain private filenames or traces.
        print("RadAccord: operation unavailable. Check inputs, output destinations and optional dependencies.", file=sys.stderr)
        return 2
