"""Final security hardening regression tests."""

from __future__ import annotations

import secrets
import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import Isolation, RunManifest
from throne_runtime.artifacts.policy import PolicyError, load_routing_policy_loose
from throne_runtime.artifacts.scanner import ScanError
from throne_runtime.artifacts.verifiers import VerificationExecutionRecord
from tests._artifact_test_util import make_service, POLICY


class TestSignedVerifierRecords(unittest.TestCase):
    def test_forged_record_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
            run = svc.create_run(project="P", subsystem="s", run_type="t", source_commit="c1")
            f = Path(td) / "a.txt"
            f.write_text("data")
            art = svc.ingest(run_id=run.run_id, path=f)
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
                capability="INTEGRITY_CHECK",
            ).sign(secrets.token_bytes(32))
            ok, msg = svc.verifiers.validate_record(
                forged,
                expected_content_hash=art.content_hash,
                expected_artifact_id=art.artifact_id,
                expected_source_commit="c1",
            )
            self.assertFalse(ok)

    def test_lean_cannot_certify(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "a.txt"
            f.write_text("x")
            art = svc.ingest(run_id=run.run_id, path=f)
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


class TestFilesystemSafety(unittest.TestCase):
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
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
            svc = make_service(Path(td))
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "ok.txt"
            f.write_text("x")
            with self.assertRaises(ScanError):
                svc.ingest(run_id=run.run_id, path=f, filename="../escape.txt")


class TestPolicyFailClosed(unittest.TestCase):
    def test_missing_policy_raises(self):
        with tempfile.TemporaryDirectory() as td:
            from throne_runtime.artifacts.service import ArtifactService

            with self.assertRaises(Exception):
                ArtifactService(
                    root=Path(td),
                    policy_dir=Path(td) / "nope",
                    require_policy=True,
                    allow_ephemeral_keys=True,
                )

    def test_valid_policy_loads(self):
        rp = load_routing_policy_loose(POLICY / "artifact_routing.yaml")
        self.assertTrue(rp.content_hash)


if __name__ == "__main__":
    unittest.main()
