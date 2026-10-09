"""Reported changelog/cache contract regressions; only synthetic local inputs."""

import json
import py_compile
import unittest

from offline_support import fixture, module, write_json
from test_offline_boundaries import snapshot_fixture


class AdditionalReaderBindings(unittest.TestCase):
    def test_snapshot_notes_use_snapshot_bytes_with_root_decoy(self):
        root, profile = fixture(self)
        record = json.loads((root / "remote.json").read_text())
        record["changelogs"] = {"en-US": "notes.txt"}
        folder = snapshot_fixture(
            root / "history", record, {"notes.txt": b"Snapshot approved notes\n"}
        )
        (root / "notes.txt").write_text("Unrelated root notes\n")
        result = module("cli").metadata_input(
            root,
            (folder / "manifest.json").relative_to(root).as_posix(),
            record["target"],
        )
        self.assertEqual(
            result["release_notes"], {"en-US": "Snapshot approved notes\n"}
        )
        (root / "notes.txt").unlink()
        try:
            result = module("cli").metadata_input(
                root,
                (folder / "manifest.json").relative_to(root).as_posix(),
                record["target"],
            )
        except ValueError as error:
            self.fail("valid snapshot notes rejected: " + str(error))
        self.assertEqual(result["release_notes"]["en-US"], "Snapshot approved notes\n")

    def listing(self):
        root, profile = fixture(self, "google")
        path = root / "metadata/listing.json"
        listing = json.loads(path.read_text())
        name = "metadata/en-US/changelogs/9.txt"
        listing["changelogs"] = {"en-US": name}
        write_json(path, listing)
        return root, profile, name

    def test_metadata_plan_captures_notes_and_rejects_later_change(self):
        root, _, name = self.listing()
        plan = module("planning").make_plan(
            root, "store-upload.json", "production", "metadata"
        )
        self.assertIn(name, plan["payload"]["inputs"])
        self.assertEqual(
            plan["payload"]["release_notes"], {"en-US": "Approved notes\n"}
        )
        (root / name).write_text("Changed after approval\n")
        with self.assertRaisesRegex(ValueError, "changed|differs"):
            module("planning").verify_plan(root, plan)

    def test_metadata_notes_missing_or_over_store_limit_fail_closed(self):
        root, _, name = self.listing()
        path = root / name
        path.write_text("x" * 501)
        with self.assertRaises(ValueError):
            module("planning").make_plan(
                root, "store-upload.json", "production", "metadata"
            )
        path.unlink()
        with self.assertRaises(ValueError):
            module("planning").make_plan(
                root, "store-upload.json", "production", "metadata"
            )

    def test_supplied_snapshot_notes_use_their_bound_content_base(self):
        root, profile = fixture(self, "google")
        record = json.loads((root / "remote.json").read_text())
        record["changelogs"] = {"en-US": "notes.txt"}
        folder = snapshot_fixture(
            root / "history", record, {"notes.txt": b"Remote approved notes\n"}
        )
        (root / "notes.txt").write_text("Unrelated root note\n")
        profile["targets"]["production"]["remote"] = (
            (folder / "manifest.json").relative_to(root).as_posix()
        )
        write_json(root / "store-upload.json", profile)
        plan = module("planning").make_plan(
            root, "store-upload.json", "production", "metadata"
        )
        self.assertEqual(
            plan["payload"]["remote"].get("release_notes"),
            {"en-US": "Remote approved notes\n"},
        )

    def test_normal_source_derived_caches_do_not_change_runtime_inventory(self):
        root, profile = fixture(self)
        runtime = root / profile["runtime"]["path"]
        expected = module("identity").runtime_inventory(runtime)
        for name in ("assets.py", "app_store_assets/profiles.py"):
            for optimize in (0, 1, 2):
                for mode in py_compile.PycInvalidationMode:
                    py_compile.compile(
                        str(runtime / name),
                        doraise=True,
                        optimize=optimize,
                        invalidation_mode=mode,
                    )
                    self.assertEqual(
                        module("identity").runtime_inventory(runtime), expected
                    )
        try:
            actual = module("identity").runtime_inventory(runtime)
        except ValueError as error:
            self.fail("normal source-derived cache rejected: " + str(error))
        self.assertEqual(actual, expected)
        self.assertEqual(
            module("identity").runtime_identity(runtime, profile["runtime"])["files"],
            expected,
        )

    def test_tampered_source_less_or_symlink_cache_still_rejects(self):
        root, profile = fixture(self)
        runtime = root / profile["runtime"]["path"]
        source = runtime / "app_store_assets/profiles.py"
        cache = (
            source.parent
            / "__pycache__"
            / (source.stem + "." + __import__("sys").implementation.cache_tag + ".pyc")
        )
        py_compile.compile(str(source), doraise=True)
        original = cache.read_bytes()
        for data in (original[:-1] + bytes([original[-1] ^ 1]), b"bad cache"):
            cache.write_bytes(data)
            with self.assertRaises(ValueError):
                module("identity").runtime_inventory(runtime)
        cache.write_bytes(original)
        extra = cache.with_name(
            "missing." + __import__("sys").implementation.cache_tag + ".pyc"
        )
        extra.write_bytes(original)
        with self.assertRaises(ValueError):
            module("identity").runtime_inventory(runtime)
        extra.unlink()
        cache.unlink()
        cache.symlink_to(source)
        with self.assertRaises(ValueError):
            module("identity").runtime_inventory(runtime)
