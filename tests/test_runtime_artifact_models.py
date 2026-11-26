"""Models and independent classification dimensions."""

from __future__ import annotations

import unittest

from throne_runtime.artifacts.models import (
    EvidenceGrade,
    Isolation,
    RunManifest,
    Trust,
)


class TestModels(unittest.TestCase):
    def test_independent_axes(self):
        m = RunManifest(
            run_id="run-1",
            project="P",
            subsystem="s",
            run_type="t",
            created_at="2026-01-01T00:00:00Z",
            trust=Trust.UNTRUSTED,
            evidence_grade=EvidenceGrade.NUMERICALLY_CROSSCHECKED,
            isolation=Isolation.SANDBOXED,
        )
        self.assertEqual(m.trust, Trust.UNTRUSTED)
        self.assertEqual(m.evidence_grade, EvidenceGrade.NUMERICALLY_CROSSCHECKED)
        self.assertEqual(m.isolation, Isolation.SANDBOXED)

    def test_invalid_manifest_rejected(self):
        with self.assertRaises(ValueError):
            RunManifest.from_dict({"schema": "wrong"})

    def test_unknown_evidence_rejected(self):
        with self.assertRaises(ValueError):
            RunManifest.from_dict(
                {
                    "schema": "throne.runtime.artifact-manifest",
                    "version": 1,
                    "run_id": "r",
                    "project": "p",
                    "subsystem": "s",
                    "run_type": "t",
                    "created_at": "t",
                    "evidence_grade": "PROOF_BY_VIBES",
                }
            )


if __name__ == "__main__":
    unittest.main()
