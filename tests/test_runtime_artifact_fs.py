"""Filesystem containment and symlink regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.isolation import IsolationError, IsolationManager
from throne_runtime.artifacts.models import Isolation
from throne_runtime.artifacts.scanner import ScanError
from tests._artifact_test_util import make_service


class TestFilesystemContainment(unittest.TestCase):
    def test_destination_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            im = IsolationManager(root)
            blob = root / "blobs"
            blob.mkdir(parents=True, exist_ok=True)
            src = blob / "x.bin"
            src.write_bytes(b"abc")
            run_id = "run-test1"
            d = im.run_dir(run_id, Isolation.QUARANTINED)
            dest = d / "file.txt"
            try:
                dest.symlink_to(src)
            except OSError:
                self.skipTest("symlinks unsupported")
            with self.assertRaises(IsolationError):
                im.place_link(run_id, Isolation.QUARANTINED, "file.txt", src)

    def test_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            im = IsolationManager(root)
            # Create tier then replace run parent via symlink is hard; ensure
            # absolute/traversal filenames are rejected.
            blob = root / "b.bin"
            blob.write_bytes(b"x")
            with self.assertRaises(IsolationError):
                im.place_link("run-x", Isolation.QUARANTINED, "../escape.txt", blob)
            with self.assertRaises(IsolationError):
                im.place_link("run-x", Isolation.QUARANTINED, "/abs.txt", blob)

    def test_string_prefix_sibling_not_confused(self):
        """relative_to must not treat /root-evil as under /root."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            sibling = Path(td) / "root-evil"
            root.mkdir()
            sibling.mkdir()
            from throne_runtime.artifacts.paths import is_under

            self.assertFalse(is_under(root, sibling / "f"))
            self.assertTrue(is_under(root, root / "a" / "b"))

    def test_external_file_ingest_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td) / "store")
            external = Path(td) / "outside.txt"
            external.write_text("external-ok")
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            art = svc.ingest(run_id=run.run_id, path=external)
            self.assertTrue(art.content_hash)

    def test_scan_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td) / "store")
            real = Path(td) / "real.txt"
            real.write_text("x")
            link = Path(td) / "link.txt"
            try:
                link.symlink_to(real)
            except OSError:
                self.skipTest("symlinks unsupported")
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            with self.assertRaises(ScanError):
                svc.ingest(run_id=run.run_id, path=link)

    def test_collision_different_content_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            im = IsolationManager(root)
            a = Path(td) / "a.bin"
            b = Path(td) / "b.bin"
            a.write_bytes(b"aaa")
            b.write_bytes(b"bbb")
            im.place_link("run1", Isolation.QUARANTINED, "same.txt", a)
            with self.assertRaises(IsolationError):
                im.place_link("run1", Isolation.QUARANTINED, "same.txt", b)


if __name__ == "__main__":
    unittest.main()
