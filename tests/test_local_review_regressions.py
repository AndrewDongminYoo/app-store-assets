"""B2 whole-candidate review findings: reject before durable effects."""

import contextlib
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch

from offline_support import fixture, module
from test_assets import png
from test_offline_boundaries import snapshot_fixture


class LocalReviewRegressions(unittest.TestCase):
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

    def editing(self, images=False):
        record = copy.deepcopy(self.record)
        files = {}
        if images:
            data = png()
            files = {"images/01.png": data}
            record["images"] = {
                "en-US": {
                    "APP_IPHONE_65": [
                        {
                            "file": "images/01.png",
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    ]
                }
            }
        snapshot = snapshot_fixture(self.root / "source-history", record, files)
        return module("metadata_io").export_metadata(
            self.root, snapshot, self.target, "editing"
        )

    def test_output_ancestor_conflicts_rejected_by_direct_api_and_cli_without_state(
        self,
    ):
        editing = self.editing()
        for entry in ("direct", "cli"):
            for directory in ("metadata", "assets"):
                for dry in (True, False):
                    with self.subTest(entry=entry, directory=directory, dry=dry):
                        state = "new-state-" + entry + "-" + directory + "-" + str(dry)
                        output = state + "/" + directory
                        if entry == "direct":
                            with self.assertRaises(ValueError):
                                module("metadata_io").import_metadata(
                                    self.root,
                                    editing,
                                    self.target,
                                    output,
                                    state,
                                    dry_run=dry,
                                )
                        else:
                            args = [
                                "import",
                                "--root",
                                str(self.root),
                                "--target",
                                "production",
                                "--source",
                                "editing",
                                "--output",
                                output,
                                "--state",
                                state,
                            ] + (["--dry-run"] if dry else [])
                            out = io.StringIO()
                            with (
                                contextlib.redirect_stdout(out),
                                contextlib.redirect_stderr(io.StringIO()),
                            ):
                                code = module("write_cli").main(args)
                            self.assertEqual(code, 2)
                            self.assertEqual(out.getvalue(), "")
                        self.assertFalse((self.root / state).exists())

    def test_oversized_final_manifest_leaves_no_history(self):
        record = dict(self.record, revision="x" * (module("records").TEXT_LIMIT + 1))
        with self.assertRaises(ValueError):
            module("publisher").publish_snapshot(self.root / "new-history", record, {})
        self.assertFalse((self.root / "new-history").exists())

    def test_manifest_at_exact_reader_limit_roundtrips(self):
        empty = dict(self.record, revision="")
        base = module("publisher").snapshot_manifest(empty, {})
        count = module("records").TEXT_LIMIT - len(module("records").canonical(base))
        record = dict(self.record, revision="r" * count)
        path = module("publisher").publish_snapshot(
            self.root / "large-history", record, {}
        )
        self.assertEqual(
            (path / "manifest.json").stat().st_size, module("records").TEXT_LIMIT
        )
        self.assertEqual(module("snapshots").validate_snapshot(path)["record"], record)

    def test_aggregate_budget_prevents_later_source_reads(self):
        source = self.root / "public-files"
        source.mkdir()
        files = {}
        for name in ("one.txt", "two.txt", "three.txt"):
            (source / name).write_bytes(b"public")
            files[name] = source / name
        expected = {name: hashlib.sha256(b"public").hexdigest() for name in files}
        for name in ("publisher", "staging"):
            with self.subTest(name=name):
                product = module(name)
                actual = product.capture_bytes
                seen = []
                captured = []

                def bounded(path, **kwargs):
                    seen.append(kwargs["limit"])
                    data = actual(path, **kwargs)
                    captured.append(len(data))
                    return data

                with (
                    patch.object(product, "FILE_LIMIT", 10),
                    patch.object(product, "capture_bytes", side_effect=bounded),
                    self.assertRaises(ValueError),
                ):
                    if name == "publisher":
                        product.publish_snapshot(
                            self.root / "new-history", self.record, files
                        )
                    else:
                        product.stage_inventory(
                            source, self.root / ("new-" + name), expected
                        )
                self.assertLessEqual(sum(captured), 10)
                self.assertLessEqual(len(seen), 2)
                self.assertEqual(seen, [10, 4])
                self.assertFalse((self.root / "new-history").exists())
                self.assertFalse((self.root / ("new-" + name)).exists())

    def test_supplied_bytes_accounted_before_any_path_capture(self):
        path = self.root / "public.txt"
        path.write_bytes(b"public")
        product = module("publisher")
        actual = product.capture_bytes
        with (
            patch.object(product, "FILE_LIMIT", 10),
            patch.object(product, "capture_bytes", wraps=actual) as captured,
            self.assertRaises(ValueError),
        ):
            product.publish_snapshot(
                self.root / "new-history",
                self.record,
                {"one.txt": b"public", "two.txt": b"public", "later.txt": path},
            )
        captured.assert_not_called()
        self.assertFalse((self.root / "new-history").exists())

    def test_import_and_export_apply_aggregate_image_budget_before_outputs(self):
        editing = self.editing(images=True)
        product = module("metadata_io")
        for operation in ("import", "export"):
            with (
                self.subTest(operation=operation),
                patch.object(product, "FILE_LIMIT", 20, create=True),
                self.assertRaises(ValueError),
            ):
                if operation == "import":
                    product.import_metadata(
                        self.root, editing, self.target, "new.json", "new-state"
                    )
                else:
                    snapshot = next((self.root / "source-history").iterdir())
                    product.export_metadata(
                        self.root, snapshot, self.target, "new-export"
                    )
            self.assertFalse((self.root / "new-state").exists())
            self.assertFalse((self.root / "new.json").exists())
            self.assertFalse((self.root / "new-export").exists())

    def test_build_publication_is_outside_local_metadata_slice_even_with_matching_hash(
        self,
    ):
        build = json.loads((self.root / "artifact.json").read_text())
        data = b"not an IPA container"
        for sha in ("0" * 64, hashlib.sha256(data).hexdigest()):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                module("publisher").publish_snapshot(
                    self.root / "new-history",
                    dict(build, sha256=sha),
                    {"app.ipa": data},
                )
            self.assertFalse((self.root / "new-history").exists())
