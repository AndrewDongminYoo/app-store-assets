"""B2 writes only fully validated captured public inputs to reserved outputs."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


class LocalOutputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        self.record = {
            "schema_version": 1,
            "type": "metadata-snapshot",
            "target": self.target,
            "fields": {"en-US": {"description": "public"}},
            "images": {},
        }

    def test_publisher_full_record_rejected_before_history_creation(self):
        for change in (
            {"api_token": "synthetic"},
            {"source_export": {"api_token": "synthetic"}},
            {"source_export": "not-a-digest"},
            {
                "target": dict(
                    self.target,
                    version=dict(self.target["version"], api_token="synthetic"),
                )
            },
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                module("publisher").publish_snapshot(
                    self.root / "new-history", dict(self.record, **change), {}
                )
            self.assertFalse((self.root / "new-history").exists())

    def test_publisher_private_parent_rejected_before_source_read_or_history(self):
        protected = self.root / ".env.production"
        protected.mkdir()
        (protected / "public.txt").write_text("synthetic")
        for name, value in (
            (".env.production/public.txt", b"synthetic"),
            ("public.txt", protected / "public.txt"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                module("publisher").publish_snapshot(
                    self.root / "new-history", self.record, {name: value}
                )
            self.assertFalse((self.root / "new-history").exists())

    def test_existing_empty_content_address_is_not_overwritten(self):
        digest = module("records").record_digest(
            {
                "schema_version": 1,
                "type": "snapshot",
                "record": self.record,
                "files": {},
            }
        )
        parent = self.root / "history"
        occupied = parent / digest
        occupied.mkdir(parents=True)
        with self.assertRaises((ValueError, OSError)):
            module("publisher").publish_snapshot(parent, self.record, {})
        self.assertEqual(list(occupied.iterdir()), [])

    def test_staging_parent_symlink_and_private_descendant_fail_before_new_output(self):
        old = self.root / "saved"
        (self.root / "helpers").rename(old)
        (self.root / "helpers").symlink_to(old, target_is_directory=True)
        expected = {
            "helpers/source.txt": hashlib.sha256(
                (old / "source.txt").read_bytes()
            ).hexdigest()
        }
        temp = tempfile.TemporaryDirectory(prefix="owned-stage-boundary-")
        self.addCleanup(temp.cleanup)
        destination = Path(temp.name).resolve() / "new-stage"
        with self.assertRaises((ValueError, OSError)):
            module("staging").stage_inventory(self.root, destination, expected)
        self.assertFalse(destination.exists())
        protected = self.root / ".env.production"
        protected.mkdir()
        (protected / "public.txt").write_text("synthetic")
        with self.assertRaises(ValueError):
            module("staging").stage_inventory(
                self.root,
                destination,
                {
                    ".env.production/public.txt": hashlib.sha256(
                        b"synthetic"
                    ).hexdigest()
                },
            )
        self.assertFalse(destination.exists())

    def test_output_parent_symlink_never_receives_export_or_published_files(self):
        snapshot = snapshot_fixture(self.root / "snapshots", self.record)
        outside = self.root / "outside-public"
        outside.mkdir()
        alias = self.root / "output-alias"
        alias.symlink_to(outside, target_is_directory=True)
        for name in ("export", "publisher"):
            with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                if name == "export":
                    module("metadata_io").export_metadata(
                        self.root, snapshot, self.target, alias / "new"
                    )
                else:
                    module("publisher").publish_snapshot(alias / "new", self.record, {})
        self.assertEqual(list(outside.iterdir()), [])

    def test_metadata_only_still_rejects_unknown_nested_image_annotations(self):
        snapshot = snapshot_fixture(self.root / "snapshots", self.record)
        editing = module("metadata_io").export_metadata(
            self.root, snapshot, self.target, "editing"
        )
        p = editing / module("metadata_io").EXPORT_MANIFEST
        value = json.loads(p.read_text())
        value["images"] = [
            {
                "locale": "en-US",
                "slot": "unsupported",
                "file": "en-US/images/unsupported/01.png",
                "remote": {"api_token": "synthetic"},
            }
        ]
        (editing / "en-US/images/unsupported").mkdir(parents=True)
        (editing / value["images"][0]["file"]).write_bytes(b"public")
        write_json(p, value)
        for dry in (True, False):
            with self.subTest(dry=dry), self.assertRaises(ValueError):
                module("metadata_io").import_metadata(
                    self.root,
                    editing,
                    self.target,
                    "new.json",
                    "new-state",
                    metadata_only=True,
                    dry_run=dry,
                )
        self.assertFalse((self.root / "new.json").exists())
        self.assertFalse((self.root / "new-state").exists())

    def test_final_enriched_record_is_validated_before_any_durable_write(self):
        snapshot = snapshot_fixture(self.root / "snapshots", self.record)
        editing = module("metadata_io").export_metadata(
            self.root, snapshot, self.target, "editing"
        )
        original = module("metadata_io").validate_public_metadata

        def reject_enriched(record, target):
            if "source_export" in record:
                raise ValueError("synthetic final provenance rejection")
            return original(record, target)

        with patch.object(
            module("metadata_io"),
            "validate_public_metadata",
            side_effect=reject_enriched,
        ):
            for dry in (True, False):
                with self.subTest(dry=dry), self.assertRaises(ValueError):
                    module("metadata_io").import_metadata(
                        self.root,
                        editing,
                        self.target,
                        "new.json",
                        "new-state",
                        dry_run=dry,
                    )
        self.assertFalse((self.root / "new-state").exists())
        self.assertFalse((self.root / "new.json").exists())

    def test_final_asset_provenance_after_enrichment_rejected_before_history(self):
        from test_assets import png

        data = png()
        image = {"file": "images/01.png", "sha256": hashlib.sha256(data).hexdigest()}
        record = copy.deepcopy(self.record)
        record["images"] = {"en-US": {"APP_IPHONE_65": [image]}}
        snapshot = snapshot_fixture(
            self.root / "snapshots", record, {image["file"]: data}
        )
        editing = module("metadata_io").export_metadata(
            self.root, snapshot, self.target, "editing"
        )
        for field in ("runtime", "catalog"):
            with self.subTest(field=field):
                name = "runtime_inventory" if field == "runtime" else "file_digest"
                bad = (
                    {"app_store_assets/__init__.py": {"api_token": "synthetic"}}
                    if field == "runtime"
                    else {"api_token": "synthetic"}
                )
                with patch.object(module("metadata_io"), name, return_value=bad):
                    for dry in (True, False):
                        with self.subTest(dry=dry), self.assertRaises(ValueError):
                            module("metadata_io").import_metadata(
                                self.root,
                                editing,
                                self.target,
                                "new.json",
                                "new-state",
                                dry_run=dry,
                            )
        self.assertFalse((self.root / "new-state").exists())
        self.assertFalse((self.root / "new.json").exists())

    def test_destination_parent_replaced_after_preflight_never_writes_outside(self):
        from contextlib import contextmanager

        outputs = module("outputs")
        original = outputs.directory
        snapshot = snapshot_fixture(self.root / "snapshots", self.record)
        outside = self.root / "outside-public"
        outside.mkdir()
        for operation in ("export", "publisher", "stage"):
            with self.subTest(operation=operation):
                parent = self.root / ("output-" + operation)
                parent.mkdir()

                @contextmanager
                def replaced(path, *args, **kwargs):
                    if Path(path).is_relative_to(parent):
                        parent.rename(self.root / ("saved-" + operation))
                        parent.symlink_to(outside, target_is_directory=True)
                    with original(path, *args, **kwargs) as fd:
                        yield fd

                with (
                    patch.object(outputs, "directory", side_effect=replaced),
                    self.assertRaises((ValueError, OSError)),
                ):
                    if operation == "export":
                        module("metadata_io").export_metadata(
                            self.root, snapshot, self.target, parent / "new"
                        )
                    elif operation == "publisher":
                        module("publisher").publish_snapshot(
                            parent / "new", self.record, {}
                        )
                    else:
                        source = self.root / "helpers"
                        expected = module("records").inventory(source, ["source.txt"])
                        module("staging").stage_inventory(
                            source, parent / "new", expected
                        )
                self.assertEqual(list(outside.iterdir()), [])
