"""U2: bound authority and checked bytes, with no provider or network calls."""

import copy
import hashlib
import importlib
import importlib.util
import io
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from offline_support import ROOT, fixture, module, write_json
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class TransferApprovalTests(unittest.TestCase):
    def setUp(self):
        name = "app_store_assets_local.transfer"
        self.assertIsNotNone(
            importlib.util.find_spec(name), "U2 transfer verifier is unavailable"
        )
        self.transfer = importlib.import_module(name)
        self.root, self.profile = fixture(self)
        self.target = self.profile["targets"]["production"]
        identity = module("profiles").target_identity(self.target)
        self.images = {"en-US/01.png": png(), "ko/01.png": png(2048, 2732)}
        entries = [
            {
                "file": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "locale": locale,
                "slot": slot,
            }
            for (name, data), locale, slot in zip(
                self.images.items(),
                ("en-US", "ko"),
                ("APP_IPHONE_65", "APP_IPAD_PRO_3GEN_129"),
                strict=False,
            )
        ]
        assets = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": identity,
            "assets": entries,
            "provenance": {"status": "unverified-import"},
        }
        directory = snapshot_fixture(self.root / "state/assets", assets, self.images)
        self.listing = {
            "schema_version": 1,
            "type": "metadata",
            "target": identity,
            "images": {},
        }
        self.source_paths = []
        for entry in entries:
            source = directory / entry["file"]
            self.source_paths.append(source)
            self.listing["images"].setdefault(entry["locale"], {})[entry["slot"]] = [
                {
                    "file": str(source.relative_to(self.root)),
                    "sha256": entry["sha256"],
                }
            ]
        self.target["assets"] = {
            "manifest": str(directory.relative_to(self.root) / "manifest.json")
        }
        self.target["replacement"] = {
            "locales": ["en-US", "ko"],
            "slots": ["APP_IPHONE_65", "APP_IPAD_PRO_3GEN_129"],
            "allow_delete": False,
        }
        write_json(self.root / "metadata/listing.json", self.listing)
        write_json(self.root / "store-upload.json", self.profile)
        remote = json.loads((self.root / "remote.json").read_text())
        remote["fields"]["ko"] = {"description": "Available locale"}
        write_json(self.root / "remote.json", remote)
        self.plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "images"
        )
        self.approval = {
            "schema_version": 1,
            "type": "transfer-approval",
            "plan_digest": self.plan["digest"],
            "target": identity,
            "operation": "images",
        }
        write_json(self.root / "plan.json", self.plan)
        write_json(self.root / "approval.json", self.approval)
        temporary = tempfile.TemporaryDirectory(prefix="transfer-stage-")
        self.addCleanup(temporary.cleanup)
        self.stage = Path(temporary.name).resolve()

    def run_stage(self, **changes):
        options = dict(
            root=self.root,
            plan_path="plan.json",
            approval_path="approval.json",
            staging_dir=self.stage,
        )
        options.update(changes)
        with patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ):
            return self.transfer.stage_transfer(**options)

    def test_invariants_1_and_2_stage_exact_bytes_and_actual_group_pairs(self):
        before = set(self.root.rglob("*"))
        result = self.run_stage()
        self.assertEqual(result["plan_digest"], self.plan["digest"])
        self.assertEqual(result["target"], self.approval["target"])
        self.assertEqual(
            [(g["locale"], g["slot"]) for g in result["groups"]],
            [("en-US", "APP_IPHONE_65"), ("ko", "APP_IPAD_PRO_3GEN_129")],
        )
        for group, data in zip(result["groups"], self.images.values(), strict=False):
            image = group["images"][0]
            staged = Path(image["staged_path"])
            self.assertEqual(staged.parent, self.stage)
            self.assertEqual(staged.read_bytes(), data)
            self.assertEqual(image["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(image["md5"], hashlib.md5(data).hexdigest())
            self.assertEqual(staged.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["provenance"], {"status": "unverified-import"})
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertIs(self.plan["payload"]["executable"], False)
        self.assertEqual(self.plan["payload"]["effects"], [])

    def test_invariant_1_rejects_every_approval_mismatch(self):
        cases = [
            (dict(self.approval, plan_digest="0" * 64), "approval plan digest"),
            (
                dict(
                    self.approval, target=dict(self.approval["target"], flavor="other")
                ),
                "approval target",
            ),
            (
                dict(
                    self.approval,
                    target={
                        k: v
                        for k, v in self.approval["target"].items()
                        if k != "account_id"
                    },
                ),
                "approval target",
            ),
            (dict(self.approval, operation="metadata"), "approval operation"),
            (dict(self.approval, token="must-not-appear"), "approval.*keys"),
            (dict(self.approval, schema_version=True), "approval schema"),
        ]
        for approval, message in cases:
            with self.subTest(message=message):
                write_json(self.root / "approval.json", approval)
                with self.assertRaisesRegex(ValueError, message) as caught:
                    self.run_stage()
                self.assertNotIn("must-not-appear", str(caught.exception))
                self.assertEqual(list(self.stage.iterdir()), [])

    def test_invariant_1_requires_a_current_rederived_plan(self):
        (self.root / "helpers/source.txt").write_text("changed input")
        with self.assertRaisesRegex(ValueError, "plan differs"):
            self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_invariant_1_rejects_forged_plan_payload(self):
        plan = copy.deepcopy(self.plan)
        plan["payload"]["executable"] = True
        write_json(self.root / "plan.json", plan)
        with self.assertRaisesRegex(ValueError, "plan digest"):
            self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_invariant_1_rejects_private_and_symlink_approval_paths(self):
        write_json(self.root / "credentials.json", self.approval)
        (self.root / "approval-link.json").symlink_to(self.root / "approval.json")
        for name, message in (
            ("credentials.json", "credential"),
            ("approval-link.json", "symlink"),
        ):
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, message):
                self.run_stage(approval_path=name)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_invariant_2_checks_even_the_last_group_after_plan_verification(self):
        verify = self.transfer.verify_plan

        def change_after_verification(*args):
            verify(*args)
            self.source_paths[-1].write_bytes(b"changed after planning")

        with patch.object(
            self.transfer, "verify_plan", side_effect=change_after_verification
        ):
            with self.assertRaisesRegex(ValueError, "image SHA-256"):
                self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_invariant_2_never_reopens_source_bytes_after_capture(self):
        capture = self.transfer.capture_bytes
        calls = []

        def replace_after_capture(path, **kwargs):
            data = capture(path, **kwargs)
            calls.append(Path(path))
            Path(path).write_bytes(b"replacement bytes")
            return data

        with patch.object(
            self.transfer, "capture_bytes", side_effect=replace_after_capture
        ):
            result = self.run_stage()
        self.assertEqual(calls, self.source_paths)
        for group, expected in zip(
            result["groups"], self.images.values(), strict=False
        ):
            self.assertEqual(
                Path(group["images"][0]["staged_path"]).read_bytes(), expected
            )

    def test_staging_rejects_nonprivate_nonempty_or_project_directories(self):
        self.stage.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "private"):
            self.run_stage()
        self.stage.chmod(0o700)
        (self.stage / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_stage()
        self.assertEqual((self.stage / "keep.txt").read_text(), "keep")
        internal = self.root / "stage"
        internal.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.run_stage(staging_dir=internal)
        self.assertEqual(list(internal.iterdir()), [])

    def test_staging_total_bound_cleans_earlier_files(self):
        with patch.object(
            self.transfer, "FILE_LIMIT", sum(map(len, self.images.values())) - 1
        ):
            with self.assertRaisesRegex(ValueError, "bound"):
                self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_staging_parent_traversal_cannot_enter_the_project(self):
        internal = self.root / "stage"
        internal.mkdir(mode=0o700)
        detour = self.root.parent / (self.root.name + "-detour")
        detour.mkdir()
        self.addCleanup(detour.rmdir)
        path = detour / ".." / self.root.name / "stage"
        with self.assertRaisesRegex(ValueError, "canonical|outside|traversal"):
            self.run_stage(staging_dir=path)
        self.assertEqual(list(internal.iterdir()), [])

    def test_staging_symlinks_are_not_followed(self):
        link = self.stage.parent / (self.stage.name + "-link")
        link.symlink_to(self.stage, target_is_directory=True)
        self.addCleanup(link.unlink)
        with self.assertRaises((ValueError, OSError)):
            self.run_stage(staging_dir=link)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_approval_changed_during_staging_discards_all_staged_files(self):
        capture = self.transfer.capture_bytes

        def change_approval(path, **kwargs):
            data = capture(path, **kwargs)
            write_json(
                self.root / "approval.json", dict(self.approval, plan_digest="0" * 64)
            )
            return data

        with patch.object(self.transfer, "capture_bytes", side_effect=change_approval):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_staging_directory_replacement_is_refused_and_original_is_cleaned(self):
        capture = self.transfer.capture_bytes
        original = self.stage
        moved = original.parent / (original.name + "-moved")
        self.addCleanup(lambda: moved.rmdir() if moved.exists() else None)
        swapped = False

        def swap_directory(path, **kwargs):
            nonlocal swapped
            data = capture(path, **kwargs)
            if not swapped:
                original.rename(moved)
                original.mkdir(mode=0o700)
                (original / "keep.txt").write_text("keep")
                swapped = True
            return data

        with patch.object(self.transfer, "capture_bytes", side_effect=swap_directory):
            with self.assertRaisesRegex(ValueError, "staging directory changed"):
                self.run_stage()
        self.assertEqual(list(moved.iterdir()), [])
        self.assertEqual((original / "keep.txt").read_text(), "keep")

    def test_oversized_intent_discards_staged_files(self):
        with patch.object(self.transfer, "TEXT_LIMIT", 1):
            with self.assertRaisesRegex(ValueError, "JSON.*bound"):
                self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_staged_child_replacement_is_refused_without_deleting_replacement(self):
        capture = self.transfer.capture_bytes
        replacement = self.stage / "000000.png"

        def replace_first(path, **kwargs):
            data = capture(path, **kwargs)
            if replacement.exists():
                replacement.rename(self.stage / "retained-original.png")
                replacement.write_bytes(b"belongs to another writer")
            return data

        with patch.object(self.transfer, "capture_bytes", side_effect=replace_first):
            with self.assertRaisesRegex(ValueError, "staged file changed"):
                self.run_stage()
        self.assertEqual(replacement.read_bytes(), b"belongs to another writer")
        self.assertFalse((self.stage / "000001.png").exists())

    def test_staged_bytes_modified_in_place_are_refused(self):
        capture = self.transfer.capture_bytes

        def overwrite_first(path, **kwargs):
            data = capture(path, **kwargs)
            first = self.stage / "000000.png"
            if first.exists():
                first.write_bytes(b"changed")
            return data

        with patch.object(self.transfer, "capture_bytes", side_effect=overwrite_first):
            with self.assertRaisesRegex(ValueError, "staged file changed"):
                self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_stdout_limit_bounds_the_exact_encoding_and_newline(self):
        result = self.run_stage()
        for image in self.stage.iterdir():
            image.unlink()
        size = len(self.transfer.canonical(result)) + 1
        output = io.StringIO()
        with patch.object(self.transfer, "TEXT_LIMIT", size), redirect_stdout(output):
            code = self.transfer.main(
                [
                    "--root",
                    str(self.root),
                    "--plan",
                    "plan.json",
                    "--approval",
                    "approval.json",
                    "--staging-dir",
                    str(self.stage),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(len(output.getvalue().encode()), size)
        for image in self.stage.iterdir():
            image.unlink()
        with patch.object(self.transfer, "TEXT_LIMIT", size - 1):
            with self.assertRaisesRegex(ValueError, "JSON.*bound"):
                self.run_stage()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_cli_outputs_one_json_intent(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "app_store_assets_local.transfer",
                "--root",
                str(self.root),
                "--plan",
                "plan.json",
                "--approval",
                "approval.json",
                "--staging-dir",
                str(self.stage),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["plan_digest"], self.plan["digest"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
