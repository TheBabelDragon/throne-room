"""Cross-process artifact lock tests."""

from __future__ import annotations

import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path

from throne_runtime.artifacts.locks import ArtifactLockManager, LockTimeout


def _hold(db: str, artifact_id: str, hold_s: float, q) -> None:
    lm = ArtifactLockManager(Path(db), default_ttl_s=5.0)
    lease = lm.acquire(artifact_id, timeout_s=2.0)
    q.put("held")
    time.sleep(hold_s)
    lm.release(lease)
    q.put("released")


class TestArtifactLocks(unittest.TestCase):
    def test_timeout_when_held(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "reg.sqlite3"
            # Bootstrap schema
            ArtifactLockManager(db)
            q: mp.Queue = mp.Queue()
            p = mp.Process(target=_hold, args=(str(db), "art-1", 2.0, q))
            p.start()
            self.assertEqual(q.get(timeout=5), "held")
            lm = ArtifactLockManager(db)
            with self.assertRaises(LockTimeout):
                lm.acquire("art-1", timeout_s=0.3)
            p.join(timeout=5)
            self.assertEqual(q.get(timeout=5), "released")
            # After release, acquire succeeds
            lease = lm.acquire("art-1", timeout_s=2.0)
            lm.release(lease)

    def test_expired_lock_reclaimed(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "reg.sqlite3"
            lm = ArtifactLockManager(db, default_ttl_s=0.2)
            lease = lm.acquire("art-x", timeout_s=1.0, ttl_s=0.2)
            time.sleep(0.35)
            lm2 = ArtifactLockManager(db, default_ttl_s=1.0)
            lease2 = lm2.acquire("art-x", timeout_s=1.0)
            lm2.release(lease2)
            # Original release may fail ownership — expected after expiry reclaim
            try:
                lm.release(lease)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
