"""Recompute archived decisions without native engines or large image inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'software'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def match_archive_newlines(source, target):
    """Serialize generated line endings like the archive; preserve all other bytes.

    Frozen writers use the host newline. Require a uniform LF or CRLF convention
    and retain the subsequent literal SHA-256 comparison; do not parse, round,
    reorder or otherwise normalize JSON content.
    """
    def convention(data):
        crlf = data.count(b'\r\n')
        if data.count(b'\r') != crlf or (crlf and data.count(b'\n') != crlf):
            raise ValueError('Mixed or bare-CR line endings in a replay artifact')
        return b'\r\n' if crlf else b'\n'

    expected = convention(Path(source).read_bytes())
    generated = Path(target).read_bytes()
    actual = convention(generated)
    if actual != expected:
        Path(target).write_bytes(generated.replace(actual, expected))
    return actual != expected


def main(output):
    from benchmark import evaluate
    from validation_refinement import evaluate as evaluate_refinement
    from output_mutants import evaluate as evaluate_mutants
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    checks = []
    for manifest in ('final_freeze.json', 'refinement_freeze.json'):
        for name, expected in json.loads((ROOT/'software'/'protocol'/manifest).read_text())['sha256'].items():
            if sha(ROOT/'software'/name) != expected: raise ValueError('Frozen content differs: '+name)
    for run in ('development_final', 'heldout', 'refinement'):
        source, target = ROOT/'work'/run, output/run
        target.mkdir()
        for name in ('cases.jsonl', 'pyradiomics.jsonl', 'mirp.jsonl'):
            if (source/name).exists(): shutil.copyfile(source/name, target/name)
        if run == 'refinement':
            evaluate_refinement(target)
            names = ['pyradiomics_refined_decisions.jsonl', 'pyradiomics_refined_summary.json']
        else:
            evaluate(target)
            names = ['decisions.jsonl', 'feature_diagnostics.jsonl', 'summary.json']
            if run == 'development_final':
                evaluate_mutants(target)
                names += ['output_mutants.jsonl', 'output_mutants_summary.json']
        for name in names:
            match_archive_newlines(source/name, target/name)
            identical = sha(source/name) == sha(target/name)
            checks.append({'run':run, 'file':name, 'byte_identical':identical})
            if not identical: raise AssertionError('Reproduced decision artifact differs: '+run+'/'+name)
    result = {'all_byte_identical':all(c['byte_identical'] for c in checks), 'checks':checks,
              'scope':'Archived comparison arithmetic only. No input image regeneration, native extraction or fresh physical witness validation is performed.'}
    (output/'validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('reproduced'))
    main(p.parse_args().output)
