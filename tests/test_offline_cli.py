import contextlib
import io
import json
import socket
import subprocess
import sys
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

    def test_dry_run_plan_fails_on_invalid_inputs(self):
        self.profile["targets"]["production"].pop("metadata")
        write_json(self.root / "store-upload.json", self.profile)
        code, out, err = self.call("plan", "--operation", "metadata", "--dry-run")
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "build").exists())
