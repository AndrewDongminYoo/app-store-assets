"""Reachable reader failures print one line and exit with status 2."""

import subprocess
import unittest
from unittest.mock import patch

from offline_support import fixture, module


class CliFailureStatus(unittest.TestCase):
    def setUp(self):
        self.root, self.profile = fixture(self)

    def run_cli(self):
        return module("cli").main(
            ["doctor", "--root", str(self.root), "--target", "production"]
        )

    def test_subprocess_timeout_returns_status_two(self):
        error = subprocess.TimeoutExpired(["git"], 30)
        with patch.object(module("cli"), "local_context", side_effect=error):
            with patch("sys.stderr"):
                self.assertEqual(self.run_cli(), 2)

    def test_deeply_nested_json_returns_status_two(self):
        (self.root / "store-upload.json").write_text("[" * 100000 + "]" * 100000)
        with patch("sys.stderr"):
            self.assertEqual(self.run_cli(), 2)


if __name__ == "__main__":
    unittest.main()
