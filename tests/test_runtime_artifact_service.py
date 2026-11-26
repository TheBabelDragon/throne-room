"""Service-level acceptance tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import Isolation
from throne_runtime.artifacts.service import ArtifactService

_POLICY = Path(__file__).resolve().parents[1] / "policies"


def _svc(root: Path) -> ArtifactService:
    return ArtifactService(root=root, policy_dir=_POLICY)


class TestService(unittest.TestCase):
    def test_ingest_and_list(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            svc = _svc(root)
            run = svc.create_run(project="Spacetime", subsystem="test", run_type="unit")
            f = root / "sample.txt"
            f.write_text("hello artifacts")
            art = svc.ingest(run_id=run.run_id, path=f)
            self.assertEqual(art.isolation, Isolation.QUARANTINED)
            arts = svc.list_artifacts(run.run_id)
            self.assertEqual(len(arts), 1)
            self.assertEqual(arts[0].content_hash, art.content_hash)

    def test_verify_and_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            svc = _svc(root)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = root / "out.bin"
            f.write_bytes(b"\x00\x01\x02")
            svc.ingest(run_id=run.run_id, path=f)
            result = svc.verify(run.run_id)
            self.assertTrue(result["ok"])
            export_dir = root / "export"
            svc.export_run(run.run_id, export_dir)
            self.assertTrue((export_dir / "manifest.json").exists())
            self.assertTrue((export_dir / "artifacts" / "out.bin").exists())

    def test_lineage_parent_run(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(Path(td))
            parent = svc.create_run(project="P", subsystem="s", run_type="t")
            child = svc.create_run(
                project="P", subsystem="s", run_type="t", parent_run=parent.run_id
            )
            self.assertEqual(child.parent_run, parent.run_id)


if __name__ == "__main__":
    unittest.main()
