"""The local write CLI prints one line and exits 2 for reachable failures."""

import subprocess
import unittest
from unittest.mock import patch

from offline_support import fixture, module


class WriteCliFailureStatus(unittest.TestCase):
    def setUp(self):
        self.root, _ = fixture(self)

    def run_cli(self):
        argv = ["import", "--root", str(self.root), "--target", "production"]
        argv += ["--source", "editing", "--output", "listing.json"]
        return module("write_cli").main(argv)

    def test_subprocess_timeout_returns_status_two(self):
        error = subprocess.TimeoutExpired(["magick"], 60)
        with patch.object(module("write_cli"), "local_context", side_effect=error):
            with patch("sys.stderr"):
                self.assertEqual(self.run_cli(), 2)

    def test_deeply_nested_json_returns_status_two(self):
        (self.root / "store-upload.json").write_text("[" * 100000 + "]" * 100000)
        with patch("sys.stderr"):
            self.assertEqual(self.run_cli(), 2)


if __name__ == "__main__":
    unittest.main()
