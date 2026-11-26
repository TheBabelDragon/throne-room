"""Policy-driven routing.

Callers cannot bypass policy by requesting a destination directory.
Promotion to CERTIFIED requires recorded verifier evidence; a certificate
filename alone is insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import EvidenceGrade, Isolation, RunManifest, Trust


@dataclass
class RouteDecision:
    isolation: Isolation
    rule: str
    reason: str


class ArtifactRouter:
    """Default routing table (v0.1, code-defined; YAML can override later)."""

    def route_new_ingest(self, manifest: RunManifest | None = None) -> RouteDecision:
        if manifest is None:
            return RouteDecision(
                Isolation.QUARANTINED,
                "unknown_or_missing_manifest",
                "Unknown source or invalid/missing manifest → quarantine",
            )
        # Newly ingested always starts quarantined regardless of self-declared grade.
        return RouteDecision(
            Isolation.QUARANTINED,
            "new_ingest",
            "Newly ingested artifact → quarantine",
        )

    def route_after_checks(self, manifest: RunManifest) -> RouteDecision:
        if manifest.status.value in ("FAILED",):
            return RouteDecision(
                Isolation.REJECTED,
                "failed_status",
                "Failed integrity or policy checks → rejected",
            )
        # Experimental / exploratory stays sandboxed after leaving quarantine.
        if manifest.evidence_grade in (
            EvidenceGrade.EXPLORATORY,
            EvidenceGrade.TESTED,
            EvidenceGrade.NUMERICALLY_CROSSCHECKED,
        ):
            return RouteDecision(
                Isolation.SANDBOXED,
                "experimental_run",
                "Experimental evidence → sandbox",
            )
        # Validated schema + checks but not formal.
        if manifest.evidence_grade == EvidenceGrade.FORMALLY_PROVED:
            # Still requires promotion gate with real verifier evidence.
            return RouteDecision(
                Isolation.SANDBOXED,
                "formal_declared_pending_verification",
                "FORMALLY_PROVED declared but promotion requires verifier evidence",
            )
        return RouteDecision(
            Isolation.VALIDATED,
            "validated_schema_checks",
            "Validated schema and checks → validated",
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
        if not verifier_id or not verifier_version:
            return False, "verifier identity and version required"
        if not target:
            return False, "theorem/proof target required"
        if not certificate_hash:
            return False, "certificate hash required"
        if verification_result != "PASS":
            return False, "verification result must be PASS"
        return True, "verifier evidence complete"
