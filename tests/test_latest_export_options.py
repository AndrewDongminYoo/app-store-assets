"""Export must reject import-only options before public reads or writes."""

import contextlib
import hashlib
import io
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class ExportOptionRegressions(unittest.TestCase):
    def setUp(self):
        self.root, profile = fixture(self)
        target = module("profiles").target_identity(profile["targets"]["production"])
        data = png()
        record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": target,
            "fields": {"en-US": {"description": "Public text"}},
            "images": {
                "en-US": {
                    "APP_IPHONE_65": [
                        {
                            "file": "image.png",
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    ]
                }
            },
        }
        self.snapshot = snapshot_fixture(
            self.root / "history", record, {"image.png": data}
        )

    def call(self, *flags, source=None, output="editing"):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module("write_cli").main(
                [
                    "export",
                    "--root",
                    str(self.root),
                    "--target",
                    "production",
                    "--source",
                    source or self.snapshot.relative_to(self.root).as_posix(),
                    "--output",
                    output,
                    *flags,
                ]
            )
        return code, out.getvalue(), err.getvalue()

    def test_export_metadata_only_rejects_before_reads_and_preserves_source(self):
        cli = module("write_cli")
        before = module("records").tree_inventory(self.snapshot)
        for source in (None, "missing"):
            for dry_run in (False, True):
                with self.subTest(source=source, dry_run=dry_run):
                    flags = ["--metadata-only", *(["--dry-run"] if dry_run else [])]
                    output = "editing-" + str(source) + "-" + str(dry_run)
                    with patch.object(
                        cli, "local_context", wraps=cli.local_context
                    ) as context:
                        code, out, err = self.call(*flags, source=source, output=output)
                    self.assertEqual(code, 2, err)
                    self.assertEqual(out, "")
                    self.assertIn("--metadata-only is only supported for import", err)
                    context.assert_not_called()
                    self.assertFalse((self.root / output).exists())
                    self.assertEqual(
                        module("records").tree_inventory(self.snapshot), before
                    )

    def test_normal_export_still_copies_images(self):
        code, out, err = self.call()
        self.assertEqual(code, 0, err)
        images = list((self.root / "editing").rglob("*.png"))
        self.assertEqual(len(images), 1)
        self.assertEqual(
            images[0].read_bytes(), (self.snapshot / "image.png").read_bytes()
        )
