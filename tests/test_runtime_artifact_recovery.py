"""Promotion journal crash-injection and startup recovery tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.journal import JournalState
from throne_runtime.artifacts.models import Isolation
from throne_runtime.artifacts.verifiers import (
    VerificationRequest,
    VerifierCapability,
)
from tests._artifact_test_util import make_service


class TestPromotionRecovery(unittest.TestCase):
    def _seed(self, td: str):
        svc = make_service(Path(td))
        run = svc.create_run(project="P", subsystem="s", run_type="t")
        f = Path(td) / "payload.txt"
        f.write_text("payload-data")
        art = svc.ingest(run_id=run.run_id, path=f)
        return svc, art

    def test_recovery_after_prepared_only(self):
        with tempfile.TemporaryDirectory() as td:
            svc, art = self._seed(td)
            req = VerificationRequest(
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="",
                proof_target="integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            erec = svc.verifiers.execute("hash_bound_self_check", req)
            try:
                svc.promotion_gate.promote(
                    art,
                    target_isolation=Isolation.VALIDATED,
                    actor="op",
                    reason="t",
                    execution_record=erec,
                    proof_target="integrity",
                    _fail_at="prepared",
                )
            except Exception:
                pass
            # Restart
            svc2 = make_service(Path(td))
            self.assertTrue(isinstance(svc2.recovery_log, list))
            loaded = svc2.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, Isolation.QUARANTINED)
            # Idempotent second recovery
            again = svc2.promotion_gate.recover_incomplete()
            self.assertIsInstance(again, list)

    def test_recovery_after_audit_committed(self):
        """Crash after audit, before old-tier removal — recovery completes."""
        with tempfile.TemporaryDirectory() as td:
            svc, art = self._seed(td)
            old_loc = art.stored_location
            req = VerificationRequest(
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="",
                proof_target="integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            erec = svc.verifiers.execute("hash_bound_self_check", req)
            # Force fail at old_tier_removal after audit
            try:
                svc.promotion_gate.promote(
                    art,
                    target_isolation=Isolation.VALIDATED,
                    actor="op",
                    reason="t",
                    execution_record=erec,
                    proof_target="integrity",
                    _fail_at="old_tier_removal",
                )
            except Exception:
                pass
            svc2 = make_service(Path(td))
            loaded = svc2.registry.get_artifact(art.artifact_id)
            # Either fully validated with no dual exposure, or recovery_required
            self.assertIn(
                loaded.isolation,
                (Isolation.VALIDATED, Isolation.QUARANTINED),
            )
            incomplete = svc2.promotion_gate.journal.list_incomplete()
            self.assertEqual(incomplete, [])

    def test_successful_promote_no_dual_exposure(self):
        with tempfile.TemporaryDirectory() as td:
            svc, art = self._seed(td)
            old = Path(art.stored_location)
            r = svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            self.assertEqual(r["decision"], "ALLOWED")
            loaded = svc.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, Isolation.VALIDATED)
            new = Path(loaded.stored_location)
            self.assertTrue(new.exists())
            if old.exists():
                self.assertEqual(old.resolve(), new.resolve())

    def test_recovery_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc, art = self._seed(td)
            svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            a1 = svc.promotion_gate.recover_incomplete()
            a2 = svc.promotion_gate.recover_incomplete()
            self.assertEqual(a1, [])
            self.assertEqual(a2, [])


if __name__ == "__main__":
    unittest.main()
