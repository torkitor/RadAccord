"""Archive-only verification never weakens the default rc2 identity check."""
from pathlib import Path
import shutil
import tempfile
import unittest
from zipfile import ZipFile

from scripts import verify_native_freeze as checker


class NativeFreezeModeTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        (self.root/'data').mkdir()
        (self.root/'protocol').mkdir()
        for name, pointer in [('RadAccord-native-calibration-1', 'native_freeze.json'),
                              ('RadAccord-native-refinement-2', 'native_refinement_freeze.json')]:
            source = checker.ROOT/'data'/(name+'.zip')
            shutil.copyfile(source, self.root/'data'/source.name)
            with ZipFile(source) as archive:
                (self.root/'protocol'/pointer).write_bytes(archive.read(name+'/protocol/'+pointer))
                if name.endswith('refinement-2'):
                    for relative in checker.SCIENTIFIC_FILES:
                        target = self.root/relative
                        target.parent.mkdir(exist_ok=True)
                        target.write_bytes(archive.read(name+'/'+relative))

    def test_default_verifies_rc2_sources_and_explicit_mode_verifies_archives_only(self):
        strict = checker.verify(self.root)
        archived = checker.verify(self.root, archives_only=True)
        self.assertEqual(strict['active_scientific_files_verified'], 7)
        self.assertEqual(archived['active_scientific_files_verified'], 0)
        self.assertEqual(archived['active_scientific_files'], {})
        self.assertEqual(archived['mode'], 'archives_only')
        self.assertTrue(archived['retained_provenance_pointers_verified'])
        self.assertEqual(archived['calibration'], strict['calibration'])
        self.assertEqual(archived['refinement'], strict['refinement'])

    def test_changed_active_source_is_not_silently_accepted_by_default(self):
        (self.root/'radaccord/operators.py').write_bytes(b'# synthetic changed implementation\n')
        with self.assertRaisesRegex(ValueError, 'scientific source differs'):
            checker.verify(self.root)
        self.assertEqual(checker.verify(self.root, archives_only=True)['status'], 'passed')

    def test_archive_only_still_rejects_archive_and_pointer_tampering(self):
        pointer = self.root/'protocol/native_freeze.json'
        original = pointer.read_bytes()
        pointer.write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError, 'provenance pointer differs'):
            checker.verify(self.root, archives_only=True)
        pointer.write_bytes(original)
        archive = self.root/'data/RadAccord-native-refinement-2.zip'
        with archive.open('ab') as stream:
            stream.write(b'tamper')
        with self.assertRaisesRegex(ValueError, 'archive hash differs'):
            checker.verify(self.root, archives_only=True)


if __name__ == '__main__':
    unittest.main()
