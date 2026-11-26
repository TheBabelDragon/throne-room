"""SQLite registry for runs, artifacts, and promotion audit log."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import (
    ArtifactRecord,
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    RunManifest,
    Sensitivity,
    Trust,
)
from .manifest import compute_manifest_hash


class Registry:
    """Process-safe (threaded) SQLite registry."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
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
                    );

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
                    );

                    CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
                    CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(content_hash);

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
                    );

                    CREATE INDEX IF NOT EXISTS idx_promotions_artifact ON promotions(artifact_id);

                    CREATE TABLE IF NOT EXISTS verification_records (
                        record_id TEXT PRIMARY KEY,
                        record_hash TEXT NOT NULL UNIQUE,
                        artifact_id TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_ver_records_artifact
                        ON verification_records(artifact_id);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def put_run(self, manifest: RunManifest) -> None:
        """UPSERT run — never delete/recreate a referenced parent row."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, project, subsystem, run_type, created_at,
                        source_commit, parent_run, trust, evidence_grade,
                        isolation, sensitivity, status, manifest_json, manifest_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        project=excluded.project,
                        subsystem=excluded.subsystem,
                        run_type=excluded.run_type,
                        created_at=excluded.created_at,
                        source_commit=excluded.source_commit,
                        parent_run=excluded.parent_run,
                        trust=excluded.trust,
                        evidence_grade=excluded.evidence_grade,
                        isolation=excluded.isolation,
                        sensitivity=excluded.sensitivity,
                        status=excluded.status,
                        manifest_json=excluded.manifest_json,
                        manifest_hash=excluded.manifest_hash
                    """,
                    (
                        manifest.run_id,
                        manifest.project,
                        manifest.subsystem,
                        manifest.run_type,
                        manifest.created_at,
                        manifest.source_commit,
                        manifest.parent_run,
                        manifest.trust.value,
                        manifest.evidence_grade.value,
                        manifest.isolation.value,
                        manifest.sensitivity.value,
                        manifest.status.value,
                        json.dumps(manifest.as_dict(), sort_keys=True),
                        manifest.manifest_hash,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_run(self, run_id: str) -> RunManifest | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT manifest_json, manifest_hash FROM runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if not row:
                    return None
                data = json.loads(row["manifest_json"])
                m = RunManifest.from_dict(data)
                # Integrity: recompute and compare stored hash
                expected = compute_manifest_hash(m)
                stored = row["manifest_hash"] or m.manifest_hash
                if stored and stored != expected:
                    raise ValueError(
                        f"corrupted manifest for {run_id}: "
                        f"stored hash mismatch"
                    )
                return m
            finally:
                conn.close()

    def list_runs(self, project: str | None = None) -> list[RunManifest]:
        with self._lock:
            conn = self._connect()
            try:
                if project:
                    rows = conn.execute(
                        "SELECT manifest_json FROM runs WHERE project = ? ORDER BY created_at",
                        (project,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT manifest_json FROM runs ORDER BY created_at"
                    ).fetchall()
                return [RunManifest.from_dict(json.loads(r["manifest_json"])) for r in rows]
            finally:
                conn.close()

    def put_artifact(self, rec: ArtifactRecord) -> None:
        """UPSERT artifact — preserve row identity under concurrent updates."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO artifacts (
                        artifact_id, run_id, content_hash, original_filename,
                        stored_location, media_type, size_bytes, source_subsystem,
                        parent_run, trust, evidence_grade, isolation, sensitivity,
                        created_at, verification_history
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(artifact_id) DO UPDATE SET
                        run_id=excluded.run_id,
                        content_hash=excluded.content_hash,
                        original_filename=excluded.original_filename,
                        stored_location=excluded.stored_location,
                        media_type=excluded.media_type,
                        size_bytes=excluded.size_bytes,
                        source_subsystem=excluded.source_subsystem,
                        parent_run=excluded.parent_run,
                        trust=excluded.trust,
                        evidence_grade=excluded.evidence_grade,
                        isolation=excluded.isolation,
                        sensitivity=excluded.sensitivity,
                        created_at=excluded.created_at,
                        verification_history=excluded.verification_history
                    """,
                    (
                        rec.artifact_id,
                        rec.run_id,
                        rec.content_hash,
                        rec.original_filename,
                        rec.stored_location,
                        rec.media_type,
                        rec.size_bytes,
                        rec.source_subsystem,
                        rec.parent_run,
                        rec.trust.value,
                        rec.evidence_grade.value,
                        rec.isolation.value,
                        rec.sensitivity.value,
                        rec.created_at,
                        json.dumps(rec.verification_history),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
                ).fetchone()
                if not row:
                    return None
                return self._row_to_artifact(row)
            finally:
                conn.close()

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at",
                    (run_id,),
                ).fetchall()
                return [self._row_to_artifact(r) for r in rows]
            finally:
                conn.close()

    def _row_to_artifact(self, row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            run_id=row["run_id"],
            content_hash=row["content_hash"],
            original_filename=row["original_filename"],
            stored_location=row["stored_location"],
            media_type=row["media_type"] or "application/octet-stream",
            size_bytes=int(row["size_bytes"] or 0),
            source_subsystem=row["source_subsystem"] or "",
            parent_run=row["parent_run"],
            trust=Trust(row["trust"]),
            evidence_grade=EvidenceGrade(row["evidence_grade"]),
            isolation=Isolation(row["isolation"]),
            sensitivity=Sensitivity(row["sensitivity"]),
            created_at=row["created_at"],
            verification_history=json.loads(row["verification_history"] or "[]"),
        )

    def append_promotion(self, rec: PromotionRecord) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO promotions (
                        promotion_id, artifact_id, run_id,
                        previous_isolation, new_isolation,
                        previous_evidence, new_evidence,
                        previous_trust, new_trust,
                        policy_rule, actor, reason, decision, timestamp,
                        verifier_evidence, source_hashes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.promotion_id,
                        rec.artifact_id,
                        rec.run_id,
                        rec.previous_isolation.value,
                        rec.new_isolation.value,
                        rec.previous_evidence.value,
                        rec.new_evidence.value,
                        rec.previous_trust.value,
                        rec.new_trust.value,
                        rec.policy_rule,
                        rec.actor,
                        rec.reason,
                        rec.decision,
                        rec.timestamp,
                        json.dumps(rec.verifier_evidence),
                        json.dumps(rec.source_hashes),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_promotions(
        self, artifact_id: str | None = None, run_id: str | None = None
    ) -> list[PromotionRecord]:
        with self._lock:
            conn = self._connect()
            try:
                if artifact_id:
                    rows = conn.execute(
                        "SELECT * FROM promotions WHERE artifact_id = ? ORDER BY timestamp",
                        (artifact_id,),
                    ).fetchall()
                elif run_id:
                    rows = conn.execute(
                        "SELECT * FROM promotions WHERE run_id = ? ORDER BY timestamp",
                        (run_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM promotions ORDER BY timestamp"
                    ).fetchall()
                out: list[PromotionRecord] = []
                for r in rows:
                    out.append(
                        PromotionRecord(
                            promotion_id=r["promotion_id"],
                            artifact_id=r["artifact_id"],
                            run_id=r["run_id"],
                            previous_isolation=Isolation(r["previous_isolation"]),
                            new_isolation=Isolation(r["new_isolation"]),
                            previous_evidence=EvidenceGrade(r["previous_evidence"]),
                            new_evidence=EvidenceGrade(r["new_evidence"]),
                            previous_trust=Trust(r["previous_trust"]),
                            new_trust=Trust(r["new_trust"]),
                            policy_rule=r["policy_rule"] or "",
                            actor=r["actor"] or "",
                            reason=r["reason"] or "",
                            decision=r["decision"] or "",
                            timestamp=r["timestamp"],
                            verifier_evidence=json.loads(r["verifier_evidence"] or "{}"),
                            source_hashes=json.loads(r["source_hashes"] or "{}"),
                        )
                    )
                return out
            finally:
                conn.close()

    def persist_verification_record(self, record_dict: dict[str, Any]) -> None:
        """Store a sealed verification execution record; reject hash collisions (replay)."""
        record_hash = record_dict.get("record_hash") or ""
        if not record_hash:
            raise ValueError("verification record missing record_hash")
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT record_id FROM verification_records WHERE record_hash = ?",
                    (record_hash,),
                ).fetchone()
                if existing:
                    raise ValueError("replayed verification record rejected")
                conn.execute(
                    """
                    INSERT INTO verification_records (
                        record_id, record_hash, artifact_id, content_hash,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_dict["record_id"],
                        record_hash,
                        record_dict["artifact_id"],
                        record_dict["content_hash"],
                        json.dumps(record_dict, sort_keys=True),
                        record_dict.get("executed_at", ""),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def seen_verification_hashes(self, artifact_id: str) -> set[str]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT record_hash FROM verification_records WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchall()
                return {r["record_hash"] for r in rows}
            finally:
                conn.close()
