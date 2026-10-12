"""Public URL hostnames must be syntactically valid ASCII DNS names."""

import json
import unittest

from offline_support import fixture, module, write_json

REJECTED = (
    "https://evil|host",
    "https://a..b",
    "https://example.com.",
    "https://-a.com",
    "https://a-.com",
    "https://" + "a" * 64 + ".com",
    "https://" + ".".join(["a" * 63] * 3 + ["a" * 62]),
    "https://xn--bcher-kva.example",
    "https://example.xn--p1ai",
    "https://exämple.com",
    "https://Kexample.com",
    "https://127.0.0.1",
    "https://example.123",
    "https://[::1]",
    "https://[v1.foo]",
    "https://[v1.foo]:443/x",
    "https://a_b.example",
)
ACCEPTED = (
    "https://example.com",
    "https://support.google.com/path",
    "https://a-b.example.invalid",
    "https://localhost",
    "https://EXAMPLE.com",
    "https://example.com:8443/x",
    "https://" + ".".join(["a" * 63] * 3 + ["a" * 61]),
)


class PublicUrlHostname(unittest.TestCase):
    def setUp(self):
        self.public_url = module("contracts").public_url

    def test_rejected_hostnames(self):
        self.assertEqual(len(REJECTED[6]) - len("https://"), 254)
        for origin in (False, True):
            for value in REJECTED:
                with self.subTest(value=value, origin=origin):
                    with self.assertRaisesRegex(
                        ValueError, "^invalid public URL hostname$"
                    ):
                        self.public_url(value, origin=origin)

    def test_accepted_hostnames(self):
        self.assertEqual(len(ACCEPTED[-1]) - len("https://"), 253)
        for value in ACCEPTED:
            with self.subTest(value=value):
                self.assertEqual(self.public_url(value), value)
        self.assertEqual(
            self.public_url("https://example.com", origin=True), "https://example.com"
        )

    def test_metadata_plan_rejects_invalid_support_hostname(self):
        root, _ = fixture(self)
        path = root / "metadata/listing.json"
        listing = json.loads(path.read_text())
        listing["fields"]["en-US"]["support_url"] = "https://evil|host/contact"
        write_json(path, listing)
        with self.assertRaisesRegex(ValueError, "invalid public URL hostname"):
            module("planning").make_plan(
                root, "store-upload.json", "production", "metadata"
            )


if __name__ == "__main__":
    unittest.main()
