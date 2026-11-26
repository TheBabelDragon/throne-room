"""Capability authorization + key persistence + recoverable promotion."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import EvidenceGrade, Isolation
from throne_runtime.artifacts.service import ArtifactService
from throne_runtime.artifacts.verifiers import (
    VerificationExecutionRecord,
    VerificationRequest,
    VerifierCapability,
)

_POLICY = Path(__file__).resolve().parents[1] / "policies"


def _svc(td: str, **kwargs) -> ArtifactService:
    return ArtifactService(
        root=Path(td),
        policy_dir=_POLICY,
        allow_ephemeral_keys=True,
        **kwargs,
    )


class TestCapabilities(unittest.TestCase):
    def test_hash_self_check_authorizes_validated(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("ok")
            art = svc.ingest(run_id=run.run_id, path=f)
            r = svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            self.assertEqual(r["decision"], "ALLOWED")
            self.assertEqual(
                svc.registry.get_artifact(art.artifact_id).isolation,
                Isolation.VALIDATED,
            )

    def test_hash_self_check_cannot_certify(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("ok")
            art = svc.ingest(run_id=run.run_id, path=f)
            svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            r = svc.promote(
                art.artifact_id,
                target="CERTIFIED_READ_ONLY",
                actor="op",
                verifier_id="hash_bound_self_check",
                proof_target="MassGap",
            )
            self.assertEqual(r["decision"], "REJECTED")

    def test_lean_cannot_certify(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("ok")
            art = svc.ingest(run_id=run.run_id, path=f)
            svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            r = svc.promote(
                art.artifact_id,
                target="CERTIFIED_READ_ONLY",
                actor="op",
                verifier_id="lean_certificate",
                proof_target="MassGap",
            )
            self.assertEqual(r["decision"], "REJECTED")

    def test_wrong_proof_target_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(
                project="P", subsystem="s", run_type="t", source_commit="c1"
            )
            f = Path(td) / "a.txt"
            f.write_text("ok")
            art = svc.ingest(run_id=run.run_id, path=f)
            req = VerificationRequest(
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="c1",
                proof_target="integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            rec = svc.verifiers.execute("hash_bound_self_check", req)
            ok, msg = svc.verifiers.validate_record(
                rec,
                expected_content_hash=art.content_hash,
                expected_artifact_id=art.artifact_id,
                expected_source_commit="c1",
                expected_proof_target="OTHER",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            self.assertFalse(ok)
            self.assertIn("proof_target", msg)

    def test_caller_dict_cannot_bypass(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            r = svc.promote(
                art.artifact_id,
                target="CERTIFIED_READ_ONLY",
                actor="attacker",
                verifier_evidence={"verification_result": "PASS"},
            )
            self.assertEqual(r["decision"], "REJECTED")


class TestKeyPersistence(unittest.TestCase):
    def test_persistent_key_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            key = secrets_bytes = __import__("secrets").token_bytes(32)
            keyfile = Path(td) / "keys.json"
            keyfile.write_text(
                json.dumps(
                    {
                        "hash_bound_self_check": [
                            {"key_id": "k1", "key_hex": key.hex(), "retired": False}
                        ],
                        "lean_certificate": [
                            {
                                "key_id": "k1",
                                "key_hex": __import__("secrets").token_bytes(32).hex(),
                                "retired": False,
                            }
                        ],
                    }
                )
            )
            root1 = Path(td) / "store1"
            svc1 = ArtifactService(
                root=root1,
                policy_dir=_POLICY,
                verifier_keys_path=keyfile,
                allow_ephemeral_keys=False,
            )
            run = svc1.create_run(project="P", subsystem="s", run_type="t", source_commit="c")
            f = Path(td) / "a.txt"
            f.write_text("persist")
            art = svc1.ingest(run_id=run.run_id, path=f)
            req = VerificationRequest(
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="c",
                proof_target="integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            rec = svc1.verifiers.execute("hash_bound_self_check", req)
            # New service instance, same keys
            svc2 = ArtifactService(
                root=root1,
                policy_dir=_POLICY,
                verifier_keys_path=keyfile,
                allow_ephemeral_keys=False,
            )
            ok, msg = svc2.verifiers.validate_record(
                VerificationExecutionRecord.from_dict(rec.as_dict()),
                expected_content_hash=art.content_hash,
                expected_artifact_id=art.artifact_id,
                expected_source_commit="c",
                expected_proof_target="integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            self.assertTrue(ok, msg)

    def test_missing_production_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError):
                ArtifactService(
                    root=Path(td),
                    policy_dir=_POLICY,
                    allow_ephemeral_keys=False,
                )


class TestRecoverablePromotion(unittest.TestCase):
    def test_audit_failure_keeps_old_tier(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            old_loc = art.stored_location
            old_iso = art.isolation
            req = VerificationRequest(
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="",
                proof_target="integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            erec = svc.verifiers.execute("hash_bound_self_check", req)
            rec = svc.promotion_gate.promote(
                art,
                target_isolation=Isolation.VALIDATED,
                actor="op",
                reason="test",
                execution_record=erec,
                proof_target="integrity",
                _fail_at="audit_append",
            )
            self.assertEqual(rec.decision, "REJECTED")
            loaded = svc.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, old_iso)
            # Original exposure restored or still present
            self.assertTrue(
                Path(loaded.stored_location).exists()
                or Path(old_loc).exists()
            )


if __name__ == "__main__":
    unittest.main()
