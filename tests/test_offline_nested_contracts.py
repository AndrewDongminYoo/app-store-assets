"""Complete input objects reject nested unknown/private or untyped values."""

import ast
import copy
import json
import unittest
from unittest.mock import patch

from offline_support import ROOT, fixture, module
from test_assets import png


class NestedContractTests(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )

    def test_catalog_complete_nested_object_is_validated_before_rule_use(self):
        original = json.loads((ROOT / "catalog/store-rules-v1.json").read_text())
        for position in (
            "top",
            "source",
            "store",
            "slot",
            "limits",
            "minimum",
            "required",
        ):
            with self.subTest(position=position):
                bad = copy.deepcopy(original)
                if position == "top":
                    bad["api_token"] = "synthetic"
                elif position == "source":
                    bad["sources"]["apple_text"] += "?api_key=x"
                elif position == "store":
                    bad["stores"]["apple"]["api_token"] = "synthetic"
                elif position == "slot":
                    bad["stores"]["apple"]["slots"]["APP_IPHONE_65"]["api_token"] = (
                        "synthetic"
                    )
                elif position == "limits":
                    bad["stores"]["apple"]["text_limits"]["name"] = [True, "characters"]
                elif position == "minimum":
                    bad["stores"]["apple"]["text_minimums"]["name"] = {
                        "api_token": "synthetic"
                    }
                else:
                    bad["stores"]["apple"]["submission_required"]["iphone"] = {
                        "api_token": "synthetic"
                    }
                with (
                    patch.object(module("catalog"), "read_json", return_value=bad),
                    self.assertRaises(ValueError),
                ):
                    module("catalog").rules()

    def test_direct_image_api_rejects_unknown_and_untyped_annotations(self):
        image = self.root / "image.png"
        image.write_bytes(png())
        entry = {"file": "image.png", "locale": "en-US", "slot": "APP_IPHONE_65"}
        for key, value in (
            ("api_token", "synthetic"),
            ("provider_sha256", {"api_token": "synthetic"}),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                module("catalog").validate_images(
                    self.root, [dict(entry, **{key: value})], "apple"
                )

    def test_direct_container_classifier_never_follows_leaf_or_parent_symlink(self):
        outside = self.root / "artifacts"
        linked = self.root / "linked"
        linked.symlink_to(outside, target_is_directory=True)
        leaf = self.root / "linked.ipa"
        leaf.symlink_to(outside / "app.ipa")
        for path in (leaf, linked / "app.ipa"):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                module("artifacts").container_kind(path)

    def test_metadata_final_provenance_types_and_every_nested_container(self):
        original = json.loads((self.root / "metadata/listing.json").read_text())
        for key, value in (
            ("schema_version", True),
            ("source_export", {"api_token": "synthetic"}),
            ("source_snapshot", ".env.production/public.json"),
            ("inputs", {"public.txt": []}),
            ("images", {"en-US": {"APP_IPHONE_65": [{"sha256": "bad"}]}}),
            (
                "binary",
                {
                    "app_id": self.target["app_id"],
                    "platform": "ios",
                    "version": dict(self.target["version"], api_token="synthetic"),
                    "processing_state": "valid",
                },
            ),
            ("effects", [{}]),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                module("metadata").validate_public_metadata(
                    dict(original, **{key: value}), self.target
                )

    def test_build_asset_and_dispatch_types_fail_as_contract_errors(self):
        original = json.loads((self.root / "artifact.json").read_text())
        for key in ("kind", "evidence"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                module("record_types").validate_build(dict(original, **{key: []}))
        with self.assertRaises(ValueError):
            module("record_types").validate_record({"type": []})

    def test_runtime_parent_symlink_is_not_canonicalized_after_approval(self):
        runtime = self.root / "tools/app-store-assets"
        old = self.root / "saved-tools"
        (self.root / "tools").rename(old)
        (self.root / "tools").symlink_to(old, target_is_directory=True)
        for name in ("runtime_inventory", "runtime_identity", "git"):
            with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                args = (
                    (runtime, self.profile["runtime"])
                    if name == "runtime_identity"
                    else (runtime, "rev-parse", "HEAD")
                    if name == "git"
                    else (runtime,)
                )
                getattr(module("identity"), name)(*args)

    def test_snapshot_manifest_changed_after_parse_is_rejected_by_direct_reader(self):
        from test_offline_boundaries import snapshot_fixture

        record = json.loads((self.root / "metadata/listing.json").read_text())
        folder = snapshot_fixture(self.root / "history", record)
        original = module("snapshots").tree_inventory

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            (folder / "manifest.json").write_text("{}")
            return result

        with (
            patch.object(module("snapshots"), "tree_inventory", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            module("snapshots").validate_snapshot(folder)

    def test_doctor_serialized_inventory_matches_parsed_profile_capture(self):
        import contextlib
        import io

        original = module("cli").inventory
        profile_path = self.root / "store-upload.json"
        data = profile_path.read_bytes()

        def changed(*args, **kwargs):
            other = copy.deepcopy(self.profile)
            other["project"] = "other-public"
            profile_path.write_text(json.dumps(other))
            result = original(*args, **kwargs)
            profile_path.write_bytes(data)
            return result

        out = io.StringIO()
        with (
            patch.object(module("cli"), "inventory", side_effect=changed),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = module("cli").main(
                ["doctor", "--root", str(self.root), "--target", "production"]
            )
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")

    def test_direct_decoder_rejects_parent_symlink_before_native_read(self):
        images = self.root / "images"
        images.mkdir()
        (images / "public.png").write_bytes(png())
        linked = self.root / "linked-images"
        linked.symlink_to(images, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            module("decoding").image_info(linked / "public.png")

    def test_read_package_has_no_eager_writer_imports(self):
        for path in (ROOT / "app_store_assets").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(
                    any(
                        "app_store_assets_local" in name
                        or name.split(".")[-1]
                        in {"publisher", "metadata_io", "staging", "write_cli"}
                        for name in names
                    ),
                    path.name,
                )
