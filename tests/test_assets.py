import errno
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("assets", ROOT / "assets.py")
ASSETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSETS)


def png(width=1242, height=2688, alpha=False, opacity=255):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    pixel = b"\x20\x40\x60" + (bytes([opacity]) if alpha else b"")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0),
        )
        + chunk(b"IDAT", zlib.compress((b"\x00" + pixel * width) * height))
        + chunk(b"IEND", b"")
    )


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "en-US").mkdir(parents=True)
        self.image = self.source / "en-US/01.png"
        self.image.write_bytes(png())

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "assets.py"), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def prepare(self, *args):
        return self.run_cli(
            "prepare-screenshots",
            "--source",
            str(self.source),
            "--out",
            str(self.root / "bundles"),
            "--project",
            "fixture",
            "--bundle-id",
            "com.example.fixture",
            *args,
        )

    def test_prepared_tree_has_a_final_hash_and_fastlane_locale_layout(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)["screenshots_path"])
        self.assertEqual(
            (folder / "en-US/01.png").read_bytes(), self.image.read_bytes()
        )
        manifest = json.loads((folder.parent / "manifest.json").read_text())
        self.assertEqual(
            manifest["assets"][0]["sha256"],
            hashlib.sha256(self.image.read_bytes()).hexdigest(),
        )
        self.assertEqual(manifest["provenance"]["status"], "unverified-import")

    def test_opaque_alpha_channel_is_rejected_before_bundle_publication(self):
        self.image.write_bytes(png(alpha=True))
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("alpha channel", result.stderr)
        self.assertFalse(list((self.root / "bundles").glob("*/manifest.json")))

    def test_normalization_preserves_original_and_hashes_encoded_final(self):
        self.image.write_bytes(png(alpha=True))
        original = self.image.read_bytes()
        result = self.prepare("--normalize-alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)["screenshots_path"])
        final = (folder / "en-US/01.png").read_bytes()
        self.assertEqual(self.image.read_bytes(), original)
        self.assertEqual(final[25], 2)
        manifest = json.loads((folder.parent / "manifest.json").read_text())
        self.assertEqual(
            manifest["assets"][0]["source_sha256"], hashlib.sha256(original).hexdigest()
        )
        self.assertEqual(
            manifest["assets"][0]["sha256"], hashlib.sha256(final).hexdigest()
        )

    def test_corrupt_pixel_stream_is_rejected_even_with_correct_header(self):
        self.image.write_bytes(png()[:45])
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot decode", result.stderr)

    def test_normalization_does_not_invent_a_background_for_transparency(self):
        self.image.write_bytes(png(alpha=True, opacity=128))
        result = self.prepare("--normalize-alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("transparent pixels", result.stderr)

    def test_eleven_images_in_one_display_class_are_rejected(self):
        for index in range(2, 12):
            (self.source / f"en-US/{index:02}.png").write_bytes(self.image.read_bytes())
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("10", result.stderr)

    def test_android_bundle_uses_phone_rules_and_preserves_source_on_repeat(self):
        self.image.write_bytes(png(1080, 1920))
        original = self.image.read_bytes()
        first = self.prepare("--platform", "android")
        self.assertEqual(first.returncode, 0, first.stderr)
        bundle = Path(json.loads(first.stdout)["bundle"])
        manifest_bytes = (bundle / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["platform"], "android")
        self.assertEqual(manifest["provenance"]["status"], "unverified-import")
        self.assertEqual(manifest["assets"][0]["profile"], "phoneScreenshots")
        self.assertEqual(manifest["assets"][0]["size"], [1080, 1920])
        self.assertEqual(
            manifest["assets"][0]["sha256"], hashlib.sha256(original).hexdigest()
        )
        self.assertEqual(
            manifest["assets"][0]["source_sha256"], hashlib.sha256(original).hexdigest()
        )
        self.assertEqual((bundle / "screenshots/en-US/01.png").read_bytes(), original)
        self.assertEqual(self.run_cli("validate", str(bundle)).returncode, 0)
        second = self.prepare("--platform", "android")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["bundle"], str(bundle))
        self.assertEqual((bundle / "manifest.json").read_bytes(), manifest_bytes)
        self.assertEqual(self.image.read_bytes(), original)

    def test_explicit_ios_keeps_the_legacy_manifest_and_bundle_identity(self):
        legacy = self.prepare()
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        explicit = self.prepare("--platform", "ios")
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(json.loads(explicit.stdout), json.loads(legacy.stdout))
        bundle = Path(json.loads(legacy.stdout)["bundle"])
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertNotIn("platform", manifest)

    def test_android_dimension_boundaries_and_landscape_are_supported(self):
        for width, height in [(320, 320), (3840, 1920), (1920, 1080)]:
            with self.subTest(size=(width, height)):
                self.image.write_bytes(png(width, height))
                result = self.prepare("--platform", "android")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_android_dimensions_and_aspect_are_rejected_before_publication(self):
        for width, height, message in [
            (319, 400, "dimensions"),
            (1921, 3841, "dimensions"),
            (320, 641, "aspect"),
        ]:
            with self.subTest(size=(width, height)):
                self.image.write_bytes(png(width, height))
                result = self.prepare("--platform", "android")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(list((self.root / "bundles").glob("*/manifest.json")))

    def test_android_eight_images_are_accepted_but_nine_are_rejected(self):
        self.image.write_bytes(png(320, 480))
        for index in range(2, 9):
            (self.source / f"en-US/{index:02}.png").write_bytes(self.image.read_bytes())
        eight = self.prepare("--platform", "android")
        self.assertEqual(eight.returncode, 0, eight.stderr)
        bundle = Path(json.loads(eight.stdout)["bundle"])
        before = (bundle / "manifest.json").read_bytes()
        (self.source / "en-US/09.png").write_bytes(self.image.read_bytes())
        nine = self.prepare("--platform", "android")
        self.assertNotEqual(nine.returncode, 0)
        self.assertIn("8", nine.stderr)
        self.assertEqual((bundle / "manifest.json").read_bytes(), before)
        self.assertEqual(
            [
                file.resolve()
                for file in (self.root / "bundles").glob("*/manifest.json")
            ],
            [bundle / "manifest.json"],
        )

    def test_android_does_not_apply_apple_framed_filename_filter(self):
        self.image.write_bytes(png(320, 480))
        (self.source / "en-US/02_framed.png").write_bytes(self.image.read_bytes())
        result = self.prepare("--platform", "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["assets"], 2)

    def test_android_nested_phone_images_exclude_other_play_artwork(self):
        nested = self.source / "en-US/images/phoneScreenshots"
        nested.mkdir(parents=True)
        self.image.write_bytes(png(1080, 1920))
        self.image.rename(nested / "01.png")
        (nested.parent / "icon.png").write_bytes(png(512, 512, alpha=True))
        (nested.parent / "featureGraphic.png").write_bytes(png(1024, 500))
        result = self.prepare(
            "--platform", "android", "--subdir", "images/phoneScreenshots"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["assets"], 1)

    def test_android_opaque_alpha_normalization_and_transparency_rejection(self):
        self.image.write_bytes(png(320, 480, alpha=True))
        original = self.image.read_bytes()
        rejected = self.prepare("--platform", "android")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("alpha", rejected.stderr)
        normalized = self.prepare("--platform", "android", "--normalize-alpha")
        self.assertEqual(normalized.returncode, 0, normalized.stderr)
        bundle = Path(json.loads(normalized.stdout)["bundle"])
        self.assertEqual(
            (bundle / "screenshots/en-US/01.png").read_bytes()[24:26], bytes([8, 2])
        )
        self.assertEqual(self.image.read_bytes(), original)
        self.image.write_bytes(png(320, 480, alpha=True, opacity=128))
        transparent = self.prepare("--platform", "android", "--normalize-alpha")
        self.assertNotEqual(transparent.returncode, 0)
        self.assertIn("transparent pixels", transparent.stderr)

    def test_android_requires_rgb24_png_but_accepts_jpeg(self):
        self.image.write_bytes(png(320, 480))
        palette = self.image.with_name("palette.png")
        subprocess.run(
            ["magick", str(self.image), "PNG8:" + str(palette)],
            check=True,
            capture_output=True,
        )
        self.image.unlink()
        rejected = self.prepare("--platform", "android")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("24-bit RGB", rejected.stderr)
        jpeg = self.image.with_suffix(".jpg")
        subprocess.run(
            ["magick", str(palette), str(jpeg)], check=True, capture_output=True
        )
        palette.unlink()
        accepted = self.prepare("--platform", "android")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_android_manifest_platform_cannot_be_downgraded_or_switched(self):
        self.image.write_bytes(png(320, 480))
        result = self.prepare("--platform", "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = Path(json.loads(result.stdout)["bundle"])
        manifest_file = bundle / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        for schema, platform in [(1, "android"), (2, "ios"), (2, None), (3, "android")]:
            with self.subTest(schema=schema, platform=platform):
                changed = dict(manifest, schema_version=schema, platform=platform)
                manifest_file.write_text(json.dumps(changed))
                checked = self.run_cli("validate", str(bundle))
                self.assertNotEqual(checked.returncode, 0)
                self.assertIn("schema/platform", checked.stderr)

    def test_android_validator_rechecks_dimensions_after_manifest_hash_changes(self):
        self.image.write_bytes(png(320, 480))
        result = self.prepare("--platform", "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = Path(json.loads(result.stdout)["bundle"])
        image = bundle / "screenshots/en-US/01.png"
        image.write_bytes(png(320, 641))
        manifest_file = bundle / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["assets"][0]["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
        manifest["assets"][0]["size"] = [320, 641]
        manifest_file.write_text(json.dumps(manifest))
        checked = self.run_cli("validate", str(bundle))
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("aspect", checked.stderr)

    def test_legacy_nested_artwork_is_flattened_without_metadata_icons(self):
        nested = self.source / "en-US/images/iphone65"
        nested.mkdir(parents=True)
        self.image.rename(nested / "01.png")
        (self.source / "en-US/images/icon.png").write_bytes(png(512, 512))
        result = self.prepare("--subdir", "images/iphone65")
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)["screenshots_path"])
        self.assertEqual([p.name for p in (folder / "en-US").iterdir()], ["01.png"])

    def test_changed_final_file_fails_bundle_validation(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)["screenshots_path"])
        (folder / "en-US/01.png").write_bytes(png(1284, 2778))
        checked = self.run_cli("validate", str(folder.parent))
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("hash differs", checked.stderr)

    def test_mixed_framed_names_cannot_silently_drop_unframed_images(self):
        (self.source / "en-US/02_framed.png").write_bytes(self.image.read_bytes())
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("framed", result.stderr)

    def test_symlinked_input_cannot_escape_the_source_tree(self):
        external = self.root / "elsewhere.png"
        self.image.rename(external)
        self.image.symlink_to(external)
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside source", result.stderr)

    def test_hidden_ipad_image_is_rejected_before_publication(self):
        (self.source / "en-US/.02.png").write_bytes(png(2048, 2732))
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hidden screenshot", result.stderr)
        self.assertFalse(list((self.root / "bundles").glob("*/manifest.json")))

    def test_format_and_extension_must_match_fastlane(self):
        for filename, message in [("01.jpg", "format"), ("01.Png", "extension")]:
            with self.subTest(filename=filename):
                image = self.image.with_name(filename)
                self.image.rename(image)
                try:
                    result = self.prepare()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)
                    self.assertFalse(
                        list((self.root / "bundles").glob("*/manifest.json"))
                    )
                finally:
                    image.rename(self.image)

    def test_validation_also_rejects_hidden_screenshots(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = Path(json.loads(result.stdout)["bundle"])
        image = bundle / "screenshots/en-US/01.png"
        image.rename(image.with_name(".02.png"))
        manifest_file = bundle / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["assets"][0]["file"] = "screenshots/en-US/.02.png"
        manifest_file.write_text(json.dumps(manifest))
        checked = self.run_cli("validate", str(bundle))
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("hidden screenshot", checked.stderr)

    def test_cache_image_and_manifest_cannot_be_changed_together(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = Path(json.loads(result.stdout)["bundle"])
        image = bundle / "screenshots/en-US/01.png"
        image.write_bytes(png(1284, 2778))
        manifest_file = bundle / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["assets"][0]["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
        manifest["assets"][0]["size"] = [1284, 2778]
        manifest_file.write_text(json.dumps(manifest))
        self.assertEqual(self.run_cli("validate", str(bundle)).returncode, 0)
        repeated = self.prepare()
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("expected manifest", repeated.stderr)
        self.assertEqual(image.read_bytes(), png(1284, 2778))

    def test_normalization_is_reproducible_across_clock_ticks(self):
        self.image.write_bytes(png(alpha=True))
        first = self.prepare("--normalize-alpha")
        self.assertEqual(first.returncode, 0, first.stderr)
        first_bundle = Path(json.loads(first.stdout)["bundle"])
        time.sleep(1.1)
        second = self.prepare(
            "--normalize-alpha", "--out", str(self.root / "fresh-bundles")
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        second_bundle = Path(json.loads(second.stdout)["bundle"])
        self.assertEqual(first_bundle.name, second_bundle.name)
        self.assertEqual(
            (first_bundle / "manifest.json").read_bytes(),
            (second_bundle / "manifest.json").read_bytes(),
        )
        final = first_bundle / "screenshots/en-US/01.png"
        self.assertEqual(
            final.read_bytes(),
            (second_bundle / "screenshots/en-US/01.png").read_bytes(),
        )
        pixels = subprocess.run(
            ["magick", str(final), "-depth", "8", "rgb:-"],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(pixels.returncode, 0, pixels.stderr)
        self.assertEqual(pixels.stdout, b"\x20\x40\x60" * 1242 * 2688)

    def test_concurrent_preparations_reuse_the_validated_winner(self):
        args = SimpleNamespace(
            source=self.source,
            out=self.root / "bundles",
            subdir=".",
            project="fixture",
            bundle_id="com.example.fixture",
            normalize_alpha=False,
        )
        barrier = threading.Barrier(2)
        rename = Path.rename

        def simultaneous_rename(folder, destination):
            barrier.wait(timeout=10)
            return rename(folder, destination)

        with patch.object(Path, "rename", simultaneous_rename), ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            futures = [pool.submit(ASSETS.prepare, args) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(results[0], results[1])
        ASSETS.validate(results[0]["bundle"])
        self.assertEqual(
            [p.resolve() for p in (self.root / "bundles").iterdir()],
            [Path(results[0]["bundle"])],
        )

    def test_rename_race_does_not_reuse_a_corrupt_winner(self):
        args = SimpleNamespace(
            source=self.source,
            out=self.root / "bundles",
            subdir=".",
            project="fixture",
            bundle_id="com.example.fixture",
            normalize_alpha=False,
        )

        def corrupt_winner(folder, destination):
            destination.mkdir()
            (destination / "manifest.json").write_text("{}")
            raise OSError(errno.ENOTEMPTY, "Directory not empty")

        with patch.object(Path, "rename", corrupt_winner):
            with self.assertRaisesRegex(ValueError, "unsupported manifest"):
                ASSETS.prepare(args)

    def test_unrelated_rename_error_is_not_treated_as_a_race(self):
        args = SimpleNamespace(
            source=self.source,
            out=self.root / "bundles",
            subdir=".",
            project="fixture",
            bundle_id="com.example.fixture",
            normalize_alpha=False,
        )
        error = OSError(errno.EACCES, "Permission denied")
        with patch.object(Path, "rename", side_effect=error):
            with self.assertRaises(OSError) as raised:
                ASSETS.prepare(args)
        self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
