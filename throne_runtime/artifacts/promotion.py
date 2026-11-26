"""PromotionGate — sole classification/storage transition mechanism.

Atomic sequence:
1. Verify source blob hash
2. Create destination tier location
3. Verify destination hash+size
4. Update registry metadata
5. Remove previous tier link (failure => not success)
6. Confirm old path gone
7. Append successful audit

Any failure restores all mutable fields and removes new destination link.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from .verifiers import VerificationExecutionRecord, VerifierRegistry


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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
    Isolation.CERTIFIED_READ_ONLY: {Isolation.REJECTED},
    Isolation.REJECTED: {Isolation.QUARANTINED},
}


class PromotionError(RuntimeError):
    pass


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

    def _snapshot(self, artifact: ArtifactRecord) -> dict[str, Any]:
        return {
            "isolation": artifact.isolation,
            "evidence_grade": artifact.evidence_grade,
            "trust": artifact.trust,
            "stored_location": artifact.stored_location,
            "verification_history": deepcopy(artifact.verification_history),
        }

    def _restore(self, artifact: ArtifactRecord, snap: dict[str, Any]) -> None:
        artifact.isolation = snap["isolation"]
        artifact.evidence_grade = snap["evidence_grade"]
        artifact.trust = snap["trust"]
        artifact.stored_location = snap["stored_location"]
        artifact.verification_history = deepcopy(snap["verification_history"])

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
        _fail_at: str | None = None,  # test injection point
    ) -> PromotionRecord:
        verifier_evidence = dict(verifier_evidence or {})
        source_hashes = dict(source_hashes or {})
        new_evidence = target_evidence or artifact.evidence_grade
        new_trust = target_trust or artifact.trust

        decision = "ALLOWED"
        reject_reason = ""

        allowed = PERMITTED_TRANSITIONS.get(artifact.isolation, set())
        if target_isolation != artifact.isolation and target_isolation not in allowed:
            decision = "REJECTED"
            reject_reason = (
                f"transition {artifact.isolation.value} → {target_isolation.value} "
                f"not permitted"
            )

        if decision == "ALLOWED" and target_isolation == Isolation.VALIDATED:
            if execution_record is None:
                decision = "REJECTED"
                reject_reason = "VALIDATED requires authenticated verifier execution"

        if decision == "ALLOWED" and (
            target_isolation == Isolation.CERTIFIED_READ_ONLY
            or new_evidence in (EvidenceGrade.FORMALLY_PROVED, EvidenceGrade.CERTIFIED)
        ):
            if execution_record is None:
                decision = "REJECTED"
                reject_reason = (
                    "CERTIFIED/FORMALLY_PROVED requires authenticated verifier "
                    "execution; caller-attested PASS is insufficient"
                )
            else:
                seen_hashes = self.registry.seen_verification_hashes(artifact.artifact_id)
                seen_nonces = self.registry.seen_verification_nonces(artifact.artifact_id)
                ok, msg = self.verifiers.validate_record(
                    execution_record,
                    expected_content_hash=artifact.content_hash,
                    expected_artifact_id=artifact.artifact_id,
                    expected_source_commit=source_commit or None,
                    seen_record_hashes=seen_hashes,
                    seen_nonces=seen_nonces,
                )
                if not ok:
                    decision = "REJECTED"
                    reject_reason = msg
                elif execution_record.result == "UNSUPPORTED":
                    decision = "REJECTED"
                    reject_reason = "unsupported verifier cannot certify"
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

        if decision == "ALLOWED" and new_evidence in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            if artifact.evidence_grade in (
                EvidenceGrade.EXPLORATORY,
                EvidenceGrade.TESTED,
                EvidenceGrade.NUMERICALLY_CROSSCHECKED,
            ) and (
                execution_record is None or execution_record.result != "PASS"
            ):
                decision = "REJECTED"
                reject_reason = (
                    "experimental/numerical evidence cannot promote to formal "
                    "without authenticated verifier PASS"
                )

        snap = self._snapshot(artifact)
        old_isolation = artifact.isolation
        old_location = artifact.stored_location

        if decision != "ALLOWED":
            rec = PromotionRecord(
                promotion_id=f"promo-{uuid.uuid4().hex[:12]}",
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                previous_isolation=old_isolation,
                new_isolation=old_isolation,
                previous_evidence=artifact.evidence_grade,
                new_evidence=artifact.evidence_grade,
                previous_trust=artifact.trust,
                new_trust=artifact.trust,
                policy_rule=policy_rule or "promotion_gate",
                actor=actor,
                reason=f"REJECTED: {reject_reason}; requested: {reason}",
                decision="REJECTED",
                timestamp=_utc_now(),
                verifier_evidence=verifier_evidence,
                source_hashes=source_hashes,
            )
            self.registry.append_promotion(rec)
            return rec

        new_location = old_location
        placed_path: Path | None = None

        try:
            if self.storage is None or self.isolation is None:
                raise PromotionError("storage/isolation not configured")

            # 1. Source blob
            blob = self.storage.get_path(artifact.content_hash)
            if sha256_file(blob) != artifact.content_hash:
                raise PromotionError("source blob hash mismatch")
            if _fail_at == "source_verify":
                raise PromotionError("injected: source_verify")

            # 2. Destination placement
            placed_path = self.isolation.place_link(
                artifact.run_id,
                target_isolation,
                artifact.original_filename,
                blob,
            )
            if _fail_at == "destination_create":
                raise PromotionError("injected: destination_create")

            # 3. Destination verify
            if sha256_file(placed_path) != artifact.content_hash:
                raise PromotionError("destination content hash mismatch")
            if placed_path.stat().st_size != artifact.size_bytes and artifact.size_bytes:
                raise PromotionError("destination size mismatch")
            if _fail_at == "destination_verify":
                raise PromotionError("injected: destination_verify")

            new_location = str(placed_path)

            # 4. Registry update
            artifact.isolation = target_isolation
            artifact.evidence_grade = new_evidence
            artifact.trust = new_trust
            artifact.stored_location = new_location
            if _fail_at == "registry_update":
                raise PromotionError("injected: registry_update")
            # history append after success path builds rec

            # 5. Remove old tier (must succeed for promotion success)
            if old_isolation != target_isolation and old_location:
                old_path = Path(old_location)
                if old_path.exists() and old_path.is_file():
                    try:
                        old_path.unlink()
                    except OSError as e:
                        raise PromotionError(f"old-tier removal failed: {e}") from e
                if _fail_at == "old_tier_removal":
                    raise PromotionError("injected: old_tier_removal")
                # 6. Confirm gone (or hardlink still valid but path removed)
                if old_path.exists() and old_path.resolve() != Path(new_location).resolve():
                    raise PromotionError("old-tier path still accessible after removal")

            # Build success audit before registry write of history
            rec = PromotionRecord(
                promotion_id=f"promo-{uuid.uuid4().hex[:12]}",
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                previous_isolation=old_isolation,
                new_isolation=target_isolation,
                previous_evidence=snap["evidence_grade"],
                new_evidence=new_evidence,
                previous_trust=snap["trust"],
                new_trust=new_trust,
                policy_rule=policy_rule or "promotion_gate",
                actor=actor,
                reason=reason,
                decision="ALLOWED",
                timestamp=_utc_now(),
                verifier_evidence=verifier_evidence,
                source_hashes=source_hashes,
            )
            artifact.verification_history.append(rec.as_dict())
            self.registry.put_artifact(artifact)

            if _fail_at == "audit_append":
                raise PromotionError("injected: audit_append")

            # 7. Append audit
            self.registry.append_promotion(rec)
            return rec

        except Exception as e:
            # Rollback filesystem destination
            if placed_path is not None and str(placed_path) != old_location:
                try:
                    if placed_path.exists():
                        placed_path.unlink()
                except OSError:
                    pass
            # Restore metadata
            self._restore(artifact, snap)
            try:
                self.registry.put_artifact(artifact)
            except Exception:
                pass
            fail = PromotionRecord(
                promotion_id=f"promo-{uuid.uuid4().hex[:12]}",
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                previous_isolation=old_isolation,
                new_isolation=old_isolation,
                previous_evidence=snap["evidence_grade"],
                new_evidence=snap["evidence_grade"],
                previous_trust=snap["trust"],
                new_trust=snap["trust"],
                policy_rule="promotion_rollback",
                actor=actor,
                reason=f"ROLLBACK: {e}; requested: {reason}",
                decision="REJECTED",
                timestamp=_utc_now(),
                verifier_evidence=verifier_evidence,
                source_hashes=source_hashes,
            )
            try:
                self.registry.append_promotion(fail)
            except Exception:
                pass
            return fail
