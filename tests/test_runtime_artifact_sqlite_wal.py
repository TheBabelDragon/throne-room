"""SQLite WAL configuration, durability, concurrency, backup/restore."""

from __future__ import annotations

import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path

from throne_runtime.artifacts.locks import ArtifactLockManager, LockError, LockTimeout
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


def _barrier_write(db_path: str, run_id: str, ready: mp.Event, go: mp.Event, done: mp.Queue):
    try:
        reg = Registry(Path(db_path))
        ready.set()
        go.wait(timeout=10)
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
        done.put("ok")
    except Exception as e:
        done.put(f"err:{e}")


def _barrier_read(db_path: str, ready: mp.Event, go: mp.Event, done: mp.Queue):
    try:
        reg = Registry(Path(db_path))
        ready.set()
        go.wait(timeout=10)
        _ = reg.list_runs()
        done.put("ok")
    except Exception as e:
        done.put(f"err:{e}")


def _hold_lease(db_path: str, aid: str, held: mp.Event, release: mp.Event, done: mp.Queue):
    try:
        lm = ArtifactLockManager(Path(db_path))
        lease = lm.acquire(aid, timeout_s=5.0, ttl_s=30.0)
        held.set()
        release.wait(timeout=15)
        lm.release(lease)
        done.put("released")
    except Exception as e:
        done.put(f"err:{e}")


def _crash_after_commit(db_path: str, run_id: str, done: mp.Queue):
    try:
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
        done.put("committed")
        # Process ends immediately after commit (normal exit simulates stop)
    except Exception as e:
        done.put(f"err:{e}")


class TestWALConfig(unittest.TestCase):
    def test_every_connection_full_sync(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "t.sqlite3")
            for _ in range(3):
                with db.connection() as conn:
                    sync = int(conn.execute("PRAGMA synchronous").fetchone()[0])
                    self.assertGreaterEqual(sync, 2)
                    mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                    self.assertEqual(mode, "wal")
                    fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
                    self.assertEqual(fk, 1)

    def test_wal_persists_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.sqlite3"
            Database(path)
            st = Database(path).wal_status()
            self.assertEqual(st["journal_mode"].lower(), "wal")
            self.assertGreaterEqual(st["synchronous"], 2)


class TestConcurrentProcesses(unittest.TestCase):
    def test_reader_during_writer(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "rw.sqlite3")
            Registry(Path(db_path))  # bootstrap
            ready_w, ready_r = mp.Event(), mp.Event()
            go = mp.Event()
            q: mp.Queue = mp.Queue()
            pw = mp.Process(
                target=_barrier_write, args=(db_path, "run-w1", ready_w, go, q)
            )
            pr = mp.Process(target=_barrier_read, args=(db_path, ready_r, go, q))
            pw.start()
            pr.start()
            self.assertTrue(ready_w.wait(5))
            self.assertTrue(ready_r.wait(5))
            go.set()
            pw.join(15)
            pr.join(15)
            results = {q.get(timeout=5), q.get(timeout=5)}
            self.assertEqual(results, {"ok"})

    def test_same_artifact_lock_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "lock.sqlite3")
            ArtifactLockManager(Path(db))
            held, release = mp.Event(), mp.Event()
            q: mp.Queue = mp.Queue()
            p = mp.Process(target=_hold_lease, args=(db, "art-same", held, release, q))
            p.start()
            self.assertTrue(held.wait(5))
            lm = ArtifactLockManager(Path(db))
            with self.assertRaises(LockTimeout):
                lm.acquire("art-same", timeout_s=0.4)
            release.set()
            p.join(10)
            self.assertEqual(q.get(timeout=5), "released")
            lease = lm.acquire("art-same", timeout_s=2.0)
            lm.release(lease)

    def test_different_artifact_locks(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "d.sqlite3"
            lm1 = ArtifactLockManager(db)
            lm2 = ArtifactLockManager(db)
            a = lm1.acquire("art-a", timeout_s=2.0)
            b = lm2.acquire("art-b", timeout_s=2.0)
            lm1.release(a)
            lm2.release(b)

    def test_lease_renew_and_ownership(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "rn.sqlite3"
            lm = ArtifactLockManager(db, default_ttl_s=2.0)
            lease = lm.acquire("art-r", timeout_s=2.0, ttl_s=2.0)
            lm.renew(lease, ttl_s=5.0)
            self.assertGreater(lease.expires_at, time.time())
            lm.release(lease)
            with self.assertRaises(LockError):
                lm.release(lease)  # ownership gone

    def test_expired_lease_reclaim(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "ex.sqlite3"
            lm = ArtifactLockManager(db, default_ttl_s=0.2)
            lease = lm.acquire("art-e", timeout_s=1.0, ttl_s=0.2)
            time.sleep(0.4)
            lm2 = ArtifactLockManager(db)
            lease2 = lm2.acquire("art-e", timeout_s=2.0)
            lm2.release(lease2)
            try:
                lm.release(lease)
            except LockError:
                pass

    def test_commit_then_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "c.sqlite3")
            Registry(Path(db_path))
            q: mp.Queue = mp.Queue()
            p = mp.Process(target=_crash_after_commit, args=(db_path, "run-persist", q))
            p.start()
            p.join(15)
            self.assertEqual(q.get(timeout=5), "committed")
            reg = Registry(Path(db_path))
            self.assertIsNotNone(reg.get_run("run-persist"))
            self.assertEqual(reg.db.integrity_check(), "ok")
            self.assertEqual(reg.db.wal_status()["journal_mode"].lower(), "wal")


class TestCheckpointBackup(unittest.TestCase):
    def test_passive_with_reader(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "cp.sqlite3")
            # open a reader connection
            reader = db.connect()
            try:
                r = db.checkpoint_passive()
                self.assertIn("log_frames", r)
            finally:
                reader.close()

    def test_full_after_readers_closed(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "cf.sqlite3")
            r = db.checkpoint_full()
            self.assertIn("checkpointed_frames", r)

    def test_backup_restore_wal_active(self):
        with tempfile.TemporaryDirectory() as td:
            src_path = Path(td) / "src.sqlite3"
            reg = Registry(src_path)
            m = RunManifest(
                run_id="run-bak",
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
            dest = Path(td) / "backup.sqlite3"
            reg.db.backup_to(dest)
            reg2 = Registry(dest)
            self.assertIsNotNone(reg2.get_run("run-bak"))
            self.assertEqual(reg2.db.integrity_check(), "ok")
            self.assertEqual(reg2.db.wal_status()["journal_mode"].lower(), "wal")


if __name__ == "__main__":
    unittest.main()
