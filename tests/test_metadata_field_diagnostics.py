"""Public diagnostics identify actual containers without printing rejected text."""

import unittest

from app_store_assets.metadata import validate_public_metadata
from test_snapshot_export import target


class MetadataFieldDiagnosticsTests(unittest.TestCase):
    def test_release_note_errors_name_their_actual_container(self):
        cases = [
            (target(), {"release_notes": {"en-US": "private\x00text"}}, "release_notes.en-US"),
            (target(), {"release_notes": {"en-US": "x" * 4001}}, "release_notes.en-US"),
            (target(store="google", platform="android", track="production"),
             {"releases": [{"version_codes": ["42"], "notes": {"ko": "private\x00text"}}]},
             "releases[0].notes.ko"),
            (target(store="google", platform="android", track="production"),
             {"releases": [{"version_codes": ["42"], "notes": {"ko": "x" * 501}}]},
             "releases[0].notes.ko"),
        ]
        for identity, fields, expected in cases:
            with self.subTest(path=expected, fields=list(fields)):
                record = dict(schema_version=1, type="metadata-snapshot", target=identity, **fields)
                with self.assertRaises(ValueError) as caught:
                    validate_public_metadata(record, identity)
                message = str(caught.exception)
                self.assertTrue(message.startswith(expected + ":"), message)
                self.assertNotIn("fields.", message)
                self.assertNotIn("private", message)
                self.assertNotIn("x" * 100, message)

    def test_invalid_locale_or_unknown_key_is_not_used_in_diagnostics(self):
        for fields in ({"private\nlocale": {"description": "bad"}},
                       {"en-US": {"private\nkey": "bad"}}):
            with self.subTest(fields=fields), self.assertRaises(ValueError) as caught:
                validate_public_metadata(dict(schema_version=1, type="metadata-snapshot",
                                              target=target(), fields=fields), target())
            self.assertNotIn("private\n", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
