"""SQLite registry for runs, artifacts, and promotion audit log."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .manifest import compute_manifest_hash
from .models import (
    ArtifactRecord,
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    RunManifest,
    Sensitivity,
    Trust,
)
from .schema import apply_registry_schema
from .sqlite_db import Database, SQLiteSettings


class Registry:
    """Process-safe registry backed by a shared WAL Database."""

    def __init__(
        self,
        db_path: Path,
        *,
        database: Database | None = None,
        settings: SQLiteSettings | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = database or Database(self.db_path, settings=settings)
        with self._lock:
            apply_registry_schema(self.db)

    def _connect(self) -> sqlite3.Connection:
        return self.db.connect()

    def put_run(self, manifest: RunManifest) -> None:
        with self._lock:
            with self.db.write_transaction() as conn:
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

    def get_run(self, run_id: str) -> RunManifest | None:
        with self._lock:
            with self.db.connection() as conn:
                row = conn.execute(
                    "SELECT manifest_json, manifest_hash FROM runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if not row:
                    return None
                data = json.loads(row["manifest_json"])
                m = RunManifest.from_dict(data)
                expected = compute_manifest_hash(m)
                stored = row["manifest_hash"] or m.manifest_hash
                if stored and stored != expected:
                    raise ValueError(
                        f"corrupted manifest for {run_id}: stored hash mismatch"
                    )
                return m

    def list_runs(self, project: str | None = None) -> list[RunManifest]:
        with self._lock:
            with self.db.connection() as conn:
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

    def put_artifact(self, rec: ArtifactRecord) -> None:
        with self._lock:
            with self.db.write_transaction() as conn:
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

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock:
            with self.db.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
                ).fetchone()
                if not row:
                    return None
                return self._row_to_artifact(row)

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        with self._lock:
            with self.db.connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at",
                    (run_id,),
                ).fetchall()
                return [self._row_to_artifact(r) for r in rows]

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
            with self.db.write_transaction() as conn:
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

    def list_promotions(
        self, artifact_id: str | None = None, run_id: str | None = None
    ) -> list[PromotionRecord]:
        with self._lock:
            with self.db.connection() as conn:
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

    def persist_verification_record(self, record_dict: dict[str, Any]) -> None:
        record_hash = record_dict.get("record_hash") or ""
        nonce = record_dict.get("nonce") or ""
        if not record_hash:
            raise ValueError("verification record missing record_hash")
        if not record_dict.get("signature"):
            raise ValueError("verification record missing signature")
        with self._lock:
            with self.db.write_transaction() as conn:
                existing = conn.execute(
                    "SELECT record_id FROM verification_records WHERE record_hash = ?",
                    (record_hash,),
                ).fetchone()
                if existing:
                    raise ValueError("replayed verification record rejected")
                if nonce:
                    existing_n = conn.execute(
                        "SELECT record_id FROM verification_records WHERE nonce = ?",
                        (nonce,),
                    ).fetchone()
                    if existing_n:
                        raise ValueError("replayed verification record rejected (nonce)")
                conn.execute(
                    """
                    INSERT INTO verification_records (
                        record_id, record_hash, nonce, artifact_id, content_hash,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_dict["record_id"],
                        record_hash,
                        nonce,
                        record_dict["artifact_id"],
                        record_dict["content_hash"],
                        json.dumps(record_dict, sort_keys=True),
                        record_dict.get("executed_at", ""),
                    ),
                )

    def seen_verification_hashes(self, artifact_id: str) -> set[str]:
        with self._lock:
            with self.db.connection() as conn:
                rows = conn.execute(
                    "SELECT record_hash FROM verification_records WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchall()
                return {r["record_hash"] for r in rows}

    def seen_verification_nonces(self, artifact_id: str) -> set[str]:
        with self._lock:
            with self.db.connection() as conn:
                rows = conn.execute(
                    "SELECT nonce FROM verification_records "
                    "WHERE artifact_id = ? AND nonce IS NOT NULL AND nonce != ''",
                    (artifact_id,),
                ).fetchall()
                return {r["nonce"] for r in rows}
