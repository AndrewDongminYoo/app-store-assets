"""Write CLI keeps profile/runtime approval bound through final validation."""

import contextlib
import io
import unittest
from unittest.mock import patch

from offline_support import fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


class LocalCLIContextTests(unittest.TestCase):
    def test_changed_profile_or_runtime_before_publication_fails_without_outputs(self):
        for changed in ("profile", "runtime"):
            with self.subTest(changed=changed):
                root, profile = fixture(self)
                target = module("profiles").target_identity(
                    profile["targets"]["production"]
                )
                record = {
                    "schema_version": 1,
                    "type": "metadata-snapshot",
                    "target": target,
                    "fields": {"en-US": {"description": "public"}},
                    "images": {},
                }
                snapshot = snapshot_fixture(root / "history", record)
                module("metadata_io").export_metadata(root, snapshot, target, "editing")
                original = module("metadata_io").inventory

                def mutate(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if changed == "profile":
                        other = dict(profile, project="other-public")
                        write_json(root / "store-upload.json", other)
                    else:
                        (
                            root / "tools/app-store-assets/app_store_assets/__init__.py"
                        ).write_text('"""changed public runtime"""\n')
                    return result

                out = io.StringIO()
                with (
                    patch.object(
                        module("metadata_io"), "inventory", side_effect=mutate
                    ),
                    contextlib.redirect_stdout(out),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    code = module("write_cli").main(
                        [
                            "import",
                            "--root",
                            str(root),
                            "--target",
                            "production",
                            "--source",
                            "editing",
                            "--output",
                            "new.json",
                            "--state",
                            "new-state",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertFalse((root / "new-state").exists())
                self.assertFalse((root / "new.json").exists())
