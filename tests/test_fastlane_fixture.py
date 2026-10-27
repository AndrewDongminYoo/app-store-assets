import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_fastlane


class FastlaneFixtureTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.personal = Path(self.scratch.name)
        self.fastfile = self.personal / "mirae/ios/fastlane/Fastfile"
        self.fastfile.parent.mkdir(parents=True)
        self.helper = self.personal / "mirae/scripts/store_assets/fastlane.rb"
        self.helper.parent.mkdir(parents=True)
        self.helper.write_text(
            'def fixture_helper; UI.user_error!("copied helper reached"); end\n'
        )
        self.fixture = test_fastlane.FastlaneIntegrationTests()
        personal = patch.object(test_fastlane, "PERSONAL", self.personal)
        personal.start()
        self.addCleanup(personal.stop)

    def test_required_local_helper_runs_from_copied_checkout(self):
        self.fastfile.write_text(
            """require_relative "../../scripts/store_assets/fastlane"
platform :ios do
  lane(:metadata) { |options| fixture_helper }
end
"""
        )
        try:
            result, report = self.fixture.lane("mirae")
        except ValueError as error:
            self.fail(f"Copied Fastfile could not run its local helper: {error}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("copied helper reached", result.stderr)
        self.assertEqual(report, {"uploads": [], "review_reads": 0})

    def test_invalid_json_reports_subprocess_evidence(self):
        cases = [
            ('raise "fixture loading failed"\n', 1, "fixture loading failed"),
            (
                'puts "not-json"\nplatform(:ios) { lane(:metadata) { |options| } }\n',
                0,
                "not-json",
            ),
        ]
        for source, exit_code, diagnostic in cases:
            with self.subTest(exit_code=exit_code):
                self.fastfile.write_text(source)
                with self.assertRaises(AssertionError) as raised:
                    self.fixture.lane("mirae")
                message = str(raised.exception)
                self.assertIn("mirae", message)
                self.assertIn(f"exit {exit_code}", message)
                self.assertIn(diagnostic, message)
                self.assertIn("stdout:", message)
                self.assertIn("stderr:", message)


if __name__ == "__main__":
    unittest.main()
