"""Atomic schema migration rollback and abrupt process-termination tests."""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import sqlite3
import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.locks import ArtifactLockManager
from throne_runtime.artifacts.manifest import attach_manifest_hash
from throne_runtime.artifacts.models import (
    EvidenceGrade,
    Isolation,
    RunManifest,
    RunStatus,
    Sensitivity,
    Trust,
)
from throne_runtime.artifacts.registry import Registry
from throne_runtime.artifacts.sqlite_db import Database
from tests._artifact_test_util import make_service


def _uncommitted_then_kill(db_path: str, run_id: str, ready: mp.Event):
    """Begin a write, insert, signal ready, then die without commit."""
    db = Database(Path(db_path))
    conn = db.connect()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """
        INSERT INTO runs (
            run_id, project, subsystem, run_type, created_at,
            source_commit, parent_run, trust, evidence_grade,
            isolation, sensitivity, status, manifest_json, manifest_hash
        ) VALUES (?, 'P', 's', 't', '2026-01-01T00:00:00Z',
                  '', NULL, 'UNTRUSTED', 'EXPLORATORY',
                  'QUARANTINED', 'INTERNAL', 'PENDING', '{}', '')
        """,
        (run_id,),
    )
    ready.set()
    # Hold the transaction open until killed
    import time

    time.sleep(30)


def _commit_then_kill(db_path: str, run_id: str, ready: mp.Event):
    reg = Registry(Path(db_path))
    m = RunManifest(
        run_id=run_id,
        project="P",
        subsystem="s",
        run_type="t",
        created_at="2026-01-01T00:00:00Z",
        trust=Trust.UNTRUSTED,
        evidence_grade=EvidenceGrade.EXPLORATORY,
        isolation=Isolation.QUARANTINED,
        sensitivity=Sensitivity.INTERNAL,
        status=RunStatus.PENDING,
    )
    attach_manifest_hash(m)
    reg.put_run(m)
    ready.set()
    import time

    time.sleep(30)


class TestSchemaRollback(unittest.TestCase):
    def test_failed_migration_leaves_no_partial_tables(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.sqlite3"
            db = Database(path)
            # Inject a failing statement mid-migration
            from throne_runtime.artifacts import schema as schema_mod

            original = list(schema_mod._REGISTRY_DDL)
            bad = original[:2] + ["CREATE TABLE IF NOT EXISTS this is invalid sql"] + original[2:]
            try:
                schema_mod._REGISTRY_DDL = bad
                with self.assertRaises(Exception):
                    schema_mod.apply_registry_schema(db)
            finally:
                schema_mod._REGISTRY_DDL = original

            # After failed migration, either nothing or full prior schema — not partial
            with db.connection() as conn:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            # The invalid statement should have rolled back the whole transaction
            # so custom tables from that failed batch should not persist.
            # (SQLite may still have empty db or only tables from earlier successful apply)
            self.assertNotIn("artifacts", tables)  # second table in failed batch


class TestAbruptTermination(unittest.TestCase):
    def test_uncommitted_absent_after_kill(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "k.sqlite3")
            Registry(Path(db_path))  # schema
            ready = mp.Event()
            p = mp.Process(
                target=_uncommitted_then_kill, args=(db_path, "run-ghost", ready)
            )
            p.start()
            self.assertTrue(ready.wait(10))
            os.kill(p.pid, signal.SIGKILL)
            p.join(10)
            reg = Registry(Path(db_path))
            self.assertIsNone(reg.get_run("run-ghost"))
            self.assertEqual(reg.db.integrity_check(), "ok")

    def test_committed_present_after_kill(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "c.sqlite3")
            Registry(Path(db_path))
            ready = mp.Event()
            p = mp.Process(
                target=_commit_then_kill, args=(db_path, "run-alive", ready)
            )
            p.start()
            self.assertTrue(ready.wait(10))
            os.kill(p.pid, signal.SIGKILL)
            p.join(10)
            reg = Registry(Path(db_path))
            self.assertIsNotNone(reg.get_run("run-alive"))
            self.assertEqual(reg.db.integrity_check(), "ok")

    def test_interrupted_promotion_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            svc = make_service(root)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            f = Path(td) / "blob.bin"
            f.write_bytes(b"crash-safe-payload")
            art = svc.ingest(run_id=run.run_id, path=f)
            blob_hash = art.content_hash
            # Interrupt promotion after PREPARED via fail injection
            from throne_runtime.artifacts.models import Isolation
            from throne_runtime.artifacts.verifiers import (
                VerificationRequest,
                VerifierCapability,
            )

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
                    reason="crash-test",
                    execution_record=erec,
                    proof_target="integrity",
                    _fail_at="prepared",
                )
            except Exception:
                pass
            # Blob must still exist
            self.assertTrue(svc.storage.exists(blob_hash))
            # Restart + recover
            svc2 = make_service(root)
            self.assertTrue(svc2.storage.exists(blob_hash))
            loaded = svc2.registry.get_artifact(art.artifact_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.content_hash, blob_hash)
            self.assertEqual(svc2.registry.db.integrity_check(), "ok")


if __name__ == "__main__":
    unittest.main()
