"""Policy-driven routing.

Callers cannot bypass policy by requesting a destination directory.
Promotion to CERTIFIED requires recorded verifier evidence; a certificate
filename alone is insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import EvidenceGrade, Isolation, RunManifest


@dataclass
class RouteDecision:
    isolation: Isolation
    rule: str
    reason: str


_DEST_MAP = {
    "quarantine": Isolation.QUARANTINED,
    "sandbox": Isolation.SANDBOXED,
    "validated": Isolation.VALIDATED,
    "certified": Isolation.CERTIFIED_READ_ONLY,
    "rejected": Isolation.REJECTED,
}


class ArtifactRouter:
    """Routing table driven by loaded YAML policy when available."""

    def __init__(self, policy: Any = None) -> None:
        self.policy = policy

    def _from_policy(self, condition: str, default: RouteDecision) -> RouteDecision:
        if self.policy is None:
            return default
        dest = self.policy.destination_for(condition)
        if not dest:
            return default
        iso = _DEST_MAP.get(dest.lower())
        if iso is None:
            return default
        return RouteDecision(iso, condition, f"policy:{self.policy.source_path}:{condition}")

    def route_new_ingest(self, manifest: RunManifest | None = None) -> RouteDecision:
        if manifest is None:
            return self._from_policy(
                "unknown_source_or_invalid_manifest",
                RouteDecision(
                    Isolation.QUARANTINED,
                    "unknown_or_missing_manifest",
                    "Unknown source or invalid/missing manifest → quarantine",
                ),
            )
        return self._from_policy(
            "newly_ingested",
            RouteDecision(
                Isolation.QUARANTINED,
                "new_ingest",
                "Newly ingested artifact → quarantine",
            ),
        )

    def route_after_checks(self, manifest: RunManifest) -> RouteDecision:
        if manifest.status.value in ("FAILED",):
            return self._from_policy(
                "failed_integrity_or_policy",
                RouteDecision(
                    Isolation.REJECTED,
                    "failed_status",
                    "Failed integrity or policy checks → rejected",
                ),
            )
        if manifest.evidence_grade in (
            EvidenceGrade.EXPLORATORY,
            EvidenceGrade.TESTED,
            EvidenceGrade.NUMERICALLY_CROSSCHECKED,
        ):
            return self._from_policy(
                "experimental_run",
                RouteDecision(
                    Isolation.SANDBOXED,
                    "experimental_run",
                    "Experimental evidence → sandbox",
                ),
            )
        if manifest.evidence_grade == EvidenceGrade.FORMALLY_PROVED:
            # Never auto-promote formal claims
            return RouteDecision(
                Isolation.SANDBOXED,
                "formal_declared_pending_verification",
                "FORMALLY_PROVED declared but promotion requires verifier evidence",
            )
        return self._from_policy(
            "validated_schema_and_checks",
            RouteDecision(
                Isolation.VALIDATED,
                "validated_schema_checks",
                "Validated schema and checks → validated",
            ),
        )

    def can_promote_to_certified(
        self,
        *,
        verifier_id: str,
        verifier_version: str,
        target: str,
        certificate_hash: str,
        verification_result: str,
    ) -> tuple[bool, str]:
        # Kept for compatibility; real gate uses VerifierRegistry execution records.
        if not verifier_id or not verifier_version:
            return False, "verifier identity and version required"
        if not target:
            return False, "theorem/proof target required"
        if not certificate_hash:
            return False, "certificate hash required"
        if verification_result != "PASS":
            return False, "verification result must be PASS"
        return True, "verifier evidence complete"
