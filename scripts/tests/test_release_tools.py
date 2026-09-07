"""Boundary tests for release integrity and selective record restoration."""
import hashlib
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_release
import restore_records


def manifest(files):
    return ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items()))


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='radaccord_release_test_')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()

    def release(self, files):
        for name, data in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (self.root / 'MANIFEST.sha256').write_text(manifest(files), encoding='utf-8')

    def archive(self, extra=None):
        files = {'work/run/records.jsonl': b'{"result":1}\n',
                 'work/run/more.jsonl': b'{"result":2}\n',
                 'work/run/summary.json': b'{"count":2}\n',
                 'software/unchanged.py': b'original = True\n'}
        target = self.root / restore_records.ARCHIVE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(target, 'w') as archive:
            for name, data in files.items():
                archive.writestr('RadAccord/' + name, data)
            archive.writestr('RadAccord/MANIFEST.sha256', manifest(files))
            if extra is not None:
                archive.writestr(*extra)
        self.release({restore_records.ARCHIVE_PATH: target.read_bytes()})
        pin = patch.object(restore_records, 'ARCHIVE_SHA256', restore_records.file_sha256(target))
        pin.start()
        self.addCleanup(pin.stop)
        return files

    def test_listed_bytes_pass_and_unlisted_public_file_fails(self):
        self.release({'docs/note.txt': b'content\n'})
        self.assertEqual(check_release.verify(self.root)['manifest_files_verified'], 1)
        (self.root / 'unlisted.txt').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'Unlisted public'):
            check_release.verify(self.root)

    def test_missing_and_modified_files_fail(self):
        self.release({'note.txt': b'expected'})
        target = self.root / 'note.txt'
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            check_release.verify(self.root)
        target.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum differs'):
            check_release.verify(self.root)

    def test_canonical_paths_are_required_on_every_platform(self):
        for name in ('../outside', '/absolute', 'C:/drive', 'a\\b', 'a//b', './file', 'a/../b', 'bad\tname',
                     'CON', 'folder/nul.txt', 'name.', 'name ', 'a?b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                restore_records.parse_manifest('0' * 64 + '  ' + name + '\n')

    def test_duplicates_case_collisions_and_empty_manifest_fail(self):
        for text in ('', 'not a digest\n', '0' * 64 + '  a\n' + '1' * 64 + '  a\n',
                     '0' * 64 + '  A\n' + '1' * 64 + '  a\n',
                     '0' * 64 + '  MANIFEST.sha256\n', '0' * 64 + '  .git/config\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                restore_records.parse_manifest(text)

    def test_local_outputs_do_not_become_public_extras(self):
        self.release({'note.txt': b'expected'})
        for name in ('.git/config', '__pycache__/cache.pyc', 'software/__pycache__/cache.pyc',
                     'outputs/report.json', 'reproduced/report.json', 'generated_inputs/image.nii',
                     'reports/report.json', '.venv-test/pyvenv.cfg', 'venv/pyvenv.cfg',
                     'software/runs/log.txt', 'work/pilot/inputs/volume.nii', 'figures/P2_Fig1.png'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('local')
        self.assertEqual(check_release.verify(self.root)['unlisted_public_files'], 0)

    def test_only_jsonl_records_restore_and_second_run_is_idempotent(self):
        files = self.archive()
        first = restore_records.restore(self.root)
        self.assertEqual((first['restored'], first['already_present']), (2, 0))
        self.assertFalse((self.root / 'software').exists())
        self.assertFalse((self.root / 'work/run/summary.json').exists())
        for name in ('work/run/records.jsonl', 'work/run/more.jsonl'):
            self.assertEqual((self.root / name).read_bytes(), files[name])
        second = restore_records.restore(self.root)
        self.assertEqual((second['restored'], second['already_present']), (0, 2))
        self.assertEqual(check_release.verify(self.root)['restored_records_verified'], 2)

    def test_conflicting_existing_record_stops_before_any_extraction(self):
        self.archive()
        target = self.root / 'work/run/records.jsonl'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'user content')
        with self.assertRaisesRegex(ValueError, 'nothing was overwritten'):
            restore_records.restore(self.root)
        self.assertEqual(target.read_bytes(), b'user content')
        self.assertFalse((self.root / 'work/run/more.jsonl').exists())

    def test_archive_pin_is_checked(self):
        self.archive()
        with patch.object(restore_records, 'ARCHIVE_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
                restore_records.restore(self.root)

    def test_archive_traversal_is_rejected_without_writing(self):
        self.archive(('RadAccord/../escape.jsonl', b'bad'))
        with self.assertRaises(ValueError):
            restore_records.restore(self.root)
        self.assertFalse((self.root / 'work').exists())
        self.assertFalse((self.root / 'escape.jsonl').exists())

    def test_archive_symlink_is_rejected(self):
        member = ZipInfo('RadAccord/work/link.jsonl')
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.archive((member, b'../../outside'))
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            restore_records.restore(self.root)

    def test_modified_or_unknown_restored_record_fails_release_check(self):
        self.archive()
        restore_records.restore(self.root)
        target = self.root / 'work/run/records.jsonl'
        target.write_bytes(b'modified')
        with self.assertRaisesRegex(ValueError, 'Restored record checksum'):
            check_release.verify(self.root)
        target.write_bytes(b'{"result":1}\n')
        (self.root / 'work/run/unknown.jsonl').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Unlisted public'):
            check_release.verify(self.root)

    def test_filesystem_symlink_is_not_followed(self):
        self.release({'note.txt': b'expected'})
        link = self.root / 'link.txt'
        try:
            link.symlink_to(self.root / 'note.txt')
        except OSError:
            self.skipTest('Filesystem symlink creation is unavailable for this account.')
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            restore_records.safe_file(self.root, 'link.txt')


if __name__ == '__main__':
    unittest.main()
