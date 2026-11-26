"""Explicit atomic schema migrations for the artifact registry database.

Does not use executescript() (which auto-commits). Each migration step runs as
individual statements inside a single BEGIN IMMEDIATE transaction so failures
roll back the whole migration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

    from .sqlite_db import Database


# Ordered list of (statement,). Keep each step a single statement.
_REGISTRY_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        project TEXT NOT NULL,
        subsystem TEXT NOT NULL,
        run_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        source_commit TEXT,
        parent_run TEXT,
        trust TEXT NOT NULL,
        evidence_grade TEXT NOT NULL,
        isolation TEXT NOT NULL,
        sensitivity TEXT NOT NULL,
        status TEXT NOT NULL,
        manifest_json TEXT NOT NULL,
        manifest_hash TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        stored_location TEXT NOT NULL,
        media_type TEXT,
        size_bytes INTEGER,
        source_subsystem TEXT,
        parent_run TEXT,
        trust TEXT NOT NULL,
        evidence_grade TEXT NOT NULL,
        isolation TEXT NOT NULL,
        sensitivity TEXT NOT NULL,
        created_at TEXT NOT NULL,
        verification_history TEXT,
        FOREIGN KEY (run_id) REFERENCES runs(run_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(content_hash)",
    """
    CREATE TABLE IF NOT EXISTS promotions (
        promotion_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        previous_isolation TEXT,
        new_isolation TEXT,
        previous_evidence TEXT,
        new_evidence TEXT,
        previous_trust TEXT,
        new_trust TEXT,
        policy_rule TEXT,
        actor TEXT,
        reason TEXT,
        decision TEXT,
        timestamp TEXT NOT NULL,
        verifier_evidence TEXT,
        source_hashes TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_promotions_artifact ON promotions(artifact_id)",
    """
    CREATE TABLE IF NOT EXISTS verification_records (
        record_id TEXT PRIMARY KEY,
        record_hash TEXT NOT NULL UNIQUE,
        nonce TEXT,
        artifact_id TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ver_records_artifact ON verification_records(artifact_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ver_records_nonce
        ON verification_records(nonce)
        WHERE nonce IS NOT NULL AND nonce != ''
    """,
]

_JOURNAL_DDL: list[str] = [
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
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_journal_artifact ON promotion_journal(artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_journal_state ON promotion_journal(state)",
]

_LOCKS_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS artifact_locks (
        artifact_id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        token TEXT NOT NULL,
        expires_at REAL NOT NULL
    )
    """,
]


def _table_columns(conn: "sqlite3.Connection", table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def apply_registry_schema(db: "Database") -> None:
    with db.write_transaction() as conn:
        for stmt in _REGISTRY_DDL:
            conn.execute(stmt)


def apply_journal_schema(db: "Database") -> None:
    with db.write_transaction() as conn:
        for stmt in _JOURNAL_DDL:
            conn.execute(stmt)
        # Idempotent column upgrade
        cols = _table_columns(conn, "promotion_journal")
        if "retry_count" not in cols:
            conn.execute(
                "ALTER TABLE promotion_journal "
                "ADD COLUMN retry_count INTEGER DEFAULT 0"
            )


def apply_locks_schema(db: "Database") -> None:
    with db.write_transaction() as conn:
        for stmt in _LOCKS_DDL:
            conn.execute(stmt)


def apply_all_schema(db: "Database") -> None:
    """Apply registry + journal + locks schema (each in its own transaction)."""
    apply_registry_schema(db)
    apply_journal_schema(db)
    apply_locks_schema(db)
