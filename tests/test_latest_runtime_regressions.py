"""Current review regressions use synthetic local inputs only."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import fixture, git, module, write_json


class LatestReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self, "google")

    def test_version_source_works_with_documented_python_minimum(self):
        (self.root / "pubspec.yaml").write_text("version: 1.0+9\n")
        self.profile["targets"]["production"]["version_source"] = {
            "file": "pubspec.yaml"
        }
        write_json(self.root / "store-upload.json", self.profile)
        plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "metadata"
        )
        self.assertEqual(
            plan["payload"]["target"]["version"], {"name": "1.0", "build": "9"}
        )
        self.assertIn("pubspec.yaml", plan["payload"]["inputs"])

    def test_trusted_ancestors_allow_public_inputs_but_private_children_reject(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for ancestor in (".codex/worktrees", "service-account-tools", "deploy.key"):
            with self.subTest(ancestor=ancestor):
                root = Path(temp.name).resolve() / ancestor / "project"
                shutil.copytree(self.root, root)
                plan = module("planning").make_plan(
                    root, "store-upload.json", "production", "metadata"
                )
                self.assertIn("metadata/listing.json", plan["payload"]["inputs"])
                for child in (
                    ".codex/public.txt",
                    "service-account/public.txt",
                    "secret.key",
                ):
                    with self.assertRaisesRegex(ValueError, "private|credential"):
                        module("records").inventory(root, [child])

    def test_fixture_commits_use_reserved_synthetic_identity(self):
        runtime = self.root / self.profile["runtime"]["path"]
        self.assertEqual(
            git(runtime, "log", "-1", "--format=%an <%ae>"),
            "Offline Fixture <fixture@example.invalid>",
        )

    def test_raw_reader_paths_still_reject_private_parent_components(self):
        records = module("records")
        for name in (
            ".env/public.txt",
            "service-account/public.txt",
            ".codex/public.txt",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic private marker")
            for reader in (
                records.read_text,
                records.file_digest,
                records.capture_bytes,
            ):
                with self.subTest(name=name, reader=reader.__name__):
                    with patch.object(
                        records.os,
                        "open",
                        side_effect=AssertionError("read before validation"),
                    ):
                        with self.assertRaisesRegex(ValueError, "private|credential"):
                            reader(path)
