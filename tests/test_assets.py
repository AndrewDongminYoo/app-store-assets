import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def png(width=1242, height=2688, alpha=False, opacity=255):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixel = b'\x20\x40\x60' + (bytes([opacity]) if alpha else b'')
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6 if alpha else 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\x00' + pixel * width) * height))
            + chunk(b'IEND', b''))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        (self.source / 'en-US').mkdir(parents=True)
        self.image = self.source / 'en-US/01.png'
        self.image.write_bytes(png())

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'assets.py'), *args], capture_output=True, text=True, timeout=30)

    def prepare(self, *args):
        return self.run_cli('prepare-screenshots', '--source', str(self.source), '--out', str(self.root / 'bundles'), '--project', 'fixture', '--bundle-id', 'com.example.fixture', *args)

    def test_prepared_tree_has_a_final_hash_and_fastlane_locale_layout(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)['screenshots_path'])
        self.assertEqual((folder / 'en-US/01.png').read_bytes(), self.image.read_bytes())
        manifest = json.loads((folder.parent / 'manifest.json').read_text())
        self.assertEqual(manifest['assets'][0]['sha256'], hashlib.sha256(self.image.read_bytes()).hexdigest())
        self.assertEqual(manifest['provenance']['status'], 'unverified-import')

    def test_opaque_alpha_channel_is_rejected_before_bundle_publication(self):
        self.image.write_bytes(png(alpha=True))
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('alpha channel', result.stderr)
        self.assertFalse(list((self.root / 'bundles').glob('*/manifest.json')))

    def test_normalization_preserves_original_and_hashes_encoded_final(self):
        self.image.write_bytes(png(alpha=True))
        original = self.image.read_bytes()
        result = self.prepare('--normalize-alpha')
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)['screenshots_path'])
        final = (folder / 'en-US/01.png').read_bytes()
        self.assertEqual(self.image.read_bytes(), original)
        self.assertEqual(final[25], 2)
        manifest = json.loads((folder.parent / 'manifest.json').read_text())
        self.assertEqual(manifest['assets'][0]['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(manifest['assets'][0]['sha256'], hashlib.sha256(final).hexdigest())

    def test_corrupt_pixel_stream_is_rejected_even_with_correct_header(self):
        self.image.write_bytes(png()[:45])
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot decode', result.stderr)

    def test_normalization_does_not_invent_a_background_for_transparency(self):
        self.image.write_bytes(png(alpha=True, opacity=128))
        result = self.prepare('--normalize-alpha')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('transparent pixels', result.stderr)

    def test_eleven_images_in_one_display_class_are_rejected(self):
        for index in range(2, 12):
            (self.source / f'en-US/{index:02}.png').write_bytes(self.image.read_bytes())
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('10', result.stderr)

    def test_legacy_nested_artwork_is_flattened_without_metadata_icons(self):
        nested = self.source / 'en-US/images/iphone65'
        nested.mkdir(parents=True)
        self.image.rename(nested / '01.png')
        (self.source / 'en-US/images/icon.png').write_bytes(png(512, 512))
        result = self.prepare('--subdir', 'images/iphone65')
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)['screenshots_path'])
        self.assertEqual([p.name for p in (folder / 'en-US').iterdir()], ['01.png'])

    def test_changed_final_file_fails_bundle_validation(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = Path(json.loads(result.stdout)['screenshots_path'])
        (folder / 'en-US/01.png').write_bytes(png(1284, 2778))
        checked = self.run_cli('validate', str(folder.parent))
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn('hash differs', checked.stderr)

    def test_mixed_framed_names_cannot_silently_drop_unframed_images(self):
        (self.source / 'en-US/02_framed.png').write_bytes(self.image.read_bytes())
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('framed', result.stderr)

    def test_symlinked_input_cannot_escape_the_source_tree(self):
        external = self.root / 'elsewhere.png'
        self.image.rename(external)
        self.image.symlink_to(external)
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside source', result.stderr)


if __name__ == '__main__':
    unittest.main()
