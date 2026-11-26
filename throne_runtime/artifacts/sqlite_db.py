"""Centralized SQLite configuration for registry, journal, and locks.

WAL is configured once at database initialization and verified on open.
There is no silent fallback to DELETE journal mode.

Filesystem artifact operations remain outside SQLite transactions; durability
across the FS/DB boundary is handled by the promotion journal, not WAL alone.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from contextlib import contextmanager


class SQLiteConfigError(RuntimeError):
    pass


# Defaults aligned with promotion lock timeouts (seconds → ms)
DEFAULT_BUSY_TIMEOUT_MS = 30_000
DEFAULT_SYNCHRONOUS = "FULL"


@dataclass(frozen=True)
class SQLiteSettings:
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
    synchronous: str = DEFAULT_SYNCHRONOUS  # FULL for registry/journal durability


class Database:
    """Shared SQLite database handle with verified WAL mode."""

    def __init__(self, path: Path | str, settings: SQLiteSettings | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = settings or SQLiteSettings()
        self._init_lock = threading.Lock()
        self._initialized = False
        self._ensure_wal()

    def _connect_raw(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=self.settings.busy_timeout_ms / 1000.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _apply_connection_pragmas(self, conn: sqlite3.Connection) -> None:
        # Per-connection requirements
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={int(self.settings.busy_timeout_ms)}")

    def _ensure_wal(self) -> None:
        """Configure WAL once; verify; fail closed if not WAL."""
        with self._init_lock:
            if self._initialized:
                # Re-verify on subsequent opens of Database object
                conn = self._connect_raw()
                try:
                    self._apply_connection_pragmas(conn)
                    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    if str(mode).lower() != "wal":
                        raise SQLiteConfigError(
                            f"expected journal_mode=wal, got {mode!r}"
                        )
                finally:
                    conn.close()
                return

            conn = self._connect_raw()
            try:
                # Set WAL during initialization
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(mode).lower() != "wal":
                    raise SQLiteConfigError(
                        f"failed to establish WAL journal_mode; got {mode!r}"
                    )
                # Durability for registry/journal
                sync = conn.execute(
                    f"PRAGMA synchronous={self.settings.synchronous}"
                ).fetchone()
                # Read back
                sync_val = conn.execute("PRAGMA synchronous").fetchone()[0]
                # SQLite returns 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA
                expected = {"OFF": 0, "NORMAL": 1, "FULL": 2, "EXTRA": 3}.get(
                    self.settings.synchronous.upper(), 2
                )
                if int(sync_val) != expected and self.settings.synchronous.upper() == "FULL":
                    # EXTRA (3) is acceptable strengthening of FULL
                    if int(sync_val) < 2:
                        raise SQLiteConfigError(
                            f"synchronous weaker than FULL: {sync_val}"
                        )
                self._apply_connection_pragmas(conn)
                conn.commit()
            finally:
                conn.close()

            # Verify WAL survives close/reopen
            conn2 = self._connect_raw()
            try:
                mode2 = conn2.execute("PRAGMA journal_mode").fetchone()[0]
                if str(mode2).lower() != "wal":
                    raise SQLiteConfigError(
                        f"WAL not persisted after reopen; got {mode2!r}"
                    )
                self._apply_connection_pragmas(conn2)
            finally:
                conn2.close()

            self._initialized = True

    def connect(self) -> sqlite3.Connection:
        """Open a connection with foreign_keys and busy_timeout applied."""
        if not self._initialized:
            self._ensure_wal()
        conn = self._connect_raw()
        self._apply_connection_pragmas(conn)
        # Confirm WAL still active (fail closed)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if str(mode).lower() != "wal":
            conn.close()
            raise SQLiteConfigError(f"journal_mode is {mode!r}, not wal")
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
        """BEGIN IMMEDIATE write transaction; short-lived."""
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
            # wal_checkpoint returns (busy, log, checkpointed)
            try:
                # PASSIVE does not block writers
                ckpt = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                busy_c, log_frames, checkpointed = (
                    int(ckpt[0]),
                    int(ckpt[1]),
                    int(ckpt[2]),
                )
            except sqlite3.Error as e:
                busy_c, log_frames, checkpointed = -1, -1, -1
                ckpt_err = str(e)
            else:
                ckpt_err = ""
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

    def integrity_check(self) -> str:
        with self.connection() as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return str(row[0])
