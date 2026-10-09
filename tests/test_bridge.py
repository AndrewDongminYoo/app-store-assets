"""Synthetic legacy consumers; no store actions or personal checkout needed."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_assets import ROOT, png


class BridgeTests(unittest.TestCase):
    def call(self, method):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            source = repo / 'source/en-US'
            source.mkdir(parents=True)
            (source / '01.png').write_bytes(png())
            code = '''
require ARGV.fetch(0)
calls = []
begin
  options = AppStoreAssets.public_send(ARGV.fetch(1), repo_root: ARGV.fetch(2),
    project: "synthetic-legacy", bundle_id: "com.example.synthetic",
    source: File.join(ARGV.fetch(2), "source"))
  calls << options if ARGV.fetch(1) == "prepare"
  puts JSON.generate(options: options, calls: calls)
rescue => error
  puts JSON.generate(error: error.message, calls: calls)
  exit 1
end
'''
            result = subprocess.run(['ruby', '-e', code, str(ROOT / 'lib/fastlane_assets.rb'), method, str(repo)],
                                    capture_output=True, text=True, timeout=30)
            return result, json.loads(result.stdout)

    def test_legacy_prepare_cannot_enable_replacement(self):
        result, report = self.call('prepare')
        self.assertNotEqual(result.returncode, 0, report)
        self.assertEqual(report['calls'], [])
        self.assertIn('reviewed plan', report['error'])

    def test_local_preparation_returns_no_transfer_options(self):
        result, report = self.call('prepare_local')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('screenshots_path', report['options'])
        self.assertNotIn('overwrite_screenshots', report['options'])


if __name__ == '__main__':
    unittest.main()
