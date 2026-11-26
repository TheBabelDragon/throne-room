"""Registry helpers for exact promotion audit reconciliation."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .models import (
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    Trust,
)


def get_promotion(registry: Any, promotion_id: str) -> PromotionRecord | None:
    with registry._lock:
        conn = registry._connect()
        try:
            row = conn.execute(
                "SELECT * FROM promotions WHERE promotion_id = ?",
                (promotion_id,),
            ).fetchone()
            if not row:
                return None
            return PromotionRecord(
                promotion_id=row["promotion_id"],
                artifact_id=row["artifact_id"],
                run_id=row["run_id"],
                previous_isolation=Isolation(row["previous_isolation"]),
                new_isolation=Isolation(row["new_isolation"]),
                previous_evidence=EvidenceGrade(row["previous_evidence"]),
                new_evidence=EvidenceGrade(row["new_evidence"]),
                previous_trust=Trust(row["previous_trust"]),
                new_trust=Trust(row["new_trust"]),
                policy_rule=row["policy_rule"] or "",
                actor=row["actor"] or "",
                reason=row["reason"] or "",
                decision=row["decision"] or "",
                timestamp=row["timestamp"],
                verifier_evidence=json.loads(row["verifier_evidence"] or "{}"),
                source_hashes=json.loads(row["source_hashes"] or "{}"),
            )
        finally:
            conn.close()


def ensure_audit_record(
    registry: Any,
    rec: PromotionRecord,
) -> str:
    """Idempotent audit ensure.

    Returns:
      'inserted' | 'already_matches'
    Raises:
      ValueError on conflicting existing record
      sqlite3.Error on real DB failures (not treated as duplicate)
    """
    existing = get_promotion(registry, rec.promotion_id)
    if existing is not None:
        if (
            existing.artifact_id == rec.artifact_id
            and existing.run_id == rec.run_id
            and existing.decision == rec.decision
            and existing.previous_isolation == rec.previous_isolation
            and existing.new_isolation == rec.new_isolation
        ):
            return "already_matches"
        raise ValueError(
            f"conflicting audit record for {rec.promotion_id}: "
            f"existing artifact={existing.artifact_id} decision={existing.decision}"
        )
    # Real insert — IntegrityError means concurrent insert of same PK
    try:
        registry.append_promotion(rec)
        return "inserted"
    except sqlite3.IntegrityError:
        # Re-read and compare
        existing = get_promotion(registry, rec.promotion_id)
        if existing is None:
            raise
        if (
            existing.artifact_id == rec.artifact_id
            and existing.run_id == rec.run_id
            and existing.decision == rec.decision
            and existing.previous_isolation == rec.previous_isolation
            and existing.new_isolation == rec.new_isolation
        ):
            return "already_matches"
        raise ValueError(
            f"conflicting audit record after IntegrityError for {rec.promotion_id}"
        )
