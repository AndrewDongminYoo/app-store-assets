import contextlib
import io
import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import fixture, module


class OfflineCLITests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.cli = module("write_cli")

    def call(self, command, *extra):
        out = io.StringIO()
        err = io.StringIO()
        actual = subprocess.run

        def local_only(argv, *a, **k):
            if not isinstance(argv, list) or Path(argv[0]).name not in (
                "git",
                "magick",
            ):
                raise AssertionError("forbidden subprocess")
            return actual(argv, *a, **k)

        with (
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network forbidden"),
            ),
            patch.object(subprocess, "run", side_effect=local_only),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = self.cli.main(
                [command, "--root", str(self.root), "--target", "production", *extra]
            )
        return (code, out.getvalue(), err.getvalue())

    def test_dry_run_import_validates_but_writes_nothing(self):
        target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        snapshot = module("publisher").publish_snapshot(
            self.root / "history",
            {
                "schema_version": 1,
                "type": "metadata-snapshot",
                "target": target,
                "fields": {"en-US": {"description": "public"}},
                "images": {},
            },
            {},
        )
        module("metadata_io").export_metadata(self.root, snapshot, target, "editing")
        before = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        code, out, err = self.call(
            "import", "--source", "editing", "--output", "new-listing.json", "--dry-run"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["status"], "dry-run")
        after = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(after, before)
        (self.root / "editing/en-US/description.txt").write_text("x" * 4001)
        code, out, err = self.call(
            "import", "--source", "editing", "--output", "new-listing.json", "--dry-run"
        )
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "new-listing.json").exists())

    def test_dry_run_export_fails_on_invalid_inputs(self):
        code, out, err = self.call(
            "export", "--source", "missing", "--output", "output", "--dry-run"
        )
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "output").exists())

    def test_local_staging_module_has_no_executor_dependency(self):
        stage = module("staging")
        expected = module("records").inventory(self.root, ["helpers"])
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        destination = Path(temp.name).resolve() / "staged"
        stage.stage_inventory(self.root, destination, expected)
        self.assertEqual(
            module("records").inventory(destination, ["helpers"]), expected
        )
        (self.root / "helpers/source.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed|staging"):
            stage.stage_inventory(
                self.root, Path(temp.name).resolve() / "second-stage", expected
            )

    def test_staging_cannot_write_inside_source(self):
        with self.assertRaisesRegex(ValueError, "overlap|source"):
            module("staging").stage_inventory(
                self.root,
                self.root / "helpers/new-stage",
                module("records").inventory(self.root, ["helpers"]),
            )
