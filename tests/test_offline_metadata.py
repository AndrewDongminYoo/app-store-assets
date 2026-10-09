import copy
import hashlib
import json
import unittest

from offline_support import fixture, module, write_json
from test_assets import png


class MetadataRoundtripTests(unittest.TestCase):
    def setup_store(self, store="apple"):
        self.root, self.profile = fixture(self, store=store)
        self.io = module(self, "metadata_io")
        self.target = module(self, "profiles").target_identity(
            self.profile["targets"]["production"]
        )
        data = png() if store == "apple" else png(810, 1440)
        slot = "APP_IPHONE_65" if store == "apple" else "phoneScreenshots"
        key = "description" if store == "apple" else "full_description"
        remote = {
            "target": self.target,
            "fields": {"en-US": {key: "Remote text"}},
            "images": {
                "en-US": {
                    slot: [
                        {
                            "id": "remote-1",
                            "file": "images/01.png",
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "processing_state": "processed",
                        }
                    ]
                }
            },
        }
        if store == "google":
            remote["releases"] = [
                {"version_codes": ["9"], "notes": {"en-US": "Remote notes"}}
            ]
        remote = module(self, "metadata").normalize_remote(remote, self.target)
        self.snapshot = module(self, "snapshots").publish_snapshot(
            self.root / "downloads", remote, {"images/01.png": data}
        )
        self.before = copy.deepcopy(remote)
        return key, slot

    def export(self):
        return self.io.export_metadata(
            self.root, self.snapshot, self.target, self.root / "new-export"
        )

    def test_apple_google_export_import_diff_preserve_original_editing_trees(self):
        for store in ("apple", "google"):
            with self.subTest(store=store):
                key, slot = self.setup_store(store)
                original = (self.root / "metadata/listing.json").read_bytes()
                notes = (self.root / "metadata/en-US/changelogs/9.txt").read_bytes()
                directory = self.export()
                text = directory / ("en-US/" + key + ".txt")
                self.assertEqual(text.read_text(), "Remote text")
                text.write_text("Reviewed local edit")
                result = self.io.import_metadata(
                    self.root,
                    directory,
                    self.target,
                    self.root / "imported-listing.json",
                    self.root / "import-history",
                )
                listing = json.loads((self.root / result["listing"]).read_text())
                self.assertEqual(listing["fields"]["en-US"][key], "Reviewed local edit")
                self.assertEqual(
                    listing["images"]["en-US"][slot][0]["sha256"],
                    self.before["images"]["en-US"][slot][0]["sha256"],
                )
                self.assertTrue(
                    (self.root / listing["images"]["en-US"][slot][0]["file"]).is_file()
                )
                self.assertEqual(
                    module(self, "snapshots").validate_snapshot(
                        (self.root / result["assets"]).parent
                    )["record"]["provenance"]["status"],
                    "unverified-import",
                )
                changes = module(self, "metadata").metadata_diff(self.before, listing)
                self.assertEqual([c["path"] for c in changes], ["fields.en-US." + key])
                if store == "google":
                    self.assertEqual(
                        (self.root / result["changelogs"]["en-US"]).read_text(),
                        "Remote notes",
                    )
                self.assertEqual(
                    (self.root / "metadata/listing.json").read_bytes(), original
                )
                self.assertEqual(
                    (self.root / "metadata/en-US/changelogs/9.txt").read_bytes(), notes
                )

    def test_export_and_import_never_overwrite_existing_outputs(self):
        self.setup_store()
        directory = self.export()
        with self.assertRaisesRegex(ValueError, "exists|overwrite"):
            self.export()
        output = self.root / "already.json"
        output.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "exists|overwrite"):
            self.io.import_metadata(
                self.root, directory, self.target, output, self.root / "history"
            )
        self.assertEqual(output.read_text(), "preserve")

    def test_import_rejects_target_conflict_private_extra_files_and_path_escape(self):
        self.setup_store()
        directory = self.export()
        manifest = directory / "store-assets-export.json"
        original = json.loads(manifest.read_text())
        changed = copy.deepcopy(original)
        changed["target"]["version"]["build"] = "10"
        write_json(manifest, changed)
        with self.assertRaisesRegex(ValueError, "target"):
            self.io.import_metadata(
                self.root,
                directory,
                self.target,
                self.root / "listing.json",
                self.root / "history",
            )
        changed = copy.deepcopy(original)
        changed["fields"][0]["file"] = "../outside.txt"
        write_json(manifest, changed)
        with self.assertRaisesRegex(ValueError, "path|relative|escape"):
            self.io.import_metadata(
                self.root,
                directory,
                self.target,
                self.root / "listing.json",
                self.root / "history",
            )
        write_json(manifest, original)
        (directory / "key.properties").write_text("synthetic protected material")
        with self.assertRaisesRegex(ValueError, "private|credential|inventory"):
            self.io.import_metadata(
                self.root,
                directory,
                self.target,
                self.root / "listing.json",
                self.root / "history",
            )

    def test_import_metadata_only_explicitly_avoids_unsupported_image_upload(self):
        self.setup_store("google")
        directory = self.export()
        manifest = directory / "store-assets-export.json"
        value = json.loads(manifest.read_text())
        value["images"][0]["slot"] = "wearScreenshots"
        write_json(manifest, value)
        with self.assertRaisesRegex(ValueError, "slot"):
            self.io.import_metadata(
                self.root,
                directory,
                self.target,
                self.root / "blocked.json",
                self.root / "history",
            )
        result = self.io.import_metadata(
            self.root,
            directory,
            self.target,
            self.root / "text-only.json",
            self.root / "history",
            metadata_only=True,
        )
        self.assertEqual(
            json.loads((self.root / result["listing"]).read_text())["images"], {}
        )
        self.assertIsNone(result["assets"])

    def test_nonpublic_manifest_mapping_is_rejected_before_inventory_reads(self):
        from unittest.mock import patch

        self.setup_store()
        directory = self.export()
        path = directory / "store-assets-export.json"
        value = json.loads(path.read_text())
        value["fields"][0]["file"] = "id_rsa"
        write_json(path, value)
        with patch.object(
            self.io,
            "inventory",
            side_effect=AssertionError("mapped protected file read"),
        ):
            with self.assertRaisesRegex(ValueError, "public.*path"):
                self.io.import_metadata(
                    self.root,
                    directory,
                    self.target,
                    self.root / "listing.json",
                    self.root / "history",
                )

    def test_export_destination_symlink_is_rejected(self):
        self.setup_store()
        (self.root / "alias").symlink_to(
            self.root / "metadata", target_is_directory=True
        )
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.io.export_metadata(
                self.root, self.snapshot, self.target, self.root / "alias/export"
            )
        self.assertFalse((self.root / "metadata/export").exists())

    def test_import_manifest_symlink_is_rejected_before_reading(self):
        from unittest.mock import patch

        self.setup_store()
        directory = self.export()
        manifest = directory / "store-assets-export.json"
        manifest.unlink()
        manifest.symlink_to(self.root / "metadata/listing.json")
        with patch.object(
            self.io, "read_json", side_effect=AssertionError("symlink target read")
        ):
            with self.assertRaisesRegex(ValueError, "symlink"):
                self.io.import_metadata(
                    self.root,
                    directory,
                    self.target,
                    self.root / "listing.json",
                    self.root / "history",
                )

    def test_import_cannot_publish_transient_text_outside_its_bound_inventory(self):
        from unittest.mock import patch

        self.setup_store()
        directory = self.export()
        original_read = self.io.text_bytes

        def transient(path):
            data = original_read(path)
            return (
                b"unreviewed transient text" if path.name == "description.txt" else data
            )

        with patch.object(self.io, "text_bytes", side_effect=transient):
            with self.assertRaisesRegex(ValueError, "changed|inventory"):
                self.io.import_metadata(
                    self.root,
                    directory,
                    self.target,
                    self.root / "listing.json",
                    self.root / "history",
                )
        self.assertFalse((self.root / "listing.json").exists())

    def test_export_cannot_mutate_immutable_source_snapshot(self):
        self.setup_store()
        with self.assertRaisesRegex(ValueError, "overlap|snapshot"):
            self.io.export_metadata(
                self.root, self.snapshot, self.target, self.snapshot / "editing"
            )
        module(self, "snapshots").validate_snapshot(self.snapshot)


if __name__ == "__main__":
    unittest.main()
