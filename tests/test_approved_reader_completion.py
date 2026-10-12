"""Approved notes/platform/path and bounded snapshot inventory regressions."""

import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from offline_support import fixture, module, write_json
from test_assets import png


class ApprovedReaderCompletion(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)
        self.target = module("profiles").target_identity(
            self.profile["targets"]["production"]
        )
        self.record = json.loads((self.root / "metadata/listing.json").read_text())

    def test_conflicting_notes_reject_before_plan_publication(self):
        self.record["fields"]["en-US"]["release_notes"] = "Field notes"
        self.record["release_notes"] = {"en-US": "Top-level notes"}
        write_json(self.root / "metadata/listing.json", self.record)
        with self.assertRaisesRegex(ValueError, "conflict"):
            module("planning").make_plan(
                self.root, "store-upload.json", "production", "metadata"
            )

    def test_notes_merge_equal_nonoverlap_and_empty_without_mutating_record(self):
        self.record["fields"]["en-US"]["release_notes"] = "Same"
        self.record["fields"]["fr-FR"] = {"release_notes": ""}
        self.record["release_notes"] = {"en-US": "Same", "de-DE": "Top-level"}
        before = copy.deepcopy(self.record)
        self.assertEqual(
            module("metadata").selected_notes(self.record),
            {"en-US": "Same", "fr-FR": "", "de-DE": "Top-level"},
        )
        self.assertEqual(self.record, before)
        (self.root / "notes.txt").write_text("Different")
        self.record.pop("release_notes")
        self.record["changelogs"] = {"en-US": "notes.txt"}
        with self.assertRaisesRegex(ValueError, "conflict"):
            module("metadata").resolve_changelogs(
                self.root, self.record, self.target, {}
            )

    def test_macos_image_plan_rejects_before_listing_or_decode(self):
        self.profile["targets"]["production"]["platform"] = "macos"
        write_json(self.root / "store-upload.json", self.profile)
        (self.root / "metadata/listing.json").unlink()
        with patch.object(
            module("catalog"),
            "image_info",
            side_effect=AssertionError("macos image decoded"),
        ):
            with self.assertRaisesRegex(ValueError, "macos"):
                module("planning").make_plan(
                    self.root, "store-upload.json", "production", "images"
                )

    def test_macos_text_metadata_plan_remains_supported(self):
        self.profile["targets"]["production"]["platform"] = "macos"
        self.record["target"]["platform"] = "macos"
        remote = json.loads((self.root / "remote.json").read_text())
        remote["target"]["platform"] = "macos"
        write_json(self.root / "store-upload.json", self.profile)
        write_json(self.root / "metadata/listing.json", self.record)
        write_json(self.root / "remote.json", remote)
        plan = module("planning").make_plan(
            self.root, "store-upload.json", "production", "metadata"
        )
        self.assertEqual(plan["payload"]["target"]["platform"], "macos")

    def test_noncanonical_root_stops_before_outside_64_character_ancestor(self):
        project = self.root / ("a" * 64) / "project"
        content = project / "editing"
        content.mkdir(parents=True)
        (project / "known").mkdir()
        (content / "notes.txt").write_text("Public notes")
        self.record["changelogs"] = {"en-US": "notes.txt"}
        result = module("metadata").resolve_changelogs(
            project / "known" / "..", self.record, self.target, {}, content_root=content
        )
        self.assertEqual(result["release_notes"], {"en-US": "Public notes"})
        with self.assertRaisesRegex(ValueError, "project"):
            module("metadata").resolve_changelogs(
                project, self.record, self.target, {}, content_root=self.root
            )

    def test_compatibility_env_cannot_inject_decoder_configuration(self):
        image = self.root / "public.png"
        image.write_bytes(png(1, 1))
        result = subprocess.CompletedProcess([], 0, b"1|1|srgb|PNG\n", b"")
        with patch.object(
            module("decoding").subprocess, "run", return_value=result
        ) as decode:
            self.assertEqual(
                module("decoding").image_info(
                    image,
                    env={
                        "HOME": "/untrusted",
                        "MAGICK_CONFIGURE_PATH": "/untrusted",
                        "GH_TOKEN": "synthetic",
                    },
                )[:2],
                (1, 1),
            )
        env = decode.call_args.kwargs["env"]
        self.assertNotEqual(env["HOME"], "/untrusted")
        self.assertNotIn("MAGICK_CONFIGURE_PATH", env)
        self.assertNotIn("GH_TOKEN", env)
