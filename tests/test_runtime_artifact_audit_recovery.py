"""Exact audit reconciliation and RECOVERY_REQUIRED retry."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.journal import JournalEntry, JournalState
from throne_runtime.artifacts.models import (
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    Trust,
)
from throne_runtime.artifacts.registry_ext import ensure_audit_record, get_promotion
from tests._artifact_test_util import make_service


class TestAuditReconcile(unittest.TestCase):
    def test_ensure_audit_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            rec = PromotionRecord(
                promotion_id="promo-test-1",
                artifact_id=art.artifact_id,
                run_id=run.run_id,
                previous_isolation=Isolation.QUARANTINED,
                new_isolation=Isolation.VALIDATED,
                previous_evidence=EvidenceGrade.EXPLORATORY,
                new_evidence=EvidenceGrade.EXPLORATORY,
                previous_trust=Trust.UNTRUSTED,
                new_trust=Trust.UNTRUSTED,
                policy_rule="t",
                actor="op",
                reason="t",
                decision="ALLOWED",
                timestamp="2026-01-01T00:00:00Z",
            )
            self.assertEqual(ensure_audit_record(svc.registry, rec), "inserted")
            self.assertEqual(ensure_audit_record(svc.registry, rec), "already_matches")
            got = get_promotion(svc.registry, "promo-test-1")
            self.assertIsNotNone(got)
            self.assertEqual(got.decision, "ALLOWED")

    def test_conflicting_audit_raises(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            rec = PromotionRecord(
                promotion_id="promo-conflict",
                artifact_id=art.artifact_id,
                run_id=run.run_id,
                previous_isolation=Isolation.QUARANTINED,
                new_isolation=Isolation.VALIDATED,
                previous_evidence=EvidenceGrade.EXPLORATORY,
                new_evidence=EvidenceGrade.EXPLORATORY,
                previous_trust=Trust.UNTRUSTED,
                new_trust=Trust.UNTRUSTED,
                policy_rule="t",
                actor="op",
                reason="t",
                decision="ALLOWED",
                timestamp="2026-01-01T00:00:00Z",
            )
            ensure_audit_record(svc.registry, rec)
            bad = PromotionRecord(
                promotion_id="promo-conflict",
                artifact_id="other-art",
                run_id=run.run_id,
                previous_isolation=Isolation.QUARANTINED,
                new_isolation=Isolation.REJECTED,
                previous_evidence=EvidenceGrade.EXPLORATORY,
                new_evidence=EvidenceGrade.EXPLORATORY,
                previous_trust=Trust.UNTRUSTED,
                new_trust=Trust.UNTRUSTED,
                policy_rule="t",
                actor="op",
                reason="t",
                decision="REJECTED",
                timestamp="2026-01-01T00:00:00Z",
            )
            with self.assertRaises(ValueError):
                ensure_audit_record(svc.registry, bad)


class TestRecoveryRequiredRetry(unittest.TestCase):
    def test_recovery_required_visible_and_retryable(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("payload")
            art = svc.ingest(run_id=run.run_id, path=f)
            snap = {
                "isolation": art.isolation.value,
                "evidence_grade": art.evidence_grade.value,
                "trust": art.trust.value,
                "stored_location": art.stored_location,
                "verification_history": [],
                "content_hash": art.content_hash,
                "size_bytes": art.size_bytes,
                "original_filename": art.original_filename,
                "run_id": art.run_id,
            }
            entry = JournalEntry(
                promotion_id="promo-rr-1",
                artifact_id=art.artifact_id,
                run_id=art.run_id,
                state=JournalState.RECOVERY_REQUIRED,
                old_isolation=Isolation.QUARANTINED.value,
                new_isolation=Isolation.VALIDATED.value,
                old_location=art.stored_location,
                new_location="",
                content_hash=art.content_hash,
                size_bytes=art.size_bytes,
                original_filename=art.original_filename,
                actor="op",
                reason="test",
                snapshot_json=json.dumps(snap),
                updated_at="2026-01-01T00:00:00Z",
                detail="injected",
            )
            svc.promotion_gate.journal.put(entry)
            # Visible to incomplete listing
            incomplete = svc.promotion_gate.journal.list_incomplete()
            self.assertTrue(any(e.promotion_id == "promo-rr-1" for e in incomplete))
            # Startup recovery attempts it
            svc2 = make_service(Path(td))
            ids = [r.get("promotion_id") for r in svc2.recovery_log]
            self.assertIn("promo-rr-1", ids)
            # Operator retry is idempotent
            r1 = svc2.promotion_gate.retry_recovery("promo-rr-1")
            r2 = svc2.promotion_gate.retry_recovery("promo-rr-1")
            self.assertIn(r1["action"], ("recovery_required", "rolled_back_prepared", "rolled_back_bad_dest", "completed"))
            self.assertIn(r2["action"], ("recovery_required", "rolled_back_prepared", "rolled_back_bad_dest", "completed", "already_terminal"))


if __name__ == "__main__":
    unittest.main()
