"""Portable human-readable evidence. No network, scripts or raw image data."""
from __future__ import annotations

import html
import json

from . import __version__


def methods_text(report):
    """A factual methods draft; authors must add acquisition and study details."""
    if not report.get('checkpoints') or report.get('profile') == 'native_adapter_unavailable':
        return ('The requested native audit could not be evaluated; no observed processing '
                'relationships or extraction provenance were established by this report.')
    engine = report.get('engine', {})
    checker = report.get('checker', {})
    checks = report.get('checkpoints', [])
    counts = {state: sum(item.get('status') == state for item in checks)
              for state in ('satisfied', 'violated', 'indeterminate', 'unavailable')}
    profile = report.get('profile', 'unspecified')
    declaration_text = ("The declared relationships were determined before native execution. "
                        if report.get('declarations') else
                        "No supported processing declaration could be established for this configuration. ")
    return (f"Physical consistency at the observed native processing boundaries was assessed with "
            f"RadAccord {checker.get('version', __version__)} "
            f"(https://github.com/torkitor/RadAccord), using profile {profile} and "
            f"{engine.get('name', 'unspecified extractor')} {engine.get('version', 'unspecified')}. "
            f"{declaration_text}"
            f"Of {len(checks)} observed checkpoints, {counts['satisfied']} were satisfied, "
            f"{counts['violated']} violated, {counts['indeterminate']} indeterminate and "
            f"{counts['unavailable']} unavailable. "
            f"This assessment did not validate feature formulae, unobserved states or clinical utility. "
            f"Available provenance identifiers are retained in the accompanying evidence report. "
            f"Configuration identifier: "
            f"{report.get('configuration_sha256', 'unavailable')}.")


def compare_evidence(previous, current):
    """Explain when earlier evidence cannot stand in for a new execution.

    Equality establishes only equality of these records. It never authorises
    reuse of a previous pass for an unobserved execution.
    """
    fields = ('schema_version', 'profile', 'engine', 'checker', 'configuration_sha256',
              'source', 'declarations', 'feature_values', 'feature_tables', 'unverified_obligations')
    changed = [key for key in fields if previous.get(key) != current.get(key)]
    return {'changed_evidence_fields': changed,
            'relationship': 'different_evidence_scope' if changed else 'matching_recorded_scope',
            'current_status': current.get('status', 'unavailable'),
            'note': 'Each new extraction still requires its own observations. Matching records '
                    'do not establish unchanged unobserved processing or clinical validity.'}


def render_html(report):
    """A standalone report with a conspicuous, bounded verdict."""
    escape = lambda value: html.escape(str(value), quote=True)
    status = str(report.get('status', 'unavailable'))
    state_class = status if status in ('satisfied', 'violated', 'indeterminate', 'unavailable') else 'unavailable'
    checks = report.get('checkpoints', [])
    rows = ''.join('<tr><td>'+escape(item.get('checkpoint', 'observation'))+'</td><td>'+
                   escape(item.get('status', 'unavailable'))+'</td><td>'+
                   escape(item.get('reason_code', 'See numerical evidence below'))+'</td></tr>' for item in checks)
    engine = report.get('engine', {})
    details = escape(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    limits = ''.join('<li>'+escape(str(item).replace('_', ' '))+'</li>'
                     for item in report.get('unverified_obligations', []))
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>RadAccord · Native evidence</title><style>
:root{font-family:Arial,Helvetica,sans-serif;color:#203346;background:#f3f5f7}
body{max-width:1000px;margin:0 auto;padding:48px 24px}header{border-bottom:3px solid #243e53;padding-bottom:24px}
.brand{font-size:14px;letter-spacing:.15em;font-weight:bold}h1{font-size:36px;line-height:1.1;letter-spacing:-.03em;margin:22px 0 14px}
h2{font-size:19px;margin-top:32px}p,li{font-size:15px;line-height:1.6}small{color:#586979}
.status{display:inline-block;padding:8px 14px;border-radius:4px;background:#e5eaf0;font-weight:bold}
.satisfied{background:#dbece7;color:#245247}.violated{background:#f4dcd7;color:#893d31}
.indeterminate,.unavailable{background:#f0e7d4;color:#68552a}
section{background:white;padding:24px;margin:20px 0;border:1px solid #dce3e8;border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px 8px;border-bottom:1px solid #dce3e8;vertical-align:top}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.45;max-height:650px;overflow:auto;background:#f6f8fa;padding:18px}
.method{overflow-wrap:anywhere}footer{font-size:12px;color:#586979;margin-top:30px}
@media print{body{padding:12px;background:white}pre{max-height:none}details{display:block}}
</style><header><div class="brand">RADACCORD / EXECUTION EVIDENCE</div><h1>Physical consistency,<br>at observed boundaries.</h1>
<p>'''+escape(engine.get('name', 'Native extraction'))+' '+escape(engine.get('version', ''))+'''</p>
<span class="status '''+state_class+'">'+escape(status.upper())+'''</span>
<p>A status describes the declared relationships at the observed checkpoints. It is not a certificate of feature correctness, pipeline completeness or clinical readiness.</p></header>
<section><h2>Observed checkpoints</h2><table><thead><tr><th>Boundary</th><th>Status</th><th>Evidence</th></tr></thead><tbody>'''+rows+'''</tbody></table></section>
<section><h2>Outside this assessment</h2><ul>'''+limits+'''</ul></section>
<section><h2>Methods draft</h2><p class="method">'''+escape(methods_text(report))+'''</p><small>Check against your study and cite the exact released version. This draft does not replace acquisition, segmentation or statistical reporting.</small></section>
<section><h2>Machine-readable evidence</h2><details><summary>Show complete JSON record</summary><pre>'''+details+'''</pre></details></section>
<footer>RadAccord · Research software · This local report contains no executable scripts and makes no network requests.</footer></html>'''
