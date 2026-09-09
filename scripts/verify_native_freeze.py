"""Verify both immutable native studies and their retained scientific implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
from zipfile import ZipFile

if __package__:
    from .restore_records import file_sha256, parse_manifest, relative_parts, safe_file
else:
    from restore_records import file_sha256, parse_manifest, relative_parts, safe_file


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_SHA256 = 'a3e2bff93996884ca8f8c31a38dbe8f1bb75acf2e011509e4d06ca9cbfd1532f'
CALIBRATION_FREEZE_SHA256 = '258e66217f03a138c7dfe07b2b16200670955d6a10f93559759cbca0d355c55b'
REFINEMENT_ARCHIVE_SHA256 = 'd8780b56b63c50e75631fa63ac0cb68874c60357d9ceb8828cf3d47b27ce6bb5'
REFINEMENT_FREEZE_SHA256 = '8a99094b119db04275251de57f1e2915720b5bad649736e5212fcecadf6a3b4e'
ANALYSIS_SHA256 = 'cef8976136b9a2797e2c753ddf5ef7de0ae5164a895a874c862121eca7b1223e'
SCIENTIFIC_FILES = (
    'radaccord/evidence.py', 'radaccord/operators.py', 'radaccord/numerics.py',
    'radaccord/mirp.py', 'radaccord/pyradiomics.py',
    'software/physical_contracts.py', 'software/sampling_contracts.py',
)


def _bytes_sha(value):
    return hashlib.sha256(value).hexdigest()


def _archive(root, name, archive_sha, freeze_path, freeze_sha, frozen_count):
    path = safe_file(root, 'data/'+name+'.zip')
    if file_sha256(path) != archive_sha:
        raise ValueError('Immutable native archive hash differs: '+name)
    prefix = name+'/'
    with ZipFile(path) as archive:
        names, seen = {}, set()
        for member in archive.infolist():
            relative_parts(member.filename)
            if (not member.filename.startswith(prefix) or member.is_dir()
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError('Unexpected archive member type or top-level directory.')
            relative = member.filename[len(prefix):]
            relative_parts(relative)
            if relative.casefold() in seen:
                raise ValueError('Duplicate or case-colliding native archive member.')
            seen.add(relative.casefold())
            names[relative] = member.filename
        manifest = parse_manifest(archive.read(names['MANIFEST.sha256']).decode('utf-8'))
        if set(names) != set(manifest) | {'MANIFEST.sha256'}:
            raise ValueError('Native archive members differ from its manifest.')
        payload = {relative: archive.read(names[relative]) for relative in manifest}
        for relative, expected in manifest.items():
            if _bytes_sha(payload[relative]) != expected:
                raise ValueError('Native archive payload hash mismatch: '+relative)
        if _bytes_sha(payload[freeze_path]) != freeze_sha:
            raise ValueError('Native freeze hash differs inside the archive.')
        freeze = json.loads(payload[freeze_path])
        if freeze.get('schema_version') != 'native-freeze-1' or len(freeze.get('files', {})) != frozen_count:
            raise ValueError('Unexpected native freeze schema or file count.')
        for relative, expected in freeze['files'].items():
            if relative not in payload or _bytes_sha(payload[relative]) != expected:
                raise ValueError('Frozen payload differs inside the archive: '+relative)
    if file_sha256(safe_file(root, freeze_path)) != freeze_sha:
        raise ValueError('The retained native provenance pointer differs: '+freeze_path)
    return ({'archive_sha256': archive_sha, 'manifest_payload_files_verified': len(manifest),
             'frozen_files_verified': frozen_count, 'freeze_sha256': freeze_sha,
             'zip_extraction_performed': False}, freeze, payload)


def verify(root):
    root = Path(root).resolve()
    calibration, _, _ = _archive(root, 'RadAccord-native-calibration-1', CALIBRATION_SHA256,
                                 'protocol/native_freeze.json', CALIBRATION_FREEZE_SHA256, 15)
    refinement, freeze, payload = _archive(root, 'RadAccord-native-refinement-2', REFINEMENT_ARCHIVE_SHA256,
                                          'protocol/native_refinement_freeze.json', REFINEMENT_FREEZE_SHA256, 27)
    if (freeze.get('phase') != 'native-refinement-2' or freeze.get('candidate') != '1.2.0rc2'
            or freeze.get('calibration_archive_sha256') != CALIBRATION_SHA256):
        raise ValueError('The refinement phase or calibration archive binding differs.')
    analysis_path = 'protocol/native_refinement_analysis.json'
    if _bytes_sha(payload[analysis_path]) != ANALYSIS_SHA256:
        raise ValueError('The archived analysis compatibility freeze differs.')
    analysis = json.loads(payload[analysis_path])
    if analysis.get('native_freeze_sha256') != REFINEMENT_FREEZE_SHA256:
        raise ValueError('The analysis correction is bound to a different native freeze.')
    for relative, expected in analysis['files'].items():
        if relative not in payload or _bytes_sha(payload[relative]) != expected:
            raise ValueError('The archived analysis compatibility payload differs: '+relative)
    active = {}
    for relative in SCIENTIFIC_FILES:
        actual = file_sha256(safe_file(root, relative))
        if actual != freeze['files'][relative]:
            raise ValueError('Retained scientific source differs from archived rc2: '+relative)
        active[relative] = actual
    return {'status': 'passed', 'calibration': calibration, 'refinement': refinement,
            'analysis_compatibility_sha256': ANALYSIS_SHA256,
            'retained_provenance_pointers_verified': True,
            'active_scientific_files': active, 'active_scientific_files_verified': len(active),
            'scope': ('Archive integrity for both studies and identity of the seven-source union '
                      '(six checking sources per engine). Current CLI/version/packaging files '
                      'are outside this scientific identity check and use the release manifest. '
                      'This does not assert native validity or remote CI success.')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2, sort_keys=True))
