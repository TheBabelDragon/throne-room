"""SQLite WAL configuration, durability, and concurrent process tests."""

from __future__ import annotations

import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path

from throne_runtime.artifacts.locks import ArtifactLockManager, LockTimeout
from throne_runtime.artifacts.registry import Registry
from throne_runtime.artifacts.sqlite_db import Database, SQLiteConfigError
from tests._artifact_test_util import make_service


def _writer(db_path: str, run_id: str, n: int, q) -> None:
    try:
        from throne_runtime.artifacts.models import (
            Isolation,
            RunManifest,
            RunStatus,
            Sensitivity,
            Trust,
            EvidenceGrade,
        )
        from throne_runtime.artifacts.manifest import attach_manifest_hash

        reg = Registry(Path(db_path))
        for i in range(n):
            m = RunManifest(
                run_id=f"{run_id}-{i}",
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
        q.put("ok")
    except Exception as e:
        q.put(f"err:{e}")


class TestWALConfig(unittest.TestCase):
    def test_wal_established_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.sqlite3"
            db = Database(path)
            st = db.wal_status()
            self.assertEqual(st["journal_mode"].lower(), "wal")
            self.assertGreaterEqual(st["synchronous"], 2)  # FULL or EXTRA
            self.assertEqual(st["foreign_keys"], 1)
            self.assertGreater(st["busy_timeout_ms"], 0)
            # Reopen
            db2 = Database(path)
            st2 = db2.wal_status()
            self.assertEqual(st2["journal_mode"].lower(), "wal")

    def test_registry_uses_wal(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Registry(Path(td) / "r.sqlite3")
            st = reg.db.wal_status()
            self.assertEqual(st["journal_mode"].lower(), "wal")

    def test_checkpoint_passive(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "c.sqlite3")
            r = db.checkpoint_passive()
            self.assertIn("log_frames", r)
            self.assertEqual(db.integrity_check(), "ok")

    def test_service_db_wal(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(Path(td))
            st = svc.registry.db.wal_status()
            self.assertEqual(st["journal_mode"].lower(), "wal")


class TestConcurrentProcesses(unittest.TestCase):
    def test_two_writers_different_keys(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "w.sqlite3")
            # Bootstrap
            Registry(Path(db_path))
            q: mp.Queue = mp.Queue()
            p1 = mp.Process(target=_writer, args=(db_path, "a", 5, q))
            p2 = mp.Process(target=_writer, args=(db_path, "b", 5, q))
            p1.start()
            p2.start()
            p1.join(timeout=30)
            p2.join(timeout=30)
            r1, r2 = q.get(timeout=5), q.get(timeout=5)
            self.assertEqual(r1, "ok")
            self.assertEqual(r2, "ok")
            reg = Registry(Path(db_path))
            self.assertEqual(len(reg.list_runs()), 10)
            self.assertEqual(reg.db.integrity_check(), "ok")

    def test_lease_contention(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "l.sqlite3"
            ArtifactLockManager(db)
            q: mp.Queue = mp.Queue()

            def hold(path, aid, hold, out):
                lm = ArtifactLockManager(Path(path))
                lease = lm.acquire(aid, timeout_s=5.0, ttl_s=10.0)
                out.put("held")
                time.sleep(hold)
                lm.renew(lease, ttl_s=10.0)
                time.sleep(0.2)
                lm.release(lease)
                out.put("done")

            p = mp.Process(target=hold, args=(str(db), "art-z", 1.0, q))
            p.start()
            self.assertEqual(q.get(timeout=5), "held")
            lm = ArtifactLockManager(db)
            with self.assertRaises(LockTimeout):
                lm.acquire("art-z", timeout_s=0.3)
            p.join(timeout=10)
            self.assertEqual(q.get(timeout=5), "done")


if __name__ == "__main__":
    unittest.main()
