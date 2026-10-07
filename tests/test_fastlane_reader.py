"""Opt-in verification against the real Fastlane 2.240.1 screenshot reader."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_assets import ROOT, png

FASTLANE_SOURCE = os.environ.get('APP_STORE_ASSETS_FASTLANE_SOURCE')
RUBY = os.environ.get('APP_STORE_ASSETS_READER_RUBY', 'ruby')
READER = '''
root, screenshots = ARGV
$LOAD_PATH.unshift(*Dir.glob(File.join(root, "*/lib")))
require "fastlane/version"
abort "Expected Fastlane 2.240.1" unless Fastlane::VERSION == "2.240.1"
require "fastlane_core"
require "deliver/loader"
require "json"
images = Deliver::Loader.load_app_screenshots(screenshots, false)
puts JSON.generate(images.map { |image| image.path.delete_prefix(screenshots + "/") })
'''


@unittest.skipUnless(FASTLANE_SOURCE, 'set APP_STORE_ASSETS_FASTLANE_SOURCE for the real 2.240.1 reader')
class FastlaneReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        (self.source / 'en-US').mkdir(parents=True)
        (self.source / 'en-US/01.png').write_bytes(png())

    def read(self, folder):
        return subprocess.run([RUBY, '-e', READER, FASTLANE_SOURCE, str(folder)], capture_output=True, text=True, timeout=30)

    def prepare(self):
        return subprocess.run([sys.executable, str(ROOT / 'assets.py'), 'prepare-screenshots', '--source', str(self.source), '--out', str(self.root / 'bundles'), '--project', 'fixture', '--bundle-id', 'com.example.fixture'], capture_output=True, text=True, timeout=30)

    def test_prepared_manifest_equals_actual_reader_inventory(self):
        (self.source / 'en-US/02.PNG').write_bytes(png(2048, 2732))
        jpeg = subprocess.run(['magick', str(self.source / 'en-US/01.png'), str(self.source / 'en-US/03.JPEG')], capture_output=True, timeout=30)
        self.assertEqual(jpeg.returncode, 0, jpeg.stderr)
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = Path(json.loads(result.stdout)['bundle'])
        read = self.read(bundle / 'screenshots')
        self.assertEqual(read.returncode, 0, read.stderr)
        inventory = json.loads(read.stdout.splitlines()[-1])
        manifest = json.loads((bundle / 'manifest.json').read_text())
        self.assertEqual(sorted('screenshots/' + name for name in inventory), sorted(asset['file'] for asset in manifest['assets']))
        self.assertEqual(len(inventory), 3)

    def test_hidden_ipad_is_skipped_by_reader_and_blocked_by_preparer(self):
        (self.source / 'en-US/.02.png').write_bytes(png(2048, 2732))
        read = self.read(self.source)
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout.splitlines()[-1]), ['en-US/01.png'])
        prepared = self.prepare()
        self.assertNotEqual(prepared.returncode, 0)
        self.assertIn('hidden screenshot', prepared.stderr)

    def test_extension_and_format_rejections_match_actual_reader(self):
        original = self.source / 'en-US/01.png'
        for filename in ('01.jpg', '01.Png'):
            with self.subTest(filename=filename):
                image = original.with_name(filename)
                original.rename(image)
                try:
                    read = self.read(self.source)
                    self.assertNotEqual(read.returncode, 0)
                    self.assertIn('Canceled uploading screenshots', read.stderr)
                    self.assertNotEqual(self.prepare().returncode, 0)
                finally:
                    image.rename(original)
