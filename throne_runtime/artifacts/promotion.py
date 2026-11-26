"""PromotionGate — sole mechanism for changing classification or storage tier."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .models import (
    ArtifactRecord,
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    Trust,
)
from .registry import Registry
from .router import ArtifactRouter


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class PromotionGate:
    def __init__(self, registry: Registry, router: ArtifactRouter | None = None) -> None:
        self.registry = registry
        self.router = router or ArtifactRouter()

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
    ) -> PromotionRecord:
        verifier_evidence = verifier_evidence or {}
        source_hashes = source_hashes or {}

        new_evidence = target_evidence or artifact.evidence_grade
        new_trust = target_trust or artifact.trust

        decision = "ALLOWED"
        reject_reason = ""

        # Hard gates for high-assurance tiers
        if target_isolation == Isolation.CERTIFIED_READ_ONLY or new_evidence in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            ok, msg = self.router.can_promote_to_certified(
                verifier_id=str(verifier_evidence.get("verifier_id", "")),
                verifier_version=str(verifier_evidence.get("verifier_version", "")),
                target=str(verifier_evidence.get("target", "")),
                certificate_hash=str(verifier_evidence.get("certificate_hash", "")),
                verification_result=str(verifier_evidence.get("verification_result", "")),
            )
            if not ok:
                decision = "REJECTED"
                reject_reason = msg

        # Numerical / test results cannot self-promote to formal proof
        if new_evidence in (EvidenceGrade.FORMALLY_PROVED, EvidenceGrade.CERTIFIED):
            if artifact.evidence_grade in (
                EvidenceGrade.EXPLORATORY,
                EvidenceGrade.TESTED,
                EvidenceGrade.NUMERICALLY_CROSSCHECKED,
            ) and not verifier_evidence.get("verification_result") == "PASS":
                decision = "REJECTED"
                reject_reason = (
                    "experimental or numerical evidence cannot promote to "
                    "FORMALLY_PROVED/CERTIFIED without independent verifier PASS"
                )

        # Certificate filename alone is insufficient (enforced by requiring hash + result)
        if decision == "ALLOWED" and target_isolation == Isolation.CERTIFIED_READ_ONLY:
            if not verifier_evidence.get("certificate_hash"):
                decision = "REJECTED"
                reject_reason = "certificate filename alone cannot establish certification"

        rec = PromotionRecord(
            promotion_id=f"promo-{uuid.uuid4().hex[:12]}",
            artifact_id=artifact.artifact_id,
            run_id=artifact.run_id,
            previous_isolation=artifact.isolation,
            new_isolation=target_isolation if decision == "ALLOWED" else artifact.isolation,
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
        self.registry.append_promotion(rec)

        if decision == "ALLOWED":
            artifact.isolation = target_isolation
            artifact.evidence_grade = new_evidence
            artifact.trust = new_trust
            artifact.verification_history.append(rec.as_dict())
            self.registry.put_artifact(artifact)

        return rec
