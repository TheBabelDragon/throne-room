"""Scanner safety: path traversal, symlinks, archives."""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from throne_runtime.artifacts.scanner import ArtifactScanner, ScanError


class TestScanner(unittest.TestCase):
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scanner = ArtifactScanner(root)
            f = root / "ok.txt"
            f.write_text("x")
            with self.assertRaises(ScanError):
                scanner.scan_file(f, relative_name="../escape.txt")

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            root.mkdir()
            outside = Path(td) / "secret"
            outside.write_text("secret")
            link = root / "link"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlinks not supported")
            scanner = ArtifactScanner(root)
            with self.assertRaises(ScanError):
                scanner.scan_file(link)

    def test_unsafe_archive_paths_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zpath = root / "bad.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("../../etc/passwd", "x")
            scanner = ArtifactScanner(root)
            with self.assertRaises(ScanError):
                scanner.inspect_archive_paths(zpath)


if __name__ == "__main__":
    unittest.main()
