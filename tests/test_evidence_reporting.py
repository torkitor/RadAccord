import json
import unittest
import numpy as np
from radaccord.evidence import array_digest, config_digest, frame_record, overall_status
from radaccord.legacy import Frame
from radaccord.reporting import methods_text, render_html, compare_evidence


class EvidenceTests(unittest.TestCase):
    def test_canonical_endian_and_layout(self):
        values = np.arange(24).reshape(2, 3, 4)
        self.assertEqual(array_digest(values.astype('<f8')), array_digest(values.astype('>f8')))
        self.assertEqual(array_digest(values), array_digest(np.asfortranarray(values)))
        self.assertNotEqual(array_digest(values), array_digest(values+1))

    def test_source_geometry_and_roi_bindings_change_independently(self):
        image = np.arange(27.).reshape((3, 3, 3)); mask = np.ones(image.shape, dtype=int)
        first = frame_record(Frame(image, mask, np.eye(4)))
        affine = np.eye(4); affine[0, 3] = .1
        second = frame_record(Frame(image, mask, affine))
        self.assertEqual(first['image_sha256'], second['image_sha256'])
        self.assertNotEqual(first['frame_sha256'], second['frame_sha256'])

    def test_failure_report_does_not_invent_execution_or_provenance(self):
        text = methods_text({'profile': 'native_adapter_unavailable', 'status': 'unavailable'})
        self.assertIn('could not be evaluated', text)
        self.assertNotIn('determined before', text)
        self.assertNotIn('binds the source', text)

    def test_report_escapes_every_untrusted_field(self):
        report = {'status': '<script>alert(1)</script>', 'engine': {'name': '<svg/onload=alert(1)>'},
                  'checkpoints': [{'checkpoint': '<img src=x onerror=alert(1)>', 'status': 'unavailable'}]}
        rendered = render_html(report)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<svg/', rendered)
        self.assertIn('&lt;img', rendered)
        self.assertIn("default-src 'none'", rendered)

    def test_changes_require_fresh_evidence(self):
        old = {'configuration_sha256': 'first', 'status': 'satisfied'}
        new = {'configuration_sha256': 'second', 'status': 'violated'}
        result = compare_evidence(old, new)
        self.assertEqual(result['changed_evidence_fields'], ['configuration_sha256'])
        self.assertEqual(result['current_status'], 'violated')
        self.assertEqual(overall_status([{'status': 'indeterminate'}, {'status': 'violated'}]), 'violated')


if __name__ == '__main__':
    unittest.main()
