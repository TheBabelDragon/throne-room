"""Final security hardening regression tests."""

from __future__ import annotations

import secrets
import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import (
    EvidenceGrade,
    Isolation,
    RunManifest,
    Trust,
)
from throne_runtime.artifacts.policy import PolicyError, load_routing_policy_loose
from throne_runtime.artifacts.scanner import ScanError
from throne_runtime.artifacts.service import ArtifactService
from throne_runtime.artifacts.verifiers import (
    VerificationExecutionRecord,
    VerificationRequest,
)


def _svc(td: str) -> ArtifactService:
    # Tests use intentional override; production defaults require_policy=True
    policy = Path(__file__).resolve().parents[1] / "policies"
    return ArtifactService(root=Path(td), policy_dir=policy, require_policy=True)


class TestSignedVerifierRecords(unittest.TestCase):
    def test_forged_record_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t", source_commit="c1")
            f = Path(td) / "a.txt"
            f.write_text("data")
            art = svc.ingest(run_id=run.run_id, path=f)
            # Forge with wrong key
            forged = VerificationExecutionRecord(
                record_id="ver-forge",
                verifier_id="hash_bound_self_check",
                verifier_version="1.0",
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="c1",
                proof_target="T",
                result="PASS",
                detail="forged",
                executed_at="2026-01-01T00:00:00Z",
            ).sign(secrets.token_bytes(32))  # wrong key
            ok, msg = svc.verifiers.validate_record(
                forged,
                expected_content_hash=art.content_hash,
                expected_artifact_id=art.artifact_id,
                expected_source_commit="c1",
            )
            self.assertFalse(ok)
            self.assertIn("signature", msg.lower())

    def test_unsigned_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            rec = VerificationExecutionRecord(
                record_id="ver-u",
                verifier_id="hash_bound_self_check",
                verifier_version="1.0",
                artifact_id="a",
                content_hash="ab" * 32,
                source_commit="c",
                proof_target="t",
                result="PASS",
                detail="",
                executed_at="2026-01-01T00:00:00Z",
            )
            ok, msg = svc.verifiers.validate_record(
                rec,
                expected_content_hash="ab" * 32,
                expected_artifact_id="a",
            )
            self.assertFalse(ok)

    def test_wrong_source_commit_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t", source_commit="c1")
            f = Path(td) / "a.txt"
            f.write_text("data")
            art = svc.ingest(run_id=run.run_id, path=f)
            key = svc.verifiers.keys.get("hash_bound_self_check")
            assert key is not None
            rec = VerificationExecutionRecord(
                record_id="ver-sc",
                verifier_id="hash_bound_self_check",
                verifier_version="1.0",
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="WRONG",
                proof_target="t",
                result="PASS",
                detail="",
                executed_at="2026-01-01T00:00:00Z",
            ).sign(key)
            ok, msg = svc.verifiers.validate_record(
                rec,
                expected_content_hash=art.content_hash,
                expected_artifact_id=art.artifact_id,
                expected_source_commit="c1",
            )
            self.assertFalse(ok)
            self.assertIn("source_commit", msg)

    def test_lean_cannot_certify(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            # First to validated
            r1 = svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            self.assertEqual(r1["decision"], "ALLOWED")
            r2 = svc.promote(
                art.artifact_id,
                target="CERTIFIED_READ_ONLY",
                actor="op",
                verifier_id="lean_certificate",
                proof_target="MassGap",
            )
            self.assertEqual(r2["decision"], "REJECTED")

    def test_caller_dict_pass_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            result = svc.promote(
                art.artifact_id,
                target="CERTIFIED_READ_ONLY",
                actor="attacker",
                verifier_evidence={
                    "verification_result": "PASS",
                    "verifier_id": "fake",
                    "certificate_hash": "ab" * 32,
                },
            )
            self.assertEqual(result["decision"], "REJECTED")


class TestAtomicPromotion(unittest.TestCase):
    def test_promotion_no_old_tier_exposure(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("move")
            art = svc.ingest(run_id=run.run_id, path=f)
            old = Path(art.stored_location)
            self.assertTrue(old.exists())
            r = svc.promote(art.artifact_id, target="VALIDATED", actor="op")
            self.assertEqual(r["decision"], "ALLOWED")
            loaded = svc.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, Isolation.VALIDATED)
            self.assertIn("validated", loaded.stored_location.replace("\\", "/"))
            # Old quarantine path removed
            if old.exists():
                self.assertEqual(old.resolve(), Path(loaded.stored_location).resolve())

    def test_injected_destination_verify_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
            old_iso = art.isolation
            old_loc = art.stored_location
            # Execute verifier then inject failure
            req = VerificationRequest(
                artifact_id=art.artifact_id,
                content_hash=art.content_hash,
                source_commit="",
                proof_target="integrity",
            )
            erec = svc.verifiers.execute("hash_bound_self_check", req)
            rec = svc.promotion_gate.promote(
                art,
                target_isolation=Isolation.VALIDATED,
                actor="op",
                reason="test",
                execution_record=erec,
                _fail_at="destination_verify",
            )
            self.assertEqual(rec.decision, "REJECTED")
            loaded = svc.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, old_iso)
            self.assertEqual(loaded.stored_location, old_loc)


class TestStrictManifest(unittest.TestCase):
    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            RunManifest.from_dict(
                {
                    "schema": "throne.runtime.artifact-manifest",
                    "version": 1,
                    "run_id": "r",
                    "project": "p",
                    "subsystem": "s",
                    "run_type": "t",
                    "created_at": "2026-01-01T00:00:00Z",
                    "evil": True,
                }
            )

    def test_bad_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            RunManifest.from_dict(
                {
                    "schema": "throne.runtime.artifact-manifest",
                    "version": 1,
                    "run_id": "r",
                    "project": "p",
                    "subsystem": "s",
                    "run_type": "t",
                    "created_at": "not-a-timestamp",
                }
            )

    def test_bad_hash_format_rejected(self):
        with self.assertRaises(ValueError):
            RunManifest.from_dict(
                {
                    "schema": "throne.runtime.artifact-manifest",
                    "version": 1,
                    "run_id": "r",
                    "project": "p",
                    "subsystem": "s",
                    "run_type": "t",
                    "created_at": "2026-01-01T00:00:00Z",
                    "manifest_hash": "zzzz",
                }
            )


class TestFilesystemSafety(unittest.TestCase):
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            target = Path(td) / "real.txt"
            target.write_text("secret")
            link = Path(td) / "link.txt"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unsupported")
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            with self.assertRaises(ScanError):
                svc.ingest(run_id=run.run_id, path=link)

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _svc(td)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "ok.txt"
            f.write_text("x")
            with self.assertRaises(ScanError):
                svc.ingest(run_id=run.run_id, path=f, filename="../escape.txt")


class TestPolicyFailClosed(unittest.TestCase):
    def test_missing_policy_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PolicyError):
                ArtifactService(
                    root=Path(td),
                    policy_dir=Path(td) / "nope",
                    require_policy=True,
                )

    def test_malformed_policy_raises(self):
        with tempfile.TemporaryDirectory() as td:
            pdir = Path(td) / "policies"
            pdir.mkdir()
            (pdir / "artifact_routing.yaml").write_text("garbage: true\n")
            with self.assertRaises(PolicyError):
                load_routing_policy_loose(pdir / "artifact_routing.yaml")

    def test_valid_policy_loads(self):
        policy = Path(__file__).resolve().parents[1] / "policies" / "artifact_routing.yaml"
        rp = load_routing_policy_loose(policy)
        self.assertTrue(rp.content_hash)
        self.assertEqual(rp.version, 1)


if __name__ == "__main__":
    unittest.main()
