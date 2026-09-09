"""Verify listed release files and reject unlisted public files.

Git metadata, Python caches and local output/virtual-environment directories are
excluded from the extra-file check. Restored study JSONL records are accepted
only when their hashes match the pinned study archive.
"""
import argparse
import json
import os
from pathlib import Path

from restore_records import archive_records, file_sha256, parse_manifest, safe_file

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DIRECTORIES = {'outputs', 'reproduced', 'generated_inputs', 'reports', 'venv',
                     'build', 'dist', 'radaccord.egg-info'}


def ignored(parts, directory=False):
    if parts[0] == '.git' or any(part in {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'} for part in parts):
        return True
    if parts[-1].endswith(('.pyc', '.pyo')):
        return True
    if len(parts) >= 2 and tuple(parts[:2]) == ('software', 'runs'):
        return True
    if parts[0] == 'work' and 'inputs' in (parts[1:] if directory else parts[1:-1]):
        return True
    if len(parts) == 2 and parts[0] == 'figures' and parts[1].startswith('P2_Fig'):
        return True
    return ((directory or len(parts) > 1)
            and (parts[0] in LOCAL_DIRECTORIES or parts[0].startswith('.venv')))


def public_files(root):
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            path = Path(parent) / name
            parts = path.relative_to(root).parts
            if ignored(parts, directory=True):
                directories.remove(name)
            elif path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Linked directories are not supported in the release.')
        for name in files:
            path = Path(parent) / name
            parts = path.relative_to(root).parts
            if not ignored(parts):
                yield path.relative_to(root).as_posix()


def verify(root=ROOT):
    root = Path(root).resolve()
    manifest = safe_file(root, 'MANIFEST.sha256')
    records = parse_manifest(manifest.read_text(encoding='utf-8'))
    for name, expected in records.items():
        path = safe_file(root, name)
        if not path.is_file():
            raise ValueError(f'Missing release file: {name}')
        if file_sha256(path) != expected:
            raise ValueError(f'Release checksum differs: {name}')
    extra = set(public_files(root)) - set(records) - {'MANIFEST.sha256'}
    restored = archive_records(root) if any(name.startswith('work/') and name.endswith('.jsonl') for name in extra) else {}
    for name in sorted(extra):
        if name not in restored:
            raise ValueError(f'Unlisted public file: {name}')
        if file_sha256(safe_file(root, name)) != restored[name]['sha256']:
            raise ValueError(f'Restored record checksum differs: {name}')
    return {'manifest_files_verified': len(records), 'restored_records_verified': len(extra),
            'unlisted_public_files': 0,
            'scope': 'Integrity against supplied checksums; this is not proof of authenticity or scientific validity.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    try:
        print(json.dumps(verify(parser.parse_args().root), indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Release verification failed: {error}\n')
