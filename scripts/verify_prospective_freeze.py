"""Verify the declared files of the prospective native validation freeze."""
import argparse
import hashlib
import json
from pathlib import Path
import re

if __package__:
    from .restore_records import file_sha256, relative_parts, safe_file
else:
    from restore_records import file_sha256, relative_parts, safe_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREEZE = 'protocol/prospective_freeze.json'
SCHEMA = 'prospective-validation-1'
PHASE = 'prospective-native-validation-1'
REQUIRED_FILES = (
    'radaccord/evidence.py', 'radaccord/operators.py', 'radaccord/numerics.py',
    'radaccord/mirp.py', 'radaccord/pyradiomics.py',
    'software/physical_contracts.py', 'software/sampling_contracts.py',
    'radaccord/__init__.py', 'pyproject.toml',
    'scripts/run_operational_benchmark.py', 'scripts/build_prospective_plans.py',
    'scripts/prepare_clinical_crops.py', 'protocol/prospective_native_validation.md',
    'protocol/operational_benchmark.md', 'protocol/new_cohort_selection.md',
    'protocol/prospective_environments.json', 'protocol/prospective_host.json',
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key in prospective freeze.')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite JSON constants are not permitted.')


def _reject_link(path):
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Links are not prospective freeze inputs.')


def _bound_file(root, relative):
    if not isinstance(relative, str):
        raise ValueError('Freeze file paths must be strings.')
    parts = relative_parts(relative)
    if parts[0].casefold() == '.git':
        raise ValueError('Git metadata is not a prospective freeze input.')
    current = root
    for part in parts:
        current = current / part
        _reject_link(current)
    path = safe_file(root, relative)
    if not path.is_file():
        raise ValueError('A declared prospective file is missing: '+relative)
    return path


def verify(root=ROOT, freeze=DEFAULT_FREEZE):
    root = Path(root).absolute()
    for ancestor in (root, *root.parents):
        _reject_link(ancestor)
    if not root.is_dir():
        raise ValueError('The prospective root must be an existing directory.')
    root = root.resolve()
    freeze_path = _bound_file(root, freeze)
    raw = freeze_path.read_bytes()
    record = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(record, dict) or record.get('schema_version') != SCHEMA or record.get('phase') != PHASE:
        raise ValueError('Unknown prospective freeze schema or phase.')
    files = record.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Prospective freeze files must be a nonempty SHA-256 map.')
    if not set(REQUIRED_FILES).issubset(files):
        raise ValueError('Prospective freeze omits required implementation or protocol files.')
    seen, verified = set(), {}
    for relative, expected in files.items():
        path = _bound_file(root, relative)
        if relative.casefold() in seen or relative.casefold() == freeze.casefold():
            raise ValueError('Duplicate, case-colliding or self-referential freeze path.')
        seen.add(relative.casefold())
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Prospective SHA-256 values must be lowercase hexadecimal strings.')
        actual = file_sha256(path)
        if actual != expected:
            raise ValueError('Prospective frozen file hash differs: '+relative)
        verified[relative] = actual
    return {'status': 'passed', 'schema_version': SCHEMA, 'phase': PHASE,
            'freeze_sha256': hashlib.sha256(raw).hexdigest(),
            'required_files_verified': len(REQUIRED_FILES),
            'files_verified': len(verified), 'files': dict(sorted(verified.items())),
            'scope': 'Identity of the files declared in this prospective freeze. '
                     'No claim of clinical validity, completed evaluation or remote CI success.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--freeze', default=DEFAULT_FREEZE,
                        help='Canonical relative POSIX path within --root.')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, args.freeze), indent=2, sort_keys=True))
    except (ValueError, OSError) as error:
        parser.exit(1, 'Prospective freeze verification failed: '+str(error)+'\n')
