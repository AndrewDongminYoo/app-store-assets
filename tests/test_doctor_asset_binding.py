"""Doctor binds local images and import provenance without a remote snapshot."""

import contextlib
import copy
import hashlib
import io
import json
import socket
import unittest
from unittest.mock import patch

from offline_support import fixture, module, write_json
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class DoctorAssetBindingTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = self.profile["targets"]["production"]
        identity = module("profiles").target_identity(self.target)
        self.data = png()
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.asset_record = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": identity,
            "provenance": {"status": "unverified-import"},
            "inputs": {"en-US/01.png": self.sha},
            "source_export": "1" * 64,
            "assets": [{"locale": "en-US", "slot": "APP_IPHONE_65",
                        "file": "en-US/01.png", "sha256": self.sha}],
        }
        self.asset_dir = snapshot_fixture(
            self.root / "state/assets", self.asset_record, {"en-US/01.png": self.data}
        )
        self.history = {
            "schema_version": 1, "type": "metadata-import", "target": identity,
            "inputs": self.asset_record["inputs"], "source_export": "1" * 64,
        }
        history_dir = snapshot_fixture(self.root / "state/metadata", self.history)
        self.listing = {
            "schema_version": 1, "type": "metadata", "target": identity,
            "source_snapshot": str(history_dir.relative_to(self.root) / "manifest.json"),
            "images": {"en-US": {"APP_IPHONE_65": [{
                "file": str(self.asset_dir.relative_to(self.root) / "en-US/01.png"),
                "sha256": self.sha,
            }]}},
        }
        self.target["assets"] = {"manifest": str(self.asset_dir.relative_to(self.root) / "manifest.json")}
        self.target["replacement"] = {"locales": ["en-US"], "slots": ["APP_IPHONE_65"], "allow_delete": False}
        # The path remains declared but absent: doctor must never read remote state.
        (self.root / "remote.json").unlink()
        self.save()

    def save(self):
        write_json(self.root / "metadata/listing.json", self.listing)
        write_json(self.root / "store-upload.json", self.profile)

    def doctor(self):
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err),
            patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")),
        ):
            code = module("cli").main([
                "doctor", "--root", str(self.root), "--target", "production"
            ])
        return code, out.getvalue(), err.getvalue()

    def assert_refused(self, pattern):
        code, out, err = self.doctor()
        self.assertEqual(code, 2, out)
        self.assertEqual(out, "")
        self.assertRegex(err, pattern)

    def test_valid_local_assets_are_inventoried_without_remote_or_writes(self):
        before = set(self.root.rglob("*"))
        code, out, err = self.doctor()
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertIn(self.listing["images"]["en-US"]["APP_IPHONE_65"][0]["file"], result["inputs"])
        self.assertEqual(result["inputs"][self.listing["images"]["en-US"]["APP_IPHONE_65"][0]["file"]], self.sha)
        self.assertIn(self.target["assets"]["manifest"], result["inputs"])
        self.assertIn(self.listing["source_snapshot"], result["inputs"])
        self.assertFalse(result["remote_verified"])
        self.assertEqual(result["effects"], [])
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_earlier_snapshot_of_same_app_is_refused(self):
        old = copy.deepcopy(self.asset_record)
        old["source_export"] = "2" * 64
        directory = snapshot_fixture(self.root / "state/assets", old, {"en-US/01.png": self.data})
        self.target["assets"]["manifest"] = str(directory.relative_to(self.root) / "manifest.json")
        self.save()
        self.assert_refused("asset manifest.*listing")

    def test_snapshot_bytes_are_charged_only_once_in_final_inventory(self):
        original = list(self.target["inputs"])
        for extra in ([], ["state"], [self.target["assets"]["manifest"]], [self.listing["source_snapshot"]]):
            with self.subTest(extra=extra):
                self.target["inputs"] = original + extra
                self.save()
                code, out, err = self.doctor()
                self.assertEqual(code, 0, err)
                expected = json.loads(out)["inputs"]
                size = sum((self.root / name).stat().st_size for name in expected)
                records = module("records")

                def bounded(root, paths):
                    budget = records.WalkBudget()
                    budget.remaining = size
                    return records.inventory(root, paths, budget=budget)

                with patch.object(module("cli"), "inventory", side_effect=bounded):
                    code, out, err = self.doctor()
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out)["inputs"], expected)

    def test_overlapping_inputs_do_not_hide_a_missing_declared_child(self):
        self.target["inputs"].extend(["state", "state/missing.txt"])
        self.save()
        self.assert_refused("missing bound input")

    def test_declared_child_removed_before_inventory_is_refused(self):
        self.target["inputs"].append("helpers/source.txt")
        self.save()
        inventory = module("cli").inventory

        def remove_child(root, paths):
            (self.root / "helpers/source.txt").unlink()
            return inventory(root, paths)

        with patch.object(module("cli"), "inventory", side_effect=remove_child):
            code, out, err = self.doctor()
        self.assertEqual(code, 2, out)
        self.assertRegex(err, "missing bound input")

    def test_declared_empty_directory_removed_before_inventory_is_refused(self):
        directory = self.root / "state/declared-empty"
        directory.mkdir()
        self.target["inputs"].extend(["state", "state/declared-empty"])
        self.save()
        inventory = module("cli").inventory

        def remove_directory(root, paths):
            directory.rmdir()
            return inventory(root, paths)

        with patch.object(module("cli"), "inventory", side_effect=remove_directory):
            self.assert_refused("missing bound input")

    def test_tampered_snapshot_bytes_are_refused(self):
        (self.asset_dir / "en-US/01.png").write_bytes(self.data + b"changed")
        self.assert_refused("hash|inventory")

    def test_listing_hash_and_membership_are_checked(self):
        image = self.listing["images"]["en-US"]["APP_IPHONE_65"][0]
        image["sha256"] = "0" * 64
        self.save()
        self.assert_refused("hash|sha256|inventory")
        (self.root / "outside.png").write_bytes(self.data)
        image.update(file="outside.png", sha256=self.sha)
        self.save()
        self.assert_refused("asset manifest.*listing")

    def test_import_provenance_must_agree_even_with_identical_image_bytes(self):
        for key, value in (("source_export", "2" * 64), ("inputs", {"en-US/01.png": "2" * 64})):
            with self.subTest(key=key):
                history = dict(self.history, **{key: value})
                directory = snapshot_fixture(self.root / "state/metadata", history)
                self.listing["source_snapshot"] = str(directory.relative_to(self.root) / "manifest.json")
                self.save()
                self.assert_refused("asset manifest.*provenance")

    def test_asset_descriptor_requires_a_listing(self):
        self.target.pop("metadata")
        self.save()
        self.assert_refused("listing")

    def test_import_provenance_cannot_be_bypassed_by_omitting_keys(self):
        for key in ("inputs", "source_export"):
            with self.subTest(key=key):
                history = {name: value for name, value in self.history.items() if name != key}
                directory = snapshot_fixture(self.root / "state/metadata", history)
                self.listing["source_snapshot"] = str(directory.relative_to(self.root) / "manifest.json")
                self.save()
                self.assert_refused("asset manifest.*provenance")

    def test_added_snapshot_file_before_final_inventory_is_refused(self):
        inventory = module("cli").inventory

        def changed(root, paths):
            (self.asset_dir / "added.txt").write_text("outside manifest")
            return inventory(root, paths)

        with patch.object(module("cli"), "inventory", side_effect=changed):
            self.assert_refused("snapshot inventory")

    def test_added_metadata_snapshot_file_before_final_inventory_is_refused(self):
        inventory = module("cli").inventory
        directory = (self.root / self.listing["source_snapshot"]).parent

        def changed(root, paths):
            (directory / "added.txt").write_text("outside provenance manifest")
            return inventory(root, paths)

        with patch.object(module("cli"), "inventory", side_effect=changed):
            self.assert_refused("snapshot inventory")

    def test_plan_keeps_the_same_asset_binding_and_remote_requirement(self):
        planning = module("planning")
        with self.assertRaisesRegex(ValueError, "missing input"):
            planning.make_plan(self.root, "store-upload.json", "production", "images")
        write_json(self.root / "remote.json", {
            "schema_version": 1, "type": "metadata-snapshot",
            "target": self.listing["target"], "version_id": "version-1",
            "editable": True, "review_active": False,
            "fields": {"en-US": {"description": "Available locale"}},
            "images": {"en-US": {}},
        })
        result = planning.make_plan(self.root, "store-upload.json", "production", "images")
        self.assertEqual(result["payload"]["assets"], self.asset_record)
        self.assertFalse(result["payload"]["executable"])
        self.assertEqual(result["payload"]["effects"], [])
        inventory = planning.inventory

        def added(root, paths):
            (self.asset_dir / "added.txt").write_text("outside manifest")
            return inventory(root, paths)

        with patch.object(planning, "inventory", side_effect=added):
            with self.assertRaisesRegex(ValueError, "snapshot inventory"):
                planning.make_plan(self.root, "store-upload.json", "production", "images")

    def test_doctor_detects_image_change_before_final_inventory(self):
        inventory = module("cli").inventory

        def changed(root, paths):
            (self.asset_dir / "en-US/01.png").write_bytes(self.data + b"changed")
            return inventory(root, paths)

        with patch.object(module("cli"), "inventory", side_effect=changed):
            self.assert_refused("capture|changed|inventory")


if __name__ == "__main__":
    unittest.main()
