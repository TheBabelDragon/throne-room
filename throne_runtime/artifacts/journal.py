"""Durable promotion journal for crash-consistent isolation transitions."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class JournalState(str, Enum):
    PREPARED = "PREPARED"
    DESTINATION_CREATED = "DESTINATION_CREATED"
    DESTINATION_VERIFIED = "DESTINATION_VERIFIED"
    REGISTRY_UPDATED = "REGISTRY_UPDATED"
    AUDIT_COMMITTED = "AUDIT_COMMITTED"
    OLD_LOCATION_REMOVED = "OLD_LOCATION_REMOVED"
    COMPLETED = "COMPLETED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    ROLLED_BACK = "ROLLED_BACK"


# Only truly terminal states — RECOVERY_REQUIRED remains visible to recovery.
TERMINAL_STATES = frozenset(
    {
        JournalState.COMPLETED,
        JournalState.ROLLED_BACK,
    }
)


@dataclass
class JournalEntry:
    promotion_id: str
    artifact_id: str
    run_id: str
    state: JournalState
    old_isolation: str
    new_isolation: str
    old_location: str
    new_location: str
    content_hash: str
    size_bytes: int
    original_filename: str
    actor: str
    reason: str
    snapshot_json: str
    updated_at: str
    detail: str = ""
    retry_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "promotion_id": self.promotion_id,
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "state": self.state.value,
            "old_isolation": self.old_isolation,
            "new_isolation": self.new_isolation,
            "old_location": self.old_location,
            "new_location": self.new_location,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "original_filename": self.original_filename,
            "actor": self.actor,
            "reason": self.reason,
            "snapshot_json": self.snapshot_json,
            "updated_at": self.updated_at,
            "detail": self.detail,
            "retry_count": self.retry_count,
        }


class PromotionJournal:
    def __init__(self, db_path: Path, lock: threading.RLock | None = None) -> None:
        self.db_path = Path(db_path)
        self._lock = lock or threading.RLock()
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
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS promotion_journal (
                        promotion_id TEXT PRIMARY KEY,
                        artifact_id TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        old_isolation TEXT NOT NULL,
                        new_isolation TEXT NOT NULL,
                        old_location TEXT,
                        new_location TEXT,
                        content_hash TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        original_filename TEXT NOT NULL,
                        actor TEXT,
                        reason TEXT,
                        snapshot_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        detail TEXT,
                        retry_count INTEGER DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_journal_artifact
                        ON promotion_journal(artifact_id);
                    CREATE INDEX IF NOT EXISTS idx_journal_state
                        ON promotion_journal(state);
                    """
                )
                # Idempotent column add for pre-migration DBs
                cols = {
                    r[1]
                    for r in conn.execute("PRAGMA table_info(promotion_journal)").fetchall()
                }
                if "retry_count" not in cols:
                    conn.execute(
                        "ALTER TABLE promotion_journal ADD COLUMN retry_count INTEGER DEFAULT 0"
                    )
                conn.commit()
            finally:
                conn.close()

    def put(self, entry: JournalEntry) -> None:
        entry.updated_at = _utc_now()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO promotion_journal (
                        promotion_id, artifact_id, run_id, state,
                        old_isolation, new_isolation, old_location, new_location,
                        content_hash, size_bytes, original_filename,
                        actor, reason, snapshot_json, updated_at, detail, retry_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(promotion_id) DO UPDATE SET
                        state=excluded.state,
                        old_location=excluded.old_location,
                        new_location=excluded.new_location,
                        updated_at=excluded.updated_at,
                        detail=excluded.detail,
                        snapshot_json=excluded.snapshot_json,
                        retry_count=excluded.retry_count
                    """,
                    (
                        entry.promotion_id,
                        entry.artifact_id,
                        entry.run_id,
                        entry.state.value,
                        entry.old_isolation,
                        entry.new_isolation,
                        entry.old_location,
                        entry.new_location,
                        entry.content_hash,
                        entry.size_bytes,
                        entry.original_filename,
                        entry.actor,
                        entry.reason,
                        entry.snapshot_json,
                        entry.updated_at,
                        entry.detail,
                        entry.retry_count,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, promotion_id: str) -> JournalEntry | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM promotion_journal WHERE promotion_id = ?",
                    (promotion_id,),
                ).fetchone()
                if not row:
                    return None
                return self._row(row)
            finally:
                conn.close()

    def list_incomplete(self) -> list[JournalEntry]:
        """Non-terminal entries, including RECOVERY_REQUIRED for retry."""
        with self._lock:
            conn = self._connect()
            try:
                terminal = tuple(s.value for s in TERMINAL_STATES)
                placeholders = ",".join("?" * len(terminal))
                rows = conn.execute(
                    f"SELECT * FROM promotion_journal WHERE state NOT IN ({placeholders}) "
                    f"ORDER BY updated_at",
                    terminal,
                ).fetchall()
                return [self._row(r) for r in rows]
            finally:
                conn.close()

    def list_recovery_required(self) -> list[JournalEntry]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM promotion_journal WHERE state = ? ORDER BY updated_at",
                    (JournalState.RECOVERY_REQUIRED.value,),
                ).fetchall()
                return [self._row(r) for r in rows]
            finally:
                conn.close()

    def _row(self, row: sqlite3.Row) -> JournalEntry:
        keys = row.keys()
        return JournalEntry(
            promotion_id=row["promotion_id"],
            artifact_id=row["artifact_id"],
            run_id=row["run_id"],
            state=JournalState(row["state"]),
            old_isolation=row["old_isolation"],
            new_isolation=row["new_isolation"],
            old_location=row["old_location"] or "",
            new_location=row["new_location"] or "",
            content_hash=row["content_hash"],
            size_bytes=int(row["size_bytes"] or 0),
            original_filename=row["original_filename"],
            actor=row["actor"] or "",
            reason=row["reason"] or "",
            snapshot_json=row["snapshot_json"],
            updated_at=row["updated_at"],
            detail=row["detail"] or "",
            retry_count=int(row["retry_count"] if "retry_count" in keys else 0),
        )
