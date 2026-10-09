import contextlib
import io
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import ROOT, fixture, module, write_json


class OfflineCLITests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.cli = module("cli")

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

    def test_doctor_and_plan_create_no_outputs_and_report_local_scope(self):
        before = set(self.root.rglob("*"))
        for command in ("doctor", "plan"):
            code, out, err = self.call(command, "--operation", "metadata")
            self.assertEqual(code, 0, err)
            result = json.loads(out)
            result = result.get("payload", result)
            self.assertEqual(result["effects"], [])
            self.assertIs(result["remote_verified"], False)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_no_effect_modules_are_distributed_or_loaded(self):
        self.call("doctor")
        for name in (
            "commands",
            "providers",
            "provider_python",
            "provider_ruby",
            "generation",
            "builds",
            "execution",
        ):
            self.assertFalse((ROOT / "app_store_assets" / f"{name}.py").exists())
            self.assertNotIn("app_store_assets." + name, sys.modules)
        self.assertFalse(hasattr(module("metadata"), "download_snapshot"))

    def test_unsupported_commands_and_credential_flags_rejected_before_profile_read(
        self,
    ):
        with patch.object(
            module("planning"),
            "load_profile",
            side_effect=AssertionError("profile touched"),
        ):
            for command in (
                "execute",
                "download",
                "generate",
                "regenerate",
                "build",
                "verify",
            ):
                with self.assertRaises(SystemExit) as error:
                    self.call(command)
                self.assertEqual(error.exception.code, 2)
            with self.assertRaises(SystemExit):
                self.call("doctor", "--auth-file", "private.json")

    def test_dry_run_import_validates_but_writes_nothing(self):
        target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        snapshot = module("snapshots").publish_snapshot(
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

    def test_dry_run_export_and_plan_fail_on_invalid_inputs(self):
        code, out, err = self.call(
            "export", "--source", "missing", "--output", "output", "--dry-run"
        )
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "output").exists())
        self.profile["targets"]["production"].pop("metadata")
        write_json(self.root / "store-upload.json", self.profile)
        code, out, err = self.call("plan", "--operation", "metadata", "--dry-run")
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "build").exists())

    def test_local_staging_module_has_no_executor_dependency(self):
        stage = module("staging")
        expected = module("records").inventory(self.root, ["helpers"])
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        destination = Path(temp.name) / "staged"
        stage.stage_inventory(self.root, destination, expected)
        self.assertEqual(
            module("records").inventory(destination, ["helpers"]), expected
        )
        (self.root / "helpers/source.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed|staging"):
            stage.stage_inventory(self.root, Path(temp.name) / "second-stage", expected)

    def test_staging_cannot_write_inside_source(self):
        with self.assertRaisesRegex(ValueError, "overlap|source"):
            module("staging").stage_inventory(
                self.root,
                self.root / "helpers/new-stage",
                module("records").inventory(self.root, ["helpers"]),
            )
