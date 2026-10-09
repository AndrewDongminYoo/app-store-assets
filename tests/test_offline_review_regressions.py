import copy
import json
import unittest
import zipfile
from unittest.mock import patch

from offline_support import fixture, module, write_json


class IndependentReviewProbes(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self, "google")

    def test_unselected_apple_track_is_rejected(self):
        target = copy.deepcopy(self.profile["targets"]["production"])
        target.update(
            store="apple",
            platform="ios",
            track={"api_token": "synthetic-public-marker"},
        )
        target.pop("release_status")
        self.profile["targets"]["unselected"] = target
        write_json(self.root / "store-upload.json", self.profile)
        with self.assertRaises(ValueError):
            module("profiles").load_profile(
                self.root, "store-upload.json", "production"
            )

    def test_binary_notes_use_public_text_validation(self):
        self.profile["targets"]["production"]["changelogs"] = {
            "en-US": "metadata/en-US/changelogs/9.txt"
        }
        write_json(self.root / "store-upload.json", self.profile)
        (self.root / "metadata/en-US/changelogs/9.txt").write_text(
            "synthetic\x00public"
        )
        with self.assertRaises(ValueError):
            plan = module("planning").make_plan(
                self.root, "store-upload.json", "production", "binary"
            )
            self.assertEqual(
                plan["payload"]["release_notes"]["en-US"], "synthetic\x00public"
            )

    def test_catalog_capture_cannot_differ_from_reported_pin(self):
        catalog, planning = module("catalog"), module("planning")
        catalog_path = self.root / "tools/app-store-assets/catalog/store-rules-v1.json"
        original = catalog_path.read_bytes()
        changed = json.loads(original)
        changed["stores"]["google"]["text_limits"]["title"][0] = 100
        listing_path = self.root / "metadata/listing.json"
        listing = json.loads(listing_path.read_text())
        listing["fields"] = {"en-US": {"title": "X" * 60}}
        write_json(listing_path, listing)
        real_read = catalog.read_json

        def swapped(path, *args, **kwargs):
            catalog_path.write_text(json.dumps(changed))
            try:
                return real_read(path, *args, **kwargs)
            finally:
                catalog_path.write_bytes(original)

        with (
            patch.object(catalog, "CATALOG_FILE", catalog_path),
            patch.object(planning, "CATALOG_FILE", catalog_path),
            patch.object(catalog, "read_json", side_effect=swapped),
        ):
            with self.assertRaises(ValueError):
                plan = planning.make_plan(
                    self.root, "store-upload.json", "production", "metadata"
                )
                self.assertEqual(
                    plan["payload"]["listing"]["fields"]["en-US"]["title"], "X" * 60
                )
                self.assertEqual(
                    plan["payload"]["catalog_sha256"],
                    module("records").file_digest(catalog_path),
                )

    def test_direct_container_kind_observes_byte_limit(self):
        path = self.root / "oversized.apk"
        with path.open("wb") as stream:
            stream.truncate(module("records").FILE_LIMIT + 1)
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("AndroidManifest.xml", b"synthetic public marker")
        with self.assertRaises(ValueError):
            self.assertEqual(module("artifacts").container_kind(path), "apk")

    def test_image_annotations_agree_with_captured_dimensions(self):
        from test_assets import png

        (self.root / "public.png").write_bytes(png(512, 1024))
        entry = {
            "file": "public.png",
            "locale": "en-US",
            "slot": "phoneScreenshots",
            "width": 1,
            "height": 1,
        }
        with self.assertRaises(ValueError):
            module("catalog").validate_images(self.root, [entry], "google")

    def test_snapshot_asset_dimensions_agree_with_captured_bytes(self):
        import hashlib

        from test_assets import png
        from test_offline_boundaries import snapshot_fixture

        data = png(512, 1024)
        record = {
            "schema_version": 1,
            "type": "asset-manifest",
            "target": module("profiles").target_identity(
                self.profile["targets"]["production"]
            ),
            "assets": [
                {
                    "file": "public.png",
                    "locale": "en-US",
                    "slot": "phoneScreenshots",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": [1, 1],
                }
            ],
            "provenance": {"status": "unverified-import"},
        }
        folder = snapshot_fixture(self.root / "history", record, {"public.png": data})
        with self.assertRaises(ValueError):
            module("snapshots").validate_snapshot(folder)
