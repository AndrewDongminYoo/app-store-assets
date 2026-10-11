"""Output walk errors stay distinct from disk-full and publication collisions."""

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_support import module


class OutputErrorDiagnostics(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_disk_full_and_creation_collisions_keep_original_errno(self):
        outputs = module("outputs")
        for kind in ("write", "rename", "link"):
            error = OSError(
                errno.ENOSPC if kind == "write" else errno.EEXIST, "synthetic failure"
            )
            with self.subTest(operation=kind):
                if kind == "write":
                    patched = patch.object(outputs, "_write", side_effect=error)
                elif kind == "rename":
                    patched = patch.object(
                        outputs,
                        "_exclusive_rename",
                        return_value=lambda *args: (_ for _ in ()).throw(error),
                    )
                else:
                    patched = patch.object(outputs.os, "link", side_effect=error)
                with patched:
                    with self.assertRaises(OSError) as raised:
                        if kind == "link":
                            outputs.write_new_file(self.root / "new.json", b"public")
                        else:
                            outputs.publish_tree(
                                self.root / "editing", {"public.txt": b"public"}
                            )
                self.assertIs(raised.exception, error)
                self.assertFalse(list(self.root.glob(".publish-*")))
                self.assertFalse(list(self.root.glob(".listing-*")))
        with self.assertRaisesRegex(ValueError, "unsafe"):
            with outputs.directory(self.root / "missing"):
                self.fail("missing directory yielded")
