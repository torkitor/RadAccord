"""Synthetic integrity failures for a prospectively bound file map."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import verify_prospective_freeze as checker


class ProspectiveFreezeTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        (self.root/'protocol').mkdir()
        (self.root/'implementation.py').write_bytes(b'parameter = 1\n')
        self.freeze = {'schema_version': checker.SCHEMA, 'phase': checker.PHASE,
                       'files': {'implementation.py': hashlib.sha256(b'parameter = 1\n').hexdigest()}}
        for relative in checker.REQUIRED_FILES:
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = ('Synthetic integrity fixture: '+relative+'\n').encode()
            path.write_bytes(data)
            self.freeze['files'][relative] = hashlib.sha256(data).hexdigest()
        self.path = self.root/checker.DEFAULT_FREEZE

    def save(self):
        self.path.write_text(json.dumps(self.freeze), encoding='utf-8')

    def test_valid_map_and_changed_or_missing_payload(self):
        self.save()
        result = checker.verify(self.root)
        self.assertEqual(result['files_verified'], len(checker.REQUIRED_FILES)+1)
        self.assertEqual(result['required_files_verified'], len(checker.REQUIRED_FILES))
        self.assertEqual(result['freeze_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        (self.root/'implementation.py').write_bytes(b'parameter = 2\n')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            checker.verify(self.root)
        (self.root/'implementation.py').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            checker.verify(self.root)

    def test_unknown_schema_phase_empty_map_and_invalid_hash(self):
        for key, value in [('schema_version', 'native-freeze-1'), ('phase', 'retrospective'),
                           ('files', {}), ('files', []),
                           ('files', {'implementation.py': 'X'*64}),
                           ('files', {'implementation.py': 123})]:
            previous = self.freeze[key]
            self.freeze[key] = value
            self.save()
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                checker.verify(self.root)
            self.freeze[key] = previous

    def test_duplicate_json_and_case_colliding_paths_are_rejected(self):
        self.save()
        text = self.path.read_text()
        self.path.write_text(text.replace('"phase":', '"phase":"discarded", "phase":'))
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            checker.verify(self.root)
        key = 'implementation.py'
        self.freeze['files']['Implementation.py'] = self.freeze['files'][key]
        (self.root/'Implementation.py').write_bytes(b'parameter = 1\n')
        self.save()
        with self.assertRaisesRegex(ValueError, 'case-colliding'):
            checker.verify(self.root)

    def test_unsafe_paths_and_self_binding_are_rejected(self):
        digest = self.freeze['files']['implementation.py']
        baseline = dict(self.freeze['files'])
        for name in ('../implementation.py', '/absolute', 'C:/drive', 'a\\b', './file',
                     'a//b', 'a/../b', 'a:stream', 'CON', '.git/config', checker.DEFAULT_FREEZE):
            self.freeze['files'] = dict(baseline, **{name: digest})
            self.save()
            with self.subTest(name=name), self.assertRaises(ValueError):
                checker.verify(self.root)
        with self.assertRaises(ValueError):
            checker.verify(self.root, '../freeze.json')

    def test_nonfinite_json_constants_and_nonobject_root_are_rejected(self):
        for text in ('[]', 'null', '{"unused":NaN}', '{"unused":Infinity}'):
            self.path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                checker.verify(self.root)

    def test_symlink_payload_and_parent_are_rejected(self):
        target = self.root/'implementation.py'
        link = self.root/'linked.py'
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('This platform does not permit creating test symlinks.')
        self.freeze['files']['linked.py'] = checker.file_sha256(target)
        self.save()
        with self.assertRaisesRegex(ValueError, 'Links'):
            checker.verify(self.root)
        directory_link = self.root/'linked_directory'
        directory_link.symlink_to(self.root/'protocol', target_is_directory=True)
        self.freeze['files'].pop('linked.py')
        self.freeze['files']['linked_directory/note'] = '0'*64
        self.save()
        with self.assertRaisesRegex(ValueError, 'Links'):
            checker.verify(self.root)

    def test_required_implementation_and_protocol_files_cannot_be_omitted(self):
        for relative in checker.REQUIRED_FILES:
            expected = self.freeze['files'].pop(relative)
            self.save()
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'omits required'):
                checker.verify(self.root)
            self.freeze['files'][relative] = expected


if __name__ == '__main__':
    unittest.main()
