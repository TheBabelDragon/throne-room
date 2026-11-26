"""Cross-process artifact promotion locks (SQLite lease).

Thread locks alone cannot serialize independent processes. This module uses
atomic INSERT into a lease table with ownership tokens and expiration.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


class LockTimeout(TimeoutError):
    pass


class LockError(RuntimeError):
    pass


@dataclass
class Lease:
    artifact_id: str
    owner: str
    token: str
    expires_at: float


class ArtifactLockManager:
    """Per-artifact cross-process locks backed by SQLite."""

    def __init__(
        self,
        db_path: Path,
        *,
        default_ttl_s: float = 60.0,
        lock: threading.RLock | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.default_ttl_s = default_ttl_s
        self._lock = lock or threading.RLock()
        self._owner = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifact_locks (
                        artifact_id TEXT PRIMARY KEY,
                        owner TEXT NOT NULL,
                        token TEXT NOT NULL,
                        expires_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def acquire(
        self, artifact_id: str, *,
        timeout_s: float = 10.0,
        ttl_s: float | None = None,
    ) -> Lease:
        ttl = self.default_ttl_s if ttl_s is None else ttl_s
        token = uuid.uuid4().hex
        deadline = time.time() + timeout_s
        while True:
            now = time.time()
            expires = now + ttl
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    # Purge expired
                    conn.execute(
                        "DELETE FROM artifact_locks WHERE expires_at < ?",
                        (now,),
                    )
                    try:
                        conn.execute(
                            """
                            INSERT INTO artifact_locks (artifact_id, owner, token, expires_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (artifact_id, self._owner, token, expires),
                        )
                        conn.commit()
                        return Lease(
                            artifact_id=artifact_id,
                            owner=self._owner,
                            token=token,
                            expires_at=expires,
                        )
                    except sqlite3.IntegrityError:
                        conn.rollback()
                finally:
                    conn.close()
            if time.time() >= deadline:
                raise LockTimeout(
                    f"could not acquire lock for {artifact_id} within {timeout_s}s"
                )
            time.sleep(0.05)

    def release(self, lease: Lease) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT owner, token FROM artifact_locks WHERE artifact_id = ?",
                    (lease.artifact_id,),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return
                if row["owner"] != lease.owner or row["token"] != lease.token:
                    conn.rollback()
                    raise LockError("lock ownership mismatch on release")
                conn.execute(
                    "DELETE FROM artifact_locks WHERE artifact_id = ? AND token = ?",
                    (lease.artifact_id, lease.token),
                )
                conn.commit()
            finally:
                conn.close()

    def force_release_expired(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM artifact_locks WHERE expires_at < ?",
                    (time.time(),),
                )
                conn.commit()
                return cur.rowcount or 0
            finally:
                conn.close()
