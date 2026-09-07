"""Regression checks for strict archived replay across platform line endings."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve()
SCRIPT = HERE.parents[2] / 'reproduce_archived.py'
SPEC = importlib.util.spec_from_file_location('replay_under_test', SCRIPT)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class ArchivedReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / 'source.jsonl'
        self.target = Path(self.directory.name) / 'target.jsonl'

    def compare(self, archived, generated):
        self.source.write_bytes(archived)
        self.target.write_bytes(generated)
        changed = replay.match_archive_newlines(self.source, self.target)
        self.assertEqual(self.source.read_bytes(), archived)
        return replay.sha(self.source) == replay.sha(self.target), changed

    def test_both_platform_directions_and_unchanged_output(self):
        content = b'{"value": 1.2345678901234567}\n{"status": "satisfied"}\n'
        for archived_eol in (b'\n', b'\r\n'):
            for generated_eol in (b'\n', b'\r\n'):
                with self.subTest(archived=archived_eol, generated=generated_eol):
                    archived = content.replace(b'\n', archived_eol)
                    generated = content.replace(b'\n', generated_eol)
                    identical, changed = self.compare(archived, generated)
                    self.assertTrue(identical)
                    self.assertEqual(changed, archived_eol != generated_eol)
                    self.assertEqual(self.target.read_bytes(), archived)

    def test_numeric_tampering_is_not_tolerated(self):
        archived = b'{"value": 1.2345678901234567}\r\n'
        generated = b'{"value": 1.2345678901234568}\n'
        self.assertFalse(self.compare(archived, generated)[0])

    def test_structure_order_whitespace_and_final_terminator_remain_strict(self):
        archived = b'{"a": 1, "b": 2}\r\n'
        for generated in (b'{"b": 2, "a": 1}\n', b'{"a": 1}\n',
                          b'{"a":1, "b": 2}\n', b'{"a": 1, "b": 2}',
                          b'{"a": 1, "b": 2}\n\n'):
            with self.subTest(generated=generated):
                self.assertFalse(self.compare(archived, generated)[0])

    def test_escaped_json_newline_is_preserved(self):
        archived = b'{"label": "line\\nnext\\r\\nlast"}\r\n'
        self.assertTrue(self.compare(archived, archived.replace(b'\r\n', b'\n'))[0])

    def test_mixed_and_bare_cr_are_rejected_without_rewriting(self):
        good = b'{"a": 1}\n{"b": 2}\n'
        for bad in (b'{"a": 1}\r\n{"b": 2}\n', b'{"a": 1}\r'):
            for archived, generated in ((bad, good), (good, bad)):
                with self.subTest(archived=archived, generated=generated):
                    self.source.write_bytes(archived)
                    self.target.write_bytes(generated)
                    with self.assertRaises(ValueError):
                        replay.match_archive_newlines(self.source, self.target)
                    self.assertEqual(self.source.read_bytes(), archived)
                    self.assertEqual(self.target.read_bytes(), generated)

    def test_single_line_and_empty_payloads_are_still_byte_compared(self):
        for content in (b'', b'{"value": 1}'):
            with self.subTest(content=content):
                self.assertEqual(self.compare(content, content), (True, False))
        self.assertFalse(self.compare(b'{"value": 1}', b'')[0])


if __name__ == '__main__':
    unittest.main()
