"""Hardening regression tests (v0.1 critical corrections)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import (
    EvidenceGrade,
    Isolation,
    Trust,
)
from throne_runtime.artifacts.scanner import ScanError, ScanLimits
from throne_runtime.artifacts.service import ArtifactService
from throne_runtime.artifacts.verifiers import VerificationExecutionRecord

_POLICY = Path(__file__).resolve().parents[1] / "policies"


def _svc(td: str) -> ArtifactService:
    return ArtifactService(root=Path(td), policy_dir=_POLICY)


class TestHardening(unittest.TestCase):
    def test_forged_verifier_pass_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("data")
            art = svc.ingest(run_id=run.run_id, path=f)
            result = svc.promote(
                art.artifact_id,
                target="CERTIFIED_READ_ONLY",
                actor="attacker",
                reason="forged",
                verifier_evidence={
                    "verifier_id": "fake",
                    "verifier_version": "1",
                    "target": "T",
                    "certificate_hash": "abc",
                    "verification_result": "PASS",
                },
            )
            self.assertEqual(result["decision"], "REJECTED")

    def test_wrong_hash_record_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(
                project="P", subsystem="s", run_type="t", source_commit="c1"
            )
            f = Path(td) / "a.txt"
            f.write_text("data")
            art = svc.ingest(run_id=run.run_id, path=f)
            bad = VerificationExecutionRecord(
                record_id="ver-bad",
                verifier_id="hash_bound_self_check",
                verifier_version="1.0",
                artifact_id=art.artifact_id,
                content_hash="0" * 64,
                source_commit="c1",
                proof_target="T",
                result="PASS",
                detail="forged",
                executed_at="2026-01-01T00:00:00Z",
            )
            # unsigned / wrong binding
            ok, msg = svc.verifiers.validate_record(
                bad,
                expected_content_hash=art.content_hash,
                expected_artifact_id=art.artifact_id,
            )
            self.assertFalse(ok)

    def test_genuine_verifier_satisfies_validated(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("ok")
            art = svc.ingest(run_id=run.run_id, path=f)
            result = svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            self.assertEqual(result["decision"], "ALLOWED")
            loaded = svc.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, Isolation.VALIDATED)

    def test_upsert_preserves_artifact_fk(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            svc.add_check(run_id=run.run_id, name="c", status="PASS")
            run2 = svc.get_run(run.run_id)
            self.assertIsNotNone(run2)
            arts = svc.list_artifacts(run.run_id)
            self.assertEqual(len(arts), 1)
            self.assertEqual(arts[0].artifact_id, art.artifact_id)

    def test_self_declared_trusted_cannot_bypass(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(
                project="P",
                subsystem="s",
                run_type="t",
                trust=Trust.TRUSTED,
                evidence_grade=EvidenceGrade.CERTIFIED,
            )
            self.assertEqual(run.trust, Trust.UNTRUSTED)
            self.assertEqual(run.evidence_grade, EvidenceGrade.EXPLORATORY)

    def test_yaml_policy_loaded(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            self.assertIsNotNone(svc.routing_policy)
            self.assertTrue(len(svc.routing_policy.rules) >= 1)

    def test_aggregate_limits(self):
        with tempfile.TemporaryDirectory() as td:
            limits = ScanLimits(max_files=2, max_total_bytes=1000, max_single_file_bytes=500)
            svc = ArtifactService(root=Path(td), policy_dir=_POLICY, scan_limits=limits)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            for i in range(2):
                f = Path(td) / f"f{i}.txt"
                f.write_text("x")
                svc.ingest(run_id=run.run_id, path=f)
            f3 = Path(td) / "f3.txt"
            f3.write_text("y")
            with self.assertRaises(ScanError):
                svc.ingest(run_id=run.run_id, path=f3)


if __name__ == "__main__":
    unittest.main()
