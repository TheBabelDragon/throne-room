"""Centralized SQLite configuration for registry, journal, and locks.

WAL and durability settings are verified on *every* connection before use.
There is no silent fallback to DELETE journal mode or weaker synchronous.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class SQLiteConfigError(RuntimeError):
    pass


DEFAULT_BUSY_TIMEOUT_MS = 30_000
DEFAULT_SYNCHRONOUS = "FULL"

_SYNC_LEVELS = {"OFF": 0, "NORMAL": 1, "FULL": 2, "EXTRA": 3}


@dataclass(frozen=True)
class SQLiteSettings:
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
    synchronous: str = DEFAULT_SYNCHRONOUS  # FULL unless explicitly configured


class Database:
    """Shared SQLite database handle with verified WAL + FULL synchronous."""

    def __init__(self, path: Path | str, settings: SQLiteSettings | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = settings or SQLiteSettings()
        if self.settings.synchronous.upper() not in _SYNC_LEVELS:
            raise SQLiteConfigError(
                f"unsupported synchronous setting: {self.settings.synchronous!r}"
            )
        self._init_lock = threading.Lock()
        self._initialized = False
        self._ensure_wal()

    def _connect_raw(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path), timeout=self.settings.busy_timeout_ms / 1000.0
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _apply_and_verify(self, conn: sqlite3.Connection) -> None:
        """Apply required PRAGMAs and fail closed if any are weaker/unexpected.

        Order: settings applied before any caller transaction begins.
        """
        # journal_mode — prefer already-WAL; set if needed
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if str(mode).lower() != "wal":
            mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise SQLiteConfigError(
                f"expected journal_mode=wal, got {mode!r}"
            )

        # synchronous — apply requested level, then read back
        want_name = self.settings.synchronous.upper()
        want_level = _SYNC_LEVELS[want_name]
        conn.execute(f"PRAGMA synchronous={want_name}")
        got_sync = int(conn.execute("PRAGMA synchronous").fetchone()[0])
        # EXTRA (3) is acceptable when FULL (2) requested
        if want_level >= 2:
            if got_sync < 2:
                raise SQLiteConfigError(
                    f"synchronous weaker than FULL: got {got_sync}"
                )
        elif got_sync != want_level:
            raise SQLiteConfigError(
                f"synchronous mismatch: want {want_level}, got {got_sync}"
            )

        conn.execute("PRAGMA foreign_keys=ON")
        fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        if fk != 1:
            raise SQLiteConfigError(f"foreign_keys not enabled: {fk}")

        conn.execute(f"PRAGMA busy_timeout={int(self.settings.busy_timeout_ms)}")
        busy = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
        if busy < int(self.settings.busy_timeout_ms):
            raise SQLiteConfigError(
                f"busy_timeout too low: {busy} < {self.settings.busy_timeout_ms}"
            )

        # Final journal_mode check after all PRAGMAs
        mode2 = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if mode2 != "wal":
            raise SQLiteConfigError(f"journal_mode degraded to {mode2!r}")

    def _ensure_wal(self) -> None:
        with self._init_lock:
            conn = self._connect_raw()
            try:
                self._apply_and_verify(conn)
                conn.commit()
            finally:
                conn.close()

            # Verify survives close/reopen
            conn2 = self._connect_raw()
            try:
                self._apply_and_verify(conn2)
            finally:
                conn2.close()

            self._initialized = True

    def connect(self) -> sqlite3.Connection:
        """Open a connection with durability settings applied and verified."""
        if not self._initialized:
            self._ensure_wal()
        conn = self._connect_raw()
        try:
            self._apply_and_verify(conn)
        except Exception:
            conn.close()
            raise
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write_transaction(self) -> Iterator[sqlite3.Connection]:
        """BEGIN IMMEDIATE write transaction; short-lived. No FS work inside."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def wal_status(self) -> dict[str, Any]:
        with self.connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            try:
                ckpt = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                busy_c, log_frames, checkpointed = (
                    int(ckpt[0]),
                    int(ckpt[1]),
                    int(ckpt[2]),
                )
                ckpt_err = ""
            except sqlite3.Error as e:
                busy_c, log_frames, checkpointed = -1, -1, -1
                ckpt_err = str(e)
            return {
                "path": str(self.path),
                "journal_mode": str(mode),
                "synchronous": int(sync),
                "foreign_keys": int(fk),
                "busy_timeout_ms": int(busy),
                "wal_checkpoint_passive": {
                    "busy": busy_c,
                    "log_frames": log_frames,
                    "checkpointed_frames": checkpointed,
                    "error": ckpt_err,
                },
            }

    def checkpoint_passive(self) -> dict[str, int]:
        with self.connection() as conn:
            row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            return {
                "busy": int(row[0]),
                "log_frames": int(row[1]),
                "checkpointed_frames": int(row[2]),
            }

    def checkpoint_full(self) -> dict[str, int]:
        """Controlled maintenance only — not for hot ingest/promote paths."""
        with self.connection() as conn:
            row = conn.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            return {
                "busy": int(row[0]),
                "log_frames": int(row[1]),
                "checkpointed_frames": int(row[2]),
            }

    def backup_to(self, dest: Path | str) -> None:
        """Online backup via sqlite3 backup API while WAL is active."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = self.connect()
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()

    def integrity_check(self) -> str:
        with self.connection() as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return str(row[0])
