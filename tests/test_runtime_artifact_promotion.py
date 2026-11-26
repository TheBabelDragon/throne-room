"""Promotion gates: no self-promotion, no numerical-to-proof, audit history."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import (
    ArtifactRecord,
    EvidenceGrade,
    Isolation,
    Sensitivity,
    Trust,
)
from throne_runtime.artifacts.promotion import PromotionGate
from throne_runtime.artifacts.registry import Registry
from throne_runtime.artifacts.router import ArtifactRouter


def _art(**kwargs):
    base = dict(
        artifact_id="art-1",
        run_id="run-1",
        content_hash="abc",
        original_filename="f.txt",
        stored_location="/x",
        media_type="text/plain",
        size_bytes=1,
        source_subsystem="test",
        parent_run=None,
        trust=Trust.UNTRUSTED,
        evidence_grade=EvidenceGrade.EXPLORATORY,
        isolation=Isolation.QUARANTINED,
        sensitivity=Sensitivity.INTERNAL,
        created_at="t",
    )
    base.update(kwargs)
    return ArtifactRecord(**base)


class TestPromotion(unittest.TestCase):
    def test_experimental_cannot_self_promote_to_proof(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Registry(Path(td) / "r.sqlite3")
            gate = PromotionGate(reg, ArtifactRouter())
            art = _art(evidence_grade=EvidenceGrade.NUMERICALLY_CROSSCHECKED)
            reg.put_artifact(art)
            rec = gate.promote(
                art,
                target_isolation=Isolation.CERTIFIED_READ_ONLY,
                target_evidence=EvidenceGrade.FORMALLY_PROVED,
                actor="self",
                reason="looks good",
            )
            self.assertEqual(rec.decision, "REJECTED")

    def test_certificate_filename_alone_insufficient(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Registry(Path(td) / "r.sqlite3")
            gate = PromotionGate(reg, ArtifactRouter())
            art = _art()
            reg.put_artifact(art)
            rec = gate.promote(
                art,
                target_isolation=Isolation.CERTIFIED_READ_ONLY,
                actor="op",
                reason="cert.lean exists",
                verifier_evidence={"certificate_filename": "cert.lean"},
            )
            self.assertEqual(rec.decision, "REJECTED")

    def test_formal_requires_verifier_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Registry(Path(td) / "r.sqlite3")
            gate = PromotionGate(reg, ArtifactRouter())
            art = _art()
            reg.put_artifact(art)
            rec = gate.promote(
                art,
                target_isolation=Isolation.CERTIFIED_READ_ONLY,
                target_evidence=EvidenceGrade.FORMALLY_PROVED,
                actor="op",
                reason="verified",
                verifier_evidence={
                    "verifier_id": "lean-checker",
                    "verifier_version": "4.0",
                    "target": "MassGap",
                    "certificate_hash": "deadbeef" * 8,
                    "verification_result": "PASS",
                },
            )
            self.assertEqual(rec.decision, "ALLOWED")
            history = reg.list_promotions(artifact_id="art-1")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].decision, "ALLOWED")

    def test_rejected_remains_traceable(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Registry(Path(td) / "r.sqlite3")
            gate = PromotionGate(reg, ArtifactRouter())
            art = _art()
            reg.put_artifact(art)
            gate.promote(
                art,
                target_isolation=Isolation.CERTIFIED_READ_ONLY,
                actor="op",
                reason="nope",
            )
            hist = reg.list_promotions(artifact_id="art-1")
            self.assertEqual(len(hist), 1)
            self.assertEqual(hist[0].decision, "REJECTED")
            # Original isolation unchanged
            loaded = reg.get_artifact("art-1")
            self.assertEqual(loaded.isolation, Isolation.QUARANTINED)


if __name__ == "__main__":
    unittest.main()
