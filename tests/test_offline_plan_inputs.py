"""Hosted B input regressions: synthetic inputs, no store or network calls."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from offline_support import fixture, module, write_json
from test_assets import png


class OfflinePlanInputTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.planning = module("planning")

    def plan(self, operation="metadata"):
        return self.planning.make_plan(
            self.root, "store-upload.json", "production", operation
        )

    def images(self):
        path = self.root / "screenshots/01.png"
        path.parent.mkdir()
        path.write_bytes(png())
        listing_path = self.root / "metadata/listing.json"
        listing = json.loads(listing_path.read_text())
        listing["images"] = {
            "en-US": {"APP_IPHONE_65": [{"file": "screenshots/01.png"}]}
        }
        write_json(listing_path, listing)
        self.profile["targets"]["production"]["replacement"] = {
            "locales": ["en-US"],
            "slots": ["APP_IPHONE_65"],
            "allow_delete": False,
        }
        write_json(self.root / "store-upload.json", self.profile)
        return path

    def test_local_listing_private_and_unknown_keys_fail_closed_for_both_operations(
        self,
    ):
        self.images()
        path = self.root / "metadata/listing.json"
        original = json.loads(path.read_text())
        for operation in ("metadata", "images"):
            for key in ("api_token", "unsupported_public_field"):
                with self.subTest(operation=operation, key=key):
                    write_json(path, dict(original, **{key: "synthetic-only"}))
                    with self.assertRaisesRegex(ValueError, "unsupported|private"):
                        self.plan(operation)
        self.assertFalse((self.root / "build").exists())

    def test_cli_rejected_local_listing_does_not_echo_private_value(self):
        path = self.root / "metadata/listing.json"
        listing = json.loads(path.read_text())
        listing["api_token"] = "synthetic-forbidden-value"
        write_json(path, listing)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module("cli").main(
                [
                    "plan",
                    "--root",
                    str(self.root),
                    "--target",
                    "production",
                    "--operation",
                    "metadata",
                ]
            )
        self.assertEqual(code, 2)
        self.assertNotIn("synthetic-forbidden-value", out.getvalue() + err.getvalue())
        self.assertFalse((self.root / "build").exists())

    def test_listing_replaced_after_parse_cannot_bind_new_hash_to_old_fields(self):
        path = self.root / "metadata/listing.json"
        read = self.planning.read_json
        observed = []

        def replace_after_parse(p, *args, **kwargs):
            value = read(p, *args, **kwargs)
            if p.resolve() == path.resolve():
                observed.append(value["fields"]["en-US"]["description"])
                changed = json.loads(path.read_text())
                changed["fields"]["en-US"]["description"] = "Changed after parse"
                write_json(path, changed)
            return value

        with patch.object(self.planning, "read_json", side_effect=replace_after_parse):
            with self.assertRaisesRegex(ValueError, "changed|capture|bound"):
                self.plan()
        self.assertEqual(observed, ["Approved description"])
        self.assertFalse((self.root / "build").exists())

    def test_other_parsed_inputs_changed_before_final_inventory_fail_closed(self):
        (self.root / "pubspec.yaml").write_text("version: 1.0+9\n")
        self.profile["targets"]["production"]["version_source"] = {
            "file": "pubspec.yaml"
        }
        write_json(self.root / "store-upload.json", self.profile)
        original_inventory = self.planning.inventory
        cases = ("store-upload.json", "remote.json", "pubspec.yaml")
        for name in cases:
            with self.subTest(input=name):
                path = self.root / name
                original = path.read_bytes()

                def replace_before_inventory(root, paths):
                    if name == "pubspec.yaml":
                        path.write_text("version: 1.0+10\n")
                        return original_inventory(root, paths)
                    value = json.loads(path.read_text())
                    if name == "store-upload.json":
                        value["mode"] = "live"
                    else:
                        value["fields"]["en-US"]["description"] = "New observation"
                    write_json(path, value)
                    return original_inventory(root, paths)

                try:
                    with (
                        patch.object(
                            self.planning,
                            "inventory",
                            side_effect=replace_before_inventory,
                        ),
                        self.assertRaisesRegex(ValueError, "changed|capture|bound"),
                    ):
                        self.plan()
                finally:
                    path.write_bytes(original)

    def test_binary_inputs_changed_before_final_inventory_fail_closed(self):
        self.root, self.profile = fixture(self, "google")
        self.profile["targets"]["production"]["changelogs"] = {
            "en-US": "metadata/en-US/changelogs/9.txt"
        }
        write_json(self.root / "store-upload.json", self.profile)
        original_inventory = self.planning.inventory

        for name in (
            "metadata/en-US/changelogs/9.txt",
            "artifact.json",
            "artifacts/app.aab",
        ):
            with self.subTest(input=name):
                path = self.root / name
                original = path.read_bytes()

                def replace_before_inventory(root, paths):
                    if name.endswith(".json"):
                        record = json.loads(path.read_text())
                        record["version"]["build"] = "10"
                        write_json(path, record)
                    elif name.endswith(".aab"):
                        path.write_bytes(original + b"changed after validation")
                    else:
                        path.write_text("Changed notes after capture\n")
                    return original_inventory(root, paths)

                try:
                    with (
                        patch.object(
                            self.planning,
                            "inventory",
                            side_effect=replace_before_inventory,
                        ),
                        self.assertRaisesRegex(ValueError, "changed|capture|bound"),
                    ):
                        self.plan("binary")
                finally:
                    path.write_bytes(original)

    def test_image_changed_after_validation_before_inventory_fail_closed(self):
        path = self.images()
        original_inventory = self.planning.inventory

        def replace_before_inventory(root, paths):
            path.write_bytes(png(width=1284, height=2778))
            return original_inventory(root, paths)

        with (
            patch.object(
                self.planning, "inventory", side_effect=replace_before_inventory
            ),
            self.assertRaisesRegex(ValueError, "changed|capture|bound"),
        ):
            self.plan("images")
