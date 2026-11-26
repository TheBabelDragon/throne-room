"""Manifest round-trip and validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.manifest import (
    attach_manifest_hash,
    compute_manifest_hash,
    load_manifest,
    write_manifest,
)
from throne_runtime.artifacts.models import RunManifest, RunStatus
from throne_runtime.artifacts.service import ArtifactService

_POLICY = Path(__file__).resolve().parents[1] / "policies"


class TestManifest(unittest.TestCase):
    def test_round_trip(self):
        m = RunManifest(
            run_id="run-abc",
            project="Spacetime",
            subsystem="formal_verification",
            run_type="lean_build",
            created_at="2026-01-01T00:00:00Z",
            source_commit="deadbeef",
            status=RunStatus.COMPLETED,
        )
        attach_manifest_hash(m)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            write_manifest(p, m)
            loaded = load_manifest(p)
            self.assertEqual(loaded.run_id, m.run_id)
            self.assertEqual(loaded.project, m.project)
            self.assertEqual(loaded.manifest_hash, m.manifest_hash)
            self.assertEqual(compute_manifest_hash(loaded), loaded.manifest_hash)

    def test_unique_run_ids(self):
        with tempfile.TemporaryDirectory() as td:
            svc = ArtifactService(root=Path(td), policy_dir=_POLICY)
            a = svc.create_run(project="P", subsystem="s", run_type="t")
            b = svc.create_run(project="P", subsystem="s", run_type="t")
            self.assertNotEqual(a.run_id, b.run_id)


if __name__ == "__main__":
    unittest.main()
