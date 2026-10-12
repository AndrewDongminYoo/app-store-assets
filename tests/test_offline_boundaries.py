"""Behavioral public-boundary regressions; only task-created synthetic inputs."""

import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from offline_support import ROOT, fixture, module, write_json
from test_assets import png


def snapshot_fixture(root, record, files=None):
    files = files or {}
    manifest = {
        "schema_version": 1,
        "type": "snapshot",
        "record": copy.deepcopy(record),
        "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        },
    }
    path = root / module("records").record_digest(manifest)
    path.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_json(path / "manifest.json", manifest)
    return path


class PublicBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )

    def cli(self, command, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module("cli").main(
                [command, "--root", str(self.root), "--target", "production", *extra]
            )
        return code, out.getvalue(), err.getvalue()

    def test_4230952487_url_policy_shared_by_api_plan_and_diff(self):
        base = json.loads((self.root / "metadata/listing.json").read_text())
        write_json(self.root / "before.json", base)
        for query in (
            "api_key=x",
            "access_key=x",
            "auth=x",
            "jwt=x",
            "%61pi_key=x",
            "lang=en&lang=ko",
            "lang=en&auth=x",
        ):
            with self.subTest(query=query):
                record = copy.deepcopy(base)
                record["fields"]["en-US"]["marketing_url"] = (
                    "https://example.invalid/?" + query
                )
                with self.assertRaises(ValueError):
                    module("metadata").validate_public_metadata(record, self.target)
                with self.assertRaises(ValueError):
                    module("metadata").metadata_diff(base, record)
                write_json(self.root / "metadata/listing.json", record)
                code, out, _ = self.cli("plan", "--operation", "metadata")
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                write_json(self.root / "after.json", record)
                code, out, _ = self.cli(
                    "diff", "--before", "before.json", "--after", "after.json"
                )
                self.assertEqual(code, 2)
                self.assertEqual(out, "")

    def test_public_locale_query_and_existing_empty_urls_remain_supported(self):
        for value in (
            "https://example.invalid/privacy?lang=en-US",
            "https://example.invalid/?hl=ko",
            "",
        ):
            clean = module("metadata").normalize_fields(
                {"en-US": {"marketing_url": value}}
            )
            self.assertEqual(clean["en-US"]["marketing_url"], value)

    def test_4230952491_build_unknown_top_and_inspector_values_rejected(self):
        original = json.loads((self.root / "artifact.json").read_text())
        for nested in (False, True):
            with self.subTest(nested=nested):
                record = copy.deepcopy(original)
                if nested:
                    from offline_support import git

                    git(self.root, "init", "-q")
                    git(self.root, "add", "helpers")
                    git(self.root, "commit", "-qm", "synthetic source")
                    record.update(
                        evidence="inspected",
                        native_guards={"app_id": True},
                        source_commit=git(self.root, "rev-parse", "HEAD"),
                        source_inputs=module("records").inventory(
                            self.root, ["helpers"]
                        ),
                        inspector={
                            "name": "synthetic-inspector",
                            "api_token": "synthetic-only",
                        },
                        adapter={"inputs": ["helpers"]},
                    )
                    self.profile["mode"] = "live"
                    write_json(self.root / "store-upload.json", self.profile)
                else:
                    record["api_token"] = "synthetic-only"
                write_json(self.root / "artifact.json", record)
                with self.assertRaises(ValueError):
                    module("planning").make_plan(
                        self.root, "store-upload.json", "production", "binary"
                    )
                code, out, _ = self.cli("plan", "--operation", "binary")
                self.assertEqual(code, 2)
                self.assertEqual(out, "")

    def test_4230952497_asset_record_and_nested_entries_rejected(self):
        data = png()
        item = {
            "file": "images/01.png",
            "locale": "en-US",
            "slot": "APP_IPHONE_65",
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for position in ("record", "asset", "provenance"):
            with self.subTest(position=position):
                record = {
                    "schema_version": 1,
                    "type": "asset-manifest",
                    "target": self.target,
                    "assets": [copy.deepcopy(item)],
                    "provenance": {"status": "unverified-import"},
                }
                selected = (
                    record
                    if position == "record"
                    else record["assets"][0]
                    if position == "asset"
                    else record["provenance"]
                )
                selected["api_token"] = "synthetic-only"
                path = snapshot_fixture(
                    self.root / "assets", record, {item["file"]: data}
                )
                listing = {
                    "schema_version": 1,
                    "type": "metadata",
                    "target": self.target,
                    "fields": {},
                    "images": {
                        "en-US": {
                            item["slot"]: [
                                {
                                    "file": str(
                                        path.relative_to(self.root) / item["file"]
                                    )
                                }
                            ]
                        }
                    },
                }
                write_json(self.root / "metadata/listing.json", listing)
                target = self.profile["targets"]["production"]
                target.update(
                    assets={
                        "manifest": str(path.relative_to(self.root) / "manifest.json")
                    },
                    replacement={
                        "locales": ["en-US"],
                        "slots": [item["slot"]],
                        "allow_delete": False,
                    },
                )
                self.profile["mode"] = "live"
                write_json(self.root / "store-upload.json", self.profile)
                with self.assertRaises(ValueError):
                    module("snapshots").validate_snapshot(path)
                with self.assertRaises(ValueError):
                    module("planning").make_plan(
                        self.root, "store-upload.json", "production", "images"
                    )
                code, out, _ = self.cli("plan", "--operation", "images")
                self.assertEqual(code, 2)
                self.assertEqual(out, "")

    def test_4230952509_parent_replacement_never_reads_outside_marker(self):
        with tempfile.TemporaryDirectory(prefix="public-race-only-") as temp:
            root = Path(temp).resolve()
            project = root / "project"
            project.mkdir()
            public = project / "public"
            public.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (public / "record.json").write_text('{"public":"inside"}')
            (outside / "record.json").write_text('{"public":"outside-marker"}')
            checked = module("records").safe_path(project, "public/record.json")
            public.rename(project / "saved")
            public.symlink_to(outside, target_is_directory=True)
            for function in ("read_text", "read_json", "file_digest"):
                with (
                    self.subTest(function=function),
                    self.assertRaises((ValueError, OSError)),
                ):
                    getattr(module("records"), function)(checked)

    def test_4230952512_every_component_rejected_before_inventory(self):
        for parent in (
            ".env",
            ".env.production",
            "credentials.json",
            "service-account.json",
            "id_rsa",
            "identity.p8",
            "secrets.key",
        ):
            with self.subTest(parent=parent):
                directory = self.root / parent
                directory.mkdir(exist_ok=True)
                (directory / "public.txt").write_text("synthetic only")
                name = parent + "/public.txt"
                with self.assertRaises(ValueError):
                    module("records").safe_path(self.root, name)
                with self.assertRaises(ValueError):
                    module("records").inventory(self.root, [name])

    def test_profile_all_targets_and_runtime_inventory_are_typed(self):
        for kind in ("unselected-target", "runtime-hash", "runtime-url"):
            with self.subTest(kind=kind):
                profile = copy.deepcopy(self.profile)
                if kind == "unselected-target":
                    profile["targets"]["other"] = copy.deepcopy(
                        profile["targets"]["production"]
                    )
                    profile["targets"]["other"]["api_token"] = "synthetic-only"
                elif kind == "runtime-hash":
                    profile["runtime"]["files"]["app_store_assets/__init__.py"] = {
                        "api_token": "synthetic-only"
                    }
                else:
                    profile["runtime"]["url"] = (
                        "https://example.invalid/runtime?api_key=x"
                    )
                write_json(self.root / "store-upload.json", profile)
                with self.assertRaises(ValueError):
                    module("profiles").load_profile(
                        self.root, "store-upload.json", "production"
                    )

    def test_snapshot_rejects_unsupported_opaque_record_type(self):
        path = snapshot_fixture(
            self.root / "snapshots",
            {"type": "unsupported", "api_token": "synthetic-only"},
        )
        with self.assertRaises(ValueError):
            module("snapshots").validate_snapshot(path)

    def test_remote_normalization_cannot_silently_drop_unknown_nested_values(self):
        record = json.loads((self.root / "remote.json").read_text())
        record["images"] = {
            "en-US": {
                "APP_IPHONE_65": [{"id": "public", "api_token": "synthetic-only"}]
            }
        }
        with self.assertRaises(ValueError):
            module("metadata").normalize_remote(record, self.target)


class ReadDistributionTests(unittest.TestCase):
    def test_b1_distributes_no_local_writer_implementation(self):
        for name in ("publisher", "metadata_io", "staging", "write_cli"):
            with self.subTest(name=name):
                self.assertFalse((ROOT / "app_store_assets" / (name + ".py")).exists())
        self.assertFalse(hasattr(module("snapshots"), "publish_snapshot"))

    def test_b1_writer_commands_rejected_before_profile_access(self):
        for command in ("import", "export"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit) as error:
                    module("cli").main(
                        [
                            command,
                            "--root",
                            "/nonexistent-public-root",
                            "--target",
                            "production",
                        ]
                    )
                self.assertEqual(error.exception.code, 2)
