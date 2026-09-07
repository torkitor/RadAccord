"""Restore archived JSONL study records from the bundled, hash-pinned release."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
from zipfile import ZipFile

ARCHIVE_SHA256 = '43ff30b546e1904b1f119c6349747d3e6289b273f2b4ee18c80dc57d0b2970bd'
ARCHIVE_PATH = 'data/RadAccord-1.0.0.zip'
ROOT = Path(__file__).resolve().parents[1]


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relative_parts(name):
    parts = name.split('/')
    if (not name or any(part in ('', '.', '..') for part in parts)
            or any(char in name for char in '\\:<>"|?*')
            or any(part.endswith((' ', '.')) for part in parts)
            or any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0], re.IGNORECASE)
                   for part in parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError('A canonical relative POSIX path is required.')
    return parts


def safe_file(root, name):
    root = Path(root).resolve()
    parts = relative_parts(name)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'Symlinks are not release files: {name}')
    if not current.resolve().is_relative_to(root):
        raise ValueError(f'Path escapes the release directory: {name}')
    if current.exists() and not stat.S_ISREG(current.stat().st_mode):
        raise ValueError(f'Expected a regular file: {name}')
    return current


def parse_manifest(text):
    records = {}
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
        if not match:
            raise ValueError(f'Invalid SHA-256 manifest line {number}.')
        digest, name = match.groups()
        relative_parts(name)
        if name.casefold() in seen:
            raise ValueError(f'Duplicate or case-colliding manifest path: {name}')
        if name == 'MANIFEST.sha256' or name.split('/')[0] == '.git':
            raise ValueError(f'Forbidden manifest entry: {name}')
        seen.add(name.casefold())
        records[name] = digest.lower()
    if not records:
        raise ValueError('The SHA-256 manifest is empty.')
    return records


def archive_records(root):
    archive = safe_file(root, ARCHIVE_PATH)
    if not archive.is_file() or file_sha256(archive) != ARCHIVE_SHA256:
        raise ValueError('The bundled study archive is missing or its SHA-256 differs.')
    with ZipFile(archive) as package:
        seen = set()
        records = {}
        members = package.infolist()
        for member in members:
            name = member.filename.rstrip('/') if member.is_dir() else member.filename
            parts = relative_parts(name)
            if parts[0] != 'RadAccord' or name.casefold() in seen:
                raise ValueError('Unexpected or duplicate archive path.')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Archive symlinks are not supported.')
            seen.add(name.casefold())
        manifest = parse_manifest(package.read('RadAccord/MANIFEST.sha256').decode('utf-8'))
        for member in members:
            name = member.filename
            if member.is_dir() or not name.startswith('RadAccord/work/') or not name.endswith('.jsonl'):
                continue
            relative = name.removeprefix('RadAccord/')
            if relative not in manifest:
                raise ValueError(f'Archive record has no checksum: {relative}')
            records[relative] = {'member': name, 'sha256': manifest[relative]}
        if not records:
            raise ValueError('The bundled archive contains no study JSONL records.')
    return records


def restore(root=ROOT):
    root = Path(root).resolve()
    records = archive_records(root)
    pending = []
    for name, record in records.items():
        target = safe_file(root, name)
        if target.exists():
            if file_sha256(target) != record['sha256']:
                raise ValueError(f'Existing record differs; nothing was overwritten: {name}')
        else:
            pending.append((target, record))
    with ZipFile(root / ARCHIVE_PATH) as package:
        for target, record in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation also refuses a file that appears after preflight.
            output = target.open('xb')
            try:
                with output, package.open(record['member']) as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if file_sha256(target) != record['sha256']:
                    raise ValueError('Restored record checksum differs.')
            except BaseException:
                target.unlink(missing_ok=True)
                raise
    return {'restored': len(pending), 'already_present': len(records) - len(pending),
            'verified_records': len(records), 'archive_sha256': ARCHIVE_SHA256,
            'scope': 'Only archived work/**/*.jsonl records are restored. No analysis is rerun.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    try:
        print(json.dumps(restore(parser.parse_args().root), indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Record restoration failed: {error}\n')
