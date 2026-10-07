import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_assets import ROOT, png

PERSONAL = Path(os.environ['APP_STORE_ASSETS_PERSONAL_ROOT']) if os.environ.get('APP_STORE_ASSETS_PERSONAL_ROOT') else None


@unittest.skipUnless(PERSONAL, 'set APP_STORE_ASSETS_PERSONAL_ROOT for actual personal Fastfile integration')
class FastlaneIntegrationTests(unittest.TestCase):
    def lane(self, project, image=None, filename='01.png', extra_images=None, **options):
        with tempfile.TemporaryDirectory() as scratch:
            repo = Path(scratch) / project
            location = 'fastlane/Fastfile' if project == 'kkomkkomi' else 'ios/fastlane/Fastfile'
            fastfile = repo / location
            fastfile.parent.mkdir(parents=True)
            shutil.copyfile(PERSONAL / project / location, fastfile)
            source = repo / ('fastlane/metadata/ios/en-US/images/iphone65' if project == 'mirae' else 'fastlane/screenshots/ios/en-US')
            source.mkdir(parents=True)
            (source / filename).write_bytes(image if image is not None else png())
            for extra_name, data in (extra_images or {}).items():
                (source / extra_name).write_bytes(data)
            (repo / 'pubspec.yaml').write_text('version: 1.0.0+1\n')
            env = dict(os.environ, APP_STORE_ASSETS_ROOT=str(ROOT))
            result = subprocess.run(['ruby', str(ROOT / 'tests/fastlane_harness.rb'), str(fastfile), json.dumps(options)], capture_output=True, text=True, env=env, timeout=30)
            report = json.loads(result.stdout)
            # Read the actual folder passed to the external upload action.
            if report['uploads'] and report['uploads'][0].get('screenshots_path') and not report['uploads'][0].get('skip_screenshots'):
                tree = Path(report['uploads'][0]['screenshots_path'])
                report['uploaded_files'] = [str(p.relative_to(tree)) for p in tree.rglob('*') if p.is_file()]
                data = (tree / 'en-US/01.png').read_bytes()
                report['uploaded_png_color'] = data[25] if len(data) > 25 else None
            return result, report

    def test_legacy_metadata_lanes_are_blocked_before_replacement(self):
        for project in ('mirae', 'ttush_push', 'kkomkkomi'):
            with self.subTest(project=project):
                result, report = self.lane(project)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['uploads'], [])
                self.assertIn('reviewed plan', result.stderr)

    def test_invalid_images_stop_before_upload_or_account_lookup(self):
        for project in ('mirae', 'ttush_push', 'kkomkkomi'):
            with self.subTest(project=project):
                result, report = self.lane(project, image=png(500, 500))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['uploads'], [])
                self.assertEqual(report['review_reads'], 0)
                self.assertIn('reviewed plan', result.stderr)

    def test_legacy_alpha_inputs_do_not_authorize_replacement(self):
        result, report = self.lane('ttush_push', image=png(alpha=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['uploads'], [])

    def test_reader_incompatible_inputs_stop_before_external_calls(self):
        cases = [
            ({'extra_images': {'.02.png': png(2048, 2732)}}, 'hidden screenshot'),
            ({'filename': '01.jpg'}, 'format'),
            ({'filename': '01.Png'}, 'extension'),
        ]
        for project in ('mirae', 'ttush_push', 'kkomkkomi'):
            for inputs, message in cases:
                with self.subTest(project=project, inputs=message):
                    result, report = self.lane(project, **inputs)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(report['uploads'], [])
                    self.assertEqual(report['review_reads'], 0)
                    self.assertIn('reviewed plan', result.stderr)

    def test_metadata_only_option_does_not_require_a_screenshot_tool(self):
        for project in ('mirae', 'ttush_push', 'kkomkkomi'):
            with self.subTest(project=project):
                result, report = self.lane(project, image=b'broken', skip_screenshots=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(report['uploads'][0]['skip_screenshots'])


if __name__ == '__main__':
    unittest.main()
