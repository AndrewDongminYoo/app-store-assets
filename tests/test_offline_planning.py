import copy
import json
import unittest
from unittest.mock import patch

from offline_support import container, fixture, module, write_json
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class OfflinePlanningTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.planning = module("planning")

    def plan(self, operation="metadata"):
        return self.planning.make_plan(
            self.root, "store-upload.json", "production", operation
        )

    def remote(self, change):
        p = self.root / "remote.json"
        r = json.loads(p.read_text())
        r.update(change)
        write_json(p, r)

    def test_supplied_apple_state_rejects_noneditable_review_active_or_missing_id(self):
        for change in (
            {"editable": False},
            {"editable": "true"},
            {"review_active": True},
            {"review_active": None},
            {"version_id": None},
            {"version_id": ""},
        ):
            with self.subTest(change=change):
                old = (self.root / "remote.json").read_bytes()
                self.remote(change)
                with self.assertRaisesRegex(ValueError, "version|editable|review"):
                    self.plan()
                (self.root / "remote.json").write_bytes(old)

    def test_apple_metadata_requires_supplied_snapshot_and_locale(self):
        self.profile["targets"]["production"].pop("remote")
        write_json(self.root / "store-upload.json", self.profile)
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.plan()

    def test_supplied_snapshot_is_never_current_remote_verification(self):
        plan = self.plan()
        p = plan["payload"]
        self.assertEqual(p["type"], "offline-release-plan")
        self.assertIs(p["executable"], False)
        self.assertEqual(p["effects"], [])
        self.assertIs(p["remote_verified"], False)
        self.assertEqual(p["remote_evidence"], "supplied-snapshot-freshness-unverified")
        self.assertFalse((self.root / "build").exists())

    def test_url_protocol_host_port_and_public_credentials(self):
        listing = json.loads((self.root / "metadata/listing.json").read_text())
        for value in (
            "example.com",
            "not a URL",
            "ftp://example.com",
            "https://",
            "https://example.com:bad",
            "https://u:p@example.com",
            "https://example.com/?token=x",
            "https://exa mple.com",
            "https://example.com\\evil",
        ):
            with self.subTest(value=value):
                listing["fields"]["en-US"]["support_url"] = value
                write_json(self.root / "metadata/listing.json", listing)
                with self.assertRaisesRegex(ValueError, "URL|url|credential"):
                    self.plan()
        listing["fields"]["en-US"]["support_url"] = "https://example.invalid/contact"
        listing["fields"]["en-US"]["marketing_url"] = ""
        write_json(self.root / "metadata/listing.json", listing)
        self.plan()

    def test_apple_name_minimum_and_maximum(self):
        listing = json.loads((self.root / "metadata/listing.json").read_text())
        for value in ("", "A", "x" * 31):
            listing["fields"]["en-US"]["name"] = value
            write_json(self.root / "metadata/listing.json", listing)
            with self.assertRaisesRegex(ValueError, "name|limit|minimum"):
                self.plan()
        listing["fields"]["en-US"]["name"] = "AB"
        write_json(self.root / "metadata/listing.json", listing)
        self.plan()

    def images(self, store="apple"):
        if store != "apple":
            self.root, self.profile = fixture(self, store)
        target = self.profile["targets"]["production"]
        slot = "APP_IPHONE_65" if store == "apple" else "phoneScreenshots"
        data = png() if store == "apple" else png(512, 1024)
        image = {
            "file": "images/01.png",
            "locale": "en-US",
            "slot": slot,
            "sha256": module("records").record_digest({"fake": 1}),
        }
        import hashlib

        image["sha256"] = hashlib.sha256(data).hexdigest()
        assets = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": module("profiles").target_identity(target),
            "assets": [image],
            "provenance": {"status": "unverified-import"},
        }
        snap = snapshot_fixture(self.root / "assets", assets, {"images/01.png": data})
        listing = json.loads((self.root / "metadata/listing.json").read_text())
        listing["images"] = {
            "en-US": {
                slot: [{"file": str(snap.relative_to(self.root) / "images/01.png")}]
            }
        }
        write_json(self.root / "metadata/listing.json", listing)
        target.update(
            assets={"manifest": str(snap.relative_to(self.root) / "manifest.json")},
            replacement={"locales": ["en-US"], "slots": [slot], "allow_delete": False},
        )
        self.profile["mode"] = "live"
        write_json(self.root / "store-upload.json", self.profile)
        return (slot, image)

    def test_computed_image_hash_and_size_retained_for_both_stores(self):
        for store in ("apple", "google"):
            slot, image = self.images(store)
            plan = self.plan("images")
            item = plan["payload"]["listing"]["images"]["en-US"][slot][0]
            self.assertEqual(item["sha256"], image["sha256"])
            self.assertEqual(len(item["size"]), 2)
            self.planning.verify_plan(self.root, plan)

    def test_image_policy_mismatch_and_manifest_target_fail_closed(self):
        self.images()
        self.profile["targets"]["production"]["replacement"]["slots"] = [
            "APP_IPHONE_67"
        ]
        write_json(self.root / "store-upload.json", self.profile)
        with self.assertRaisesRegex(ValueError, "policy|replacement|slot"):
            self.plan("images")

    def test_changed_source_and_target_invalidates_plan(self):
        plan = self.plan()
        (self.root / "helpers/source.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed|differs"):
            self.planning.verify_plan(self.root, plan)

    def test_effect_configuration_and_unknown_schema_rejected(self):
        for key in ("provider", "build"):
            p = copy.deepcopy(self.profile)
            p["targets"]["production"][key] = {"argv": ["native-upload"]}
            write_json(self.root / "store-upload.json", p)
            with self.assertRaisesRegex(ValueError, "unknown|offline"):
                self.plan()

    def test_runtime_untracked_and_ignored_executable_mutation_blocked(self):
        runtime = self.root / "tools/app-store-assets"
        (runtime / "untracked.py").write_text("raise RuntimeError()")
        with self.assertRaisesRegex(ValueError, "modified|untracked"):
            self.plan()

    def test_private_input_is_rejected_before_read(self):
        (self.root / "helpers/credentials.json").write_text("synthetic protected value")
        with (
            patch.object(
                module("records"),
                "file_digest",
                side_effect=AssertionError("protected read"),
            ),
            self.assertRaisesRegex(ValueError, "credential|private"),
        ):
            module("records").inventory(self.root, ["helpers/credentials.json"])

    def test_symlink_and_shell_literal_paths_are_confined(self):
        (self.root / "alias").symlink_to(
            self.root / "metadata", target_is_directory=True
        )
        with self.assertRaisesRegex(ValueError, "symlink"):
            module("records").safe_path(self.root, "alias/listing.json")
        self.plan()

    def test_google_apk_and_aab_kind_are_bound_without_endpoint_policy(self):
        for kind in ("apk", "aab"):
            self.root, self.profile = fixture(self, "google", kind)
            plan = self.plan("binary")
            self.assertEqual(plan["payload"]["artifact"]["kind"], kind)
            self.assertEqual(plan["payload"]["build"]["kind"], kind)
            self.assertEqual(
                plan["payload"]["artifact_verification"],
                "container-and-supplied-record-only",
            )

    def test_kind_record_filename_and_container_mismatch_fail_closed(self):
        self.root, self.profile = fixture(self, "google", "apk")
        path = self.root / "artifact.json"
        record = json.loads(path.read_text())
        record["kind"] = "aab"
        write_json(path, record)
        with self.assertRaisesRegex(ValueError, "kind"):
            self.plan("binary")
        record["kind"] = "apk"
        write_json(path, record)
        container(self.root / "artifacts/app.apk", "aab")
        record["sha256"] = module("records").file_digest(
            self.root / "artifacts/app.apk"
        )
        write_json(path, record)
        with self.assertRaisesRegex(ValueError, "container|kind"):
            self.plan("binary")

    def test_fixture_build_is_not_live_inspection(self):
        self.profile["mode"] = "live"
        write_json(self.root / "store-upload.json", self.profile)
        with self.assertRaisesRegex(ValueError, "fixture|inspection"):
            self.plan("binary")

    def test_image_decoder_consumes_hash_bound_capture(self):
        slot, image = self.images()
        catalog = module("catalog")
        original = catalog.image_info

        def check(path, **kwargs):
            self.assertFalse(path.is_relative_to(self.root.resolve()))
            self.assertEqual(module("records").file_digest(path), image["sha256"])
            return original(path, **kwargs)

        with patch.object(catalog, "image_info", side_effect=check):
            self.plan("images")
