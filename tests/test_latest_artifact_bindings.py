"""Current review regressions use synthetic local inputs only."""

import json
import unittest
from unittest.mock import patch

from offline_support import fixture, git, module, write_json


class LatestReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self, "google")

    def live_build(self):
        (self.root / "adapter-only").mkdir()
        (self.root / "adapter-only/source.txt").write_text("Inspected source\n")
        git(self.root, "init", "-q")
        git(self.root, "add", "adapter-only")
        git(self.root, "commit", "-qm", "Synthetic inspected source")
        record = json.loads((self.root / "artifact.json").read_text())
        record.update(
            evidence="inspected",
            native_guards={"app_id": True},
            source_commit=git(self.root, "rev-parse", "HEAD"),
            source_inputs=module("records").inventory(self.root, ["adapter-only"]),
            inspector="synthetic-inspector",
            adapter={"inputs": ["adapter-only"]},
        )
        write_json(self.root / "artifact.json", record)
        self.profile["mode"] = "live"
        write_json(self.root / "store-upload.json", self.profile)
        return record

    def test_live_adapter_only_sources_enter_final_inventory(self):
        record = self.live_build()
        plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "binary"
        )
        self.assertEqual(
            plan["payload"]["inputs"]["adapter-only/source.txt"],
            record["source_inputs"]["adapter-only/source.txt"],
        )
        self.assertIn("adapter-only", plan["payload"]["input_paths"])

    def test_live_adapter_changes_between_inspection_and_inventory_reject(self):
        self.live_build()
        planning = module("planning")
        actual = planning.inventory
        for name in ("source.txt", "added.txt"):
            with self.subTest(name=name):
                path = self.root / "adapter-only" / name
                original = path.read_bytes() if path.exists() else None

                def change(root, paths):
                    path.write_text("Changed after inspection\n")
                    return actual(root, paths)

                try:
                    with patch.object(planning, "inventory", side_effect=change):
                        with self.assertRaisesRegex(ValueError, "changed|differ"):
                            planning.make_plan(
                                self.root, "store-upload.json", "production", "binary"
                            )
                finally:
                    (
                        path.write_bytes(original)
                        if original is not None
                        else path.unlink()
                    )

    def test_artifact_classifies_existing_capture_without_second_copy(self):
        artifacts = module("artifacts")
        with patch.object(
            artifacts, "container_kind", side_effect=AssertionError("second capture")
        ):
            plan = module("planning").make_plan(
                self.root, "store-upload.json", "production", "binary"
            )
        self.assertEqual(plan["payload"]["build"]["kind"], "aab")
