"""PromotionGate — sole mechanism for changing classification or storage tier.

Performs a real storage transition: place into destination tier, verify hash,
update registry, then remove old-tier exposure. Rollback retains prior state
on any failure. Append-only audit trail is always preserved.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .hashing import sha256_file
from .models import (
    ArtifactRecord,
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    Trust,
)
from .registry import Registry
from .router import ArtifactRouter
from .verifiers import VerifierRegistry, VerificationExecutionRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Permitted isolation transitions (from → allowed targets)
PERMITTED_TRANSITIONS: dict[Isolation, set[Isolation]] = {
    Isolation.QUARANTINED: {
        Isolation.SANDBOXED,
        Isolation.VALIDATED,
        Isolation.REJECTED,
    },
    Isolation.SANDBOXED: {
        Isolation.VALIDATED,
        Isolation.REJECTED,
        Isolation.QUARANTINED,
    },
    Isolation.VALIDATED: {
        Isolation.CERTIFIED_READ_ONLY,
        Isolation.SANDBOXED,
        Isolation.REJECTED,
    },
    Isolation.CERTIFIED_READ_ONLY: {
        Isolation.REJECTED,  # revoke only
    },
    Isolation.REJECTED: {
        Isolation.QUARANTINED,  # re-open for review
    },
}


class PromotionGate:
    def __init__(
        self,
        registry: Registry,
        router: ArtifactRouter | None = None,
        *,
        isolation_manager: Any = None,
        storage: Any = None,
        verifier_registry: VerifierRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.router = router or ArtifactRouter()
        self.isolation = isolation_manager
        self.storage = storage
        self.verifiers = verifier_registry or VerifierRegistry()

    def promote(
        self,
        artifact: ArtifactRecord,
        *,
        target_isolation: Isolation,
        target_evidence: EvidenceGrade | None = None,
        target_trust: Trust | None = None,
        actor: str,
        reason: str,
        policy_rule: str = "",
        verifier_evidence: dict[str, Any] | None = None,
        source_hashes: dict[str, str] | None = None,
        execution_record: VerificationExecutionRecord | None = None,
        source_commit: str = "",
    ) -> PromotionRecord:
        verifier_evidence = dict(verifier_evidence or {})
        source_hashes = dict(source_hashes or {})

        new_evidence = target_evidence or artifact.evidence_grade
        new_trust = target_trust or artifact.trust

        decision = "ALLOWED"
        reject_reason = ""

        # Transition table
        allowed = PERMITTED_TRANSITIONS.get(artifact.isolation, set())
        if target_isolation != artifact.isolation and target_isolation not in allowed:
            decision = "REJECTED"
            reject_reason = (
                f"transition {artifact.isolation.value} → {target_isolation.value} "
                f"not permitted"
            )

        # VALIDATED requires integrity evidence (execution record or prior checks)
        if decision == "ALLOWED" and target_isolation == Isolation.VALIDATED:
            if execution_record is None and not verifier_evidence.get("integrity_ok"):
                decision = "REJECTED"
                reject_reason = "VALIDATED requires validation/integrity evidence"

        # CERTIFIED / formal requires independent verifier execution
        if decision == "ALLOWED" and (
            target_isolation == Isolation.CERTIFIED_READ_ONLY
            or new_evidence in (EvidenceGrade.FORMALLY_PROVED, EvidenceGrade.CERTIFIED)
        ):
            if execution_record is None:
                decision = "REJECTED"
                reject_reason = (
                    "CERTIFIED/FORMALLY_PROVED requires a real verifier execution record; "
                    "caller-attested PASS is insufficient"
                )
            else:
                seen = self.registry.seen_verification_hashes(artifact.artifact_id)
                ok, msg = self.verifiers.validate_record(
                    execution_record,
                    expected_content_hash=artifact.content_hash,
                    expected_artifact_id=artifact.artifact_id,
                    expected_source_commit=source_commit or None,
                    seen_record_hashes=seen,
                )
                if not ok:
                    decision = "REJECTED"
                    reject_reason = msg
                else:
                    try:
                        self.registry.persist_verification_record(
                            execution_record.as_dict()
                        )
                    except ValueError as e:
                        decision = "REJECTED"
                        reject_reason = str(e)
                    else:
                        verifier_evidence = {
                            **verifier_evidence,
                            **execution_record.as_dict(),
                        }

        # Numerical cannot become formal without execution record (already gated)
        if decision == "ALLOWED" and new_evidence in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            if artifact.evidence_grade in (
                EvidenceGrade.EXPLORATORY,
                EvidenceGrade.TESTED,
                EvidenceGrade.NUMERICALLY_CROSSCHECKED,
            ) and execution_record is None:
                decision = "REJECTED"
                reject_reason = (
                    "experimental/numerical evidence cannot promote to formal "
                    "without independent verifier execution"
                )

        # Trust elevation only through gate with evidence
        if decision == "ALLOWED" and new_trust == Trust.TRUSTED:
            if artifact.trust != Trust.TRUSTED and execution_record is None:
                if target_isolation not in (
                    Isolation.VALIDATED,
                    Isolation.CERTIFIED_READ_ONLY,
                ):
                    decision = "REJECTED"
                    reject_reason = "TRUSTED requires validated tier or verifier evidence"

        old_isolation = artifact.isolation
        old_location = artifact.stored_location

        rec = PromotionRecord(
            promotion_id=f"promo-{uuid.uuid4().hex[:12]}",
            artifact_id=artifact.artifact_id,
            run_id=artifact.run_id,
            previous_isolation=old_isolation,
            new_isolation=target_isolation if decision == "ALLOWED" else old_isolation,
            previous_evidence=artifact.evidence_grade,
            new_evidence=new_evidence if decision == "ALLOWED" else artifact.evidence_grade,
            previous_trust=artifact.trust,
            new_trust=new_trust if decision == "ALLOWED" else artifact.trust,
            policy_rule=policy_rule or "promotion_gate",
            actor=actor,
            reason=reason if decision == "ALLOWED" else f"REJECTED: {reject_reason}; requested: {reason}",
            decision=decision,
            timestamp=_utc_now(),
            verifier_evidence=verifier_evidence,
            source_hashes=source_hashes,
        )
        # Always append audit first
        self.registry.append_promotion(rec)

        if decision != "ALLOWED":
            return rec

        # Real storage transition
        new_location = old_location
        try:
            if self.storage is not None and self.isolation is not None:
                blob = self.storage.get_path(artifact.content_hash)
                # Verify blob before placement
                if sha256_file(blob) != artifact.content_hash:
                    raise RuntimeError("destination content hash mismatch before place")
                placed = self.isolation.place_link(
                    artifact.run_id,
                    target_isolation,
                    artifact.original_filename,
                    blob,
                )
                # Verify destination
                if sha256_file(placed) != artifact.content_hash:
                    raise RuntimeError("destination content hash mismatch after place")
                new_location = str(placed)

            artifact.isolation = target_isolation
            artifact.evidence_grade = new_evidence
            artifact.trust = new_trust
            artifact.stored_location = new_location
            artifact.verification_history.append(rec.as_dict())
            self.registry.put_artifact(artifact)

            # Remove old-tier exposure only after successful registry update
            if (
                self.isolation is not None
                and old_isolation != target_isolation
                and old_location
            ):
                old_path = Path(old_location)
                if old_path.exists() and old_path.is_file():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass  # non-fatal; audit already records transition
        except Exception as e:
            # Rollback metadata to prior state; keep audit REJECTED amendment
            artifact.isolation = old_isolation
            artifact.stored_location = old_location
            self.registry.put_artifact(artifact)
            fail = PromotionRecord(
                promotion_id=f"promo-{uuid.uuid4().hex[:12]}",
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                previous_isolation=target_isolation,
                new_isolation=old_isolation,
                previous_evidence=new_evidence,
                new_evidence=artifact.evidence_grade,
                previous_trust=new_trust,
                new_trust=artifact.trust,
                policy_rule="promotion_rollback",
                actor=actor,
                reason=f"ROLLBACK after failure: {e}",
                decision="REJECTED",
                timestamp=_utc_now(),
                verifier_evidence=verifier_evidence,
                source_hashes=source_hashes,
            )
            self.registry.append_promotion(fail)
            rec = fail

        return rec
