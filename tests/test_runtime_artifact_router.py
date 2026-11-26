"""Routing policy."""

from __future__ import annotations

import unittest

from throne_runtime.artifacts.models import EvidenceGrade, Isolation, RunManifest, RunStatus
from throne_runtime.artifacts.router import ArtifactRouter


class TestRouter(unittest.TestCase):
    def test_unknown_to_quarantine(self):
        d = ArtifactRouter().route_new_ingest(None)
        self.assertEqual(d.isolation, Isolation.QUARANTINED)

    def test_new_ingest_quarantine(self):
        m = RunManifest(
            run_id="r",
            project="p",
            subsystem="s",
            run_type="t",
            created_at="t",
            evidence_grade=EvidenceGrade.FORMALLY_PROVED,
        )
        d = ArtifactRouter().route_new_ingest(m)
        self.assertEqual(d.isolation, Isolation.QUARANTINED)

    def test_experimental_to_sandbox(self):
        m = RunManifest(
            run_id="r",
            project="p",
            subsystem="s",
            run_type="t",
            created_at="t",
            evidence_grade=EvidenceGrade.NUMERICALLY_CROSSCHECKED,
            status=RunStatus.COMPLETED,
        )
        d = ArtifactRouter().route_after_checks(m)
        self.assertEqual(d.isolation, Isolation.SANDBOXED)


if __name__ == "__main__":
    unittest.main()
