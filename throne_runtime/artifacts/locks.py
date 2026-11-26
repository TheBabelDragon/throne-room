"""Cross-process artifact promotion locks (SQLite lease with renewal).

Ownership = (owner, token). Release is idempotent when the row is already
gone. Renewal requires the lease to still be unexpired.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .sqlite_db import Database


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
    """Per-artifact cross-process locks backed by SQLite leases."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        database: "Database | None" = None,
        default_ttl_s: float = 60.0,
        lock: threading.RLock | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        from .sqlite_db import Database

        if database is not None:
            self.db = database
        else:
            if db_path is None:
                raise ValueError("db_path or database required")
            self.db = Database(db_path)
        self.default_ttl_s = default_ttl_s
        self._lock = lock or threading.RLock()
        self._owner = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._clock = clock or time.time
        self._ensure_schema()

    def _now(self) -> float:
        return float(self._clock())

    def _ensure_schema(self) -> None:
        with self._lock:
            with self.db.write_transaction() as conn:
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

    def acquire(
        self,
        artifact_id: str,
        *,
        timeout_s: float = 10.0,
        ttl_s: float | None = None,
    ) -> Lease:
        ttl = self.default_ttl_s if ttl_s is None else ttl_s
        token = uuid.uuid4().hex
        deadline = self._now() + timeout_s
        while True:
            now = self._now()
            expires = now + ttl
            with self._lock:
                try:
                    with self.db.write_transaction() as conn:
                        conn.execute(
                            "DELETE FROM artifact_locks WHERE expires_at < ?",
                            (now,),
                        )
                        try:
                            conn.execute(
                                """
                                INSERT INTO artifact_locks
                                    (artifact_id, owner, token, expires_at)
                                VALUES (?, ?, ?, ?)
                                """,
                                (artifact_id, self._owner, token, expires),
                            )
                            return Lease(
                                artifact_id=artifact_id,
                                owner=self._owner,
                                token=token,
                                expires_at=expires,
                            )
                        except sqlite3.IntegrityError:
                            pass
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if "locked" not in msg and "busy" not in msg:
                        raise
            if self._now() >= deadline:
                raise LockTimeout(
                    f"could not acquire lock for {artifact_id} within {timeout_s}s"
                )
            time.sleep(0.05)

    def renew(self, lease: Lease, *, ttl_s: float | None = None) -> Lease:
        """Extend lease only if still owned *and* unexpired.

        Does not mutate ``lease`` unless the UPDATE succeeds.
        """
        ttl = self.default_ttl_s if ttl_s is None else ttl_s
        now = self._now()
        expires = now + ttl
        with self._lock:
            with self.db.write_transaction() as conn:
                cur = conn.execute(
                    """
                    UPDATE artifact_locks
                    SET expires_at = ?
                    WHERE artifact_id = ?
                      AND owner = ?
                      AND token = ?
                      AND expires_at > ?
                    """,
                    (
                        expires,
                        lease.artifact_id,
                        lease.owner,
                        lease.token,
                        now,
                    ),
                )
                if cur.rowcount != 1:
                    raise LockError(
                        "lease renew failed: ownership lost, token mismatch, or expired"
                    )
        lease.expires_at = expires
        return lease

    def release(self, lease: Lease) -> None:
        """Release if still owned. Idempotent if the row is already absent."""
        with self._lock:
            with self.db.write_transaction() as conn:
                row = conn.execute(
                    "SELECT owner, token FROM artifact_locks WHERE artifact_id = ?",
                    (lease.artifact_id,),
                ).fetchone()
                if row is None:
                    return  # already released / reclaimed / never held
                if row["owner"] != lease.owner or row["token"] != lease.token:
                    raise LockError("lock ownership mismatch on release")
                conn.execute(
                    "DELETE FROM artifact_locks WHERE artifact_id = ? AND token = ?",
                    (lease.artifact_id, lease.token),
                )

    def force_release_expired(self) -> int:
        with self._lock:
            with self.db.write_transaction() as conn:
                cur = conn.execute(
                    "DELETE FROM artifact_locks WHERE expires_at < ?",
                    (self._now(),),
                )
                return cur.rowcount or 0
