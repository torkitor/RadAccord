"""Audit declared spatial sampling before feature extraction or reuse.

Run: python radaccord_sampling.py --plan plan.json --report report.json
An optional --html report.html creates a standalone local summary.
The plan must be specified independently of the candidate being checked.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
from pathlib import Path
import sys

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'software'))
from physical_contracts import Frame, POSITION_ATOL_MM, read_frame
from sampling_contracts import sampling_witness


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _pair_corner_error(image_path, mask_path):
    """Maximum physical separation of paired voxel centres, in millimetres."""
    image, mask = nib.load(image_path), nib.load(mask_path)
    if len(image.shape) != 3 or image.shape != mask.shape:
        return None
    corners = np.array(list(itertools.product(*[(0, n - 1) for n in image.shape])), dtype=float)
    homogeneous = np.column_stack((corners, np.ones(len(corners))))
    difference = homogeneous @ (image.affine - mask.affine).T
    return float(np.linalg.norm(difference[:, :3], axis=1).max())


def _read_candidate(image_path, mask_path, label, position_atol_mm=POSITION_ATOL_MM):
    """Retain the original header domain but allow an observed empty ROI.

    The new witness validates all array/affine properties and can then report
    an ROI that disappeared. The trusted source still uses read_frame unchanged.
    """
    image, mask = nib.load(image_path), nib.load(mask_path)
    for item in (image, mask):
        if item.header.get_xyzt_units()[0] != 'mm':
            raise ValueError('Explicit millimetre spatial units are required.')
        q, qcode = item.get_qform(coded=True)
        s, scode = item.get_sform(coded=True)
        if qcode and scode and not np.allclose(q, s, atol=POSITION_ATOL_MM, rtol=0):
            raise ValueError('Conflicting spatial forms are outside this profile.')
    frame = Frame(image.get_fdata(), np.asanyarray(mask.dataobj), image.affine, label)
    geometry = {'same_shape': image.shape == mask.shape,
                'same_affine': bool(np.allclose(image.affine, mask.affine, atol=POSITION_ATOL_MM, rtol=0))}
    error = _pair_corner_error(image_path, mask_path)
    geometry['physical_corner_agreement'] = error is not None and error <= position_atol_mm
    return frame, geometry


def verify_sampling(source_image, source_mask, candidate_image, candidate_mask,
                    sampling, source_label=1, candidate_label=1):
    """Return path-free evidence for one declared source-to-candidate operation.

    Unsupported inputs raise an exception; the CLI records them as unavailable.
    A successful sampling check is not universal radiomic feature equivalence.
    """
    source, source_geometry = read_frame(source_image, source_mask, source_label)
    position_tolerance = sampling['position_atol_mm']
    candidate, candidate_geometry = _read_candidate(candidate_image, candidate_mask, candidate_label,
                                                    position_tolerance)
    witness = sampling_witness(source, candidate, sampling)
    source_pair_error = _pair_corner_error(source_image, source_mask)
    candidate_pair_error = _pair_corner_error(candidate_image, candidate_mask)
    source_geometry['physical_corner_agreement'] = source_pair_error is not None and source_pair_error <= position_tolerance
    paired = all(source_geometry.values()) and all(candidate_geometry.values())
    if not paired or witness['status'] == 'violated':
        decision = 'violated'
    elif witness['status'] != 'satisfied':
        decision = 'indeterminate'
    elif witness['coverage']['status'] == 'violated':
        decision = 'roi_support_lost'
    elif witness['coverage']['status'] != 'satisfied':
        decision = 'indeterminate'
    elif not witness['coverage']['candidate_roi_voxels']:
        decision = 'sampled_roi_empty'
    elif witness['feature_reuse']['decision'] == 'requires_reextraction':
        decision = 'sampling_satisfied_reextract'
    elif witness['feature_reuse']['decision'] == 'input_roi_preserved':
        decision = 'input_roi_preserved'
    else:
        decision = 'blocked'
    return {
        'decision': decision,
        'paired_geometry': {'source': source_geometry, 'candidate': candidate_geometry},
        'paired_max_corner_error_mm': {'source': source_pair_error, 'candidate': candidate_pair_error},
        'sampling': witness,
        'input_sha256': {
            role: file_sha256(path) for role, path in (
                ('source_image', source_image), ('source_mask', source_mask),
                ('candidate_image', candidate_image), ('candidate_mask', candidate_mask))
        },
    }


def audit_plan(plan, base_directory=Path('.')):
    """Audit an ordered list of checkpoints; require byte-linked stage inputs.

    The first step's source is trusted. Later inputs must match the preceding
    checkpoint's outputs. This locates the first observed failed checkpoint,
    not an unobserved internal error or the cause of a discrepancy.
    """
    if plan.get('schema_version') != '1.0' or not isinstance(plan.get('steps'), list) or not plan['steps']:
        raise ValueError('A version 1.0 plan with a nonempty steps list is required.')
    base_directory = Path(base_directory)
    rows = []
    previous = None
    first_failed = None
    first_review = None
    first_unverified = None
    for index, step in enumerate(plan['steps'], start=1):
        try:
            source, candidate = step['source'], step['candidate']
            paths = [base_directory / item[key] for item, key in (
                (source, 'image'), (source, 'mask'), (candidate, 'image'), (candidate, 'mask'))]
            row = verify_sampling(*paths, step['sampling'],
                                  source_label=source.get('label', 1),
                                  candidate_label=candidate.get('label', 1))
            current = row['input_sha256']
            linked = previous is None and index == 1 or previous is not None and (
                current['source_image'] == previous['candidate_image'] and
                current['source_mask'] == previous['candidate_mask'] and
                source.get('label', 1) == plan['steps'][index-2]['candidate'].get('label', 1))
            row['linked_to_previous_checkpoint'] = bool(linked)
            if not linked:
                row['decision'] = 'unavailable'
                row['reason'] = 'The checkpoint input does not match the preceding retained output.'
            previous = current
        except Exception as error:
            # Third-party reader exceptions can contain private filesystem paths.
            row = {'decision': 'unavailable', 'error_type': type(error).__name__,
                   'reason': 'Input, sampling declaration or checkpoint could not be evaluated.'}
            previous = None
        row['checkpoint'] = index
        if first_failed is None and row['decision'] in {'violated', 'roi_support_lost', 'sampled_roi_empty', 'blocked'}:
            first_failed = index
        if first_unverified is None and row['decision'] in {'unavailable', 'indeterminate'}:
            first_unverified = index
        if first_review is None and row['decision'] not in {'input_roi_preserved', 'sampling_satisfied_reextract'}:
            first_review = index
        rows.append(row)
    decision = 'review_required' if first_review else 'sampling_satisfied'
    reuse = 'blocked' if first_review else ('requires_reextraction' if any(
        row['decision'] == 'sampling_satisfied_reextract' for row in rows) else 'input_roi_preserved')
    return {
        'schema_version': '1.0', 'profile': 'declared_sampling_candidate',
        'decision': decision, 'feature_reuse': reuse,
        'first_failed_checkpoint': first_failed, 'first_unverified_checkpoint': first_unverified,
        'first_review_checkpoint': first_review, 'checkpoints': rows,
        'plan_sha256': hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'),
                                               allow_nan=False).encode('utf-8')).hexdigest(),
        'scope': 'Fidelity to the declared discrete sampling operation and stated ROI support. '
                 'The source and plan are trusted. Correct resampling requires new feature extraction. '
                 'Input ROI preservation does not establish equivalence of all features. '
                 'Only supplied checkpoints are observed; clinical validity is not assessed.',
    }


def render_html(report):
    """Render a standalone report containing only the path-free evidence."""
    escape = lambda value: html.escape(str(value))
    decisions = {
        'blocked': ('Review before proceeding', 'One or more checkpoints failed or could not be evaluated.'),
        'requires_reextraction': ('Sampling verified. Extract features again.',
                                 'The declared operation was reproduced. Previous radiomic values are not approved for reuse.'),
        'input_roi_preserved': ('Input ROI preserved',
                                'Selected input samples are preserved. Feature reuse still needs an applicable feature and configuration contract.'),
    }
    title, explanation = decisions.get(report.get('feature_reuse'), decisions['blocked'])
    body = []
    for row in report.get('checkpoints', []):
        witness = row.get('sampling', {})
        coverage = witness.get('coverage') or {}
        body.append('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in (
            row['checkpoint'], row['decision'].replace('_', ' '),
            witness.get('max_corner_error_mm', 'unavailable'),
            witness.get('max_intensity_error', 'unavailable'),
            witness.get('violating_roi_voxels', 'unavailable'),
            witness.get('ambiguous_roi_voxels', 'unavailable'),
            coverage.get('source_roi_definitely_outside_candidate_fov', 'unavailable'))) + '</tr>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RadAccord | Sampling report</title>
<style>body{font-family:Arial,sans-serif;color:#243047;background:#f5f6f9;margin:0}
main{max-width:1120px;margin:48px auto;padding:0 28px}header{border-bottom:3px solid #5f6f9f;padding-bottom:24px}
.brand{font-size:34px;font-weight:700;color:#5f6f9f;letter-spacing:-1px}.sub{color:#5b6577}
section{background:#fff;padding:26px;margin-top:24px;border:1px solid #e1e5ed;border-radius:10px}
h1{font-size:28px;margin:0 0 12px}h2{font-size:19px}p{line-height:1.6}
.label{font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#5f6f9f;font-weight:bold}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th{text-align:left;background:#f0f2f8}
th,td{padding:12px 10px;border-bottom:1px solid #e1e5ed;vertical-align:top}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f5f6f9;padding:18px}
footer{font-size:12px;color:#647087;margin:24px 0}summary{cursor:pointer;font-weight:bold}
@media print{body{background:#fff}main{margin:0;max-width:none}section{break-inside:avoid}details{display:none}}
</style><main><header><div class="brand">RadAccord</div>
<div class="sub">Declared spatial sampling · Research report</div></header>
<section><p class="label">Decision</p><h1>''' + escape(title) + '</h1><p>' + escape(explanation) + '''</p></section>
<section><h2>Checkpoint evidence</h2><div class="scroll"><table><thead><tr>
<th>Step</th><th>Decision</th><th>Maximum position error (mm)</th><th>Maximum nominal intensity error</th>
<th>Incompatible ROI voxels</th><th>Boundary-indeterminate ROI voxels</th><th>Source ROI centres certainly outside field of view</th>
</tr></thead><tbody>''' + ''.join(body) + '''</tbody></table></div></section>
<section><h2>Interpretation</h2><p>''' + escape(report.get('scope', 'Evaluation unavailable.')) + '''</p>
<p>When review is required, inspect the failed component at the first reported checkpoint. These observations localise a discrepancy; they do not identify its cause.</p></section>
<section><details><summary>Complete evidence and hashes</summary><pre>''' + escape(json.dumps(report, indent=2, allow_nan=False)) + '''</pre></details></section>
<footer>Local, standalone report. No image data, file paths, external scripts or network requests are included.</footer></main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--html', type=Path)
    args = parser.parse_args()
    try:
        report = audit_plan(json.loads(args.plan.read_text(encoding='utf-8')), args.plan.parent)
    except Exception as error:
        report = {'decision': 'unavailable', 'feature_reuse': 'blocked',
                  'error_type': type(error).__name__,
                  'reason': 'The plan could not be evaluated.'}
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8', newline='\n')
    if args.html:
        args.html.write_text(render_html(report), encoding='utf-8', newline='\n')
    print(report['decision'])
    return 0 if report['decision'] == 'sampling_satisfied' else 2 if report['decision'] == 'unavailable' else 1


if __name__ == '__main__':
    raise SystemExit(main())
