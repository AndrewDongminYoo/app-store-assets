"""A Google target without a track fails with the module's ValueError contract."""

import copy
import unittest

from offline_support import fixture, module


class GoogleTrackError(unittest.TestCase):
    def setUp(self):
        _, profile = fixture(self, store="google", kind="aab")
        self.target = copy.deepcopy(profile["targets"]["production"])
        del self.target["track"]

    def test_target_identity_reports_a_missing_track(self):
        with self.assertRaisesRegex(ValueError, "invalid Google track"):
            module("profiles").target_identity(self.target)

    def test_target_shape_reports_a_missing_track(self):
        with self.assertRaisesRegex(ValueError, "invalid Google track"):
            module("profiles").validate_target_shape(self.target)


if __name__ == "__main__":
    unittest.main()
