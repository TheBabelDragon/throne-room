"""Independent classification dimensions and core data models.

Trust, evidence grade, isolation, and sensitivity are independent axes.
An artifact may be numerically cross-checked while remaining untrusted
and sandboxed. A formally proved artifact does not automatically become
a certified implementation. A successful experiment never becomes a proof.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Trust(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    TRUSTED = "TRUSTED"


class EvidenceGrade(str, Enum):
    EXPLORATORY = "EXPLORATORY"
    TESTED = "TESTED"
    NUMERICALLY_CROSSCHECKED = "NUMERICALLY_CROSSCHECKED"
    FORMALLY_PROVED = "FORMALLY_PROVED"
    CERTIFIED = "CERTIFIED"


class Isolation(str, Enum):
    QUARANTINED = "QUARANTINED"
    SANDBOXED = "SANDBOXED"
    VALIDATED = "VALIDATED"
    CERTIFIED_READ_ONLY = "CERTIFIED_READ_ONLY"
    REJECTED = "REJECTED"


class Sensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    RESTRICTED = "RESTRICTED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


MANIFEST_SCHEMA = "throne.runtime.artifact-manifest"
MANIFEST_VERSION = 1


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a content-addressed artifact within a run."""

    artifact_id: str
    content_hash: str
    filename: str
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    role: str = "output"  # input | output | log | certificate | other

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArtifactRef":
        return cls(
            artifact_id=str(d["artifact_id"]),
            content_hash=str(d["content_hash"]),
            filename=str(d["filename"]),
            media_type=str(d.get("media_type", "application/octet-stream")),
            size_bytes=int(d.get("size_bytes", 0)),
            role=str(d.get("role", "output")),
        )


@dataclass
class CheckResult:
    """Record of a verification or validation check."""

    name: str
    status: str  # PASS | FAIL | SKIP | ERROR
    detail: str = ""
    verifier_id: str = ""
    verifier_version: str = ""
    target: str = ""
    certificate_hash: str = ""
    timestamp: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CheckResult":
        return cls(
            name=str(d["name"]),
            status=str(d["status"]),
            detail=str(d.get("detail", "")),
            verifier_id=str(d.get("verifier_id", "")),
            verifier_version=str(d.get("verifier_version", "")),
            target=str(d.get("target", "")),
            certificate_hash=str(d.get("certificate_hash", "")),
            timestamp=str(d.get("timestamp", "")),
        )


@dataclass
class RunManifest:
    """Versioned, strictly validated run manifest.

    Classifications are independent. No artifact may assign itself a higher
    trust or evidence grade through its own manifest; promotion is external.
    """

    schema: str = MANIFEST_SCHEMA
    version: int = MANIFEST_VERSION
    run_id: str = ""
    project: str = ""
    subsystem: str = ""
    run_type: str = ""
    created_at: str = ""
    source_commit: str = ""
    parent_run: str | None = None
    trust: Trust = Trust.UNTRUSTED
    evidence_grade: EvidenceGrade = EvidenceGrade.EXPLORATORY
    isolation: Isolation = Isolation.QUARANTINED
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    inputs: list[ArtifactRef] = field(default_factory=list)
    outputs: list[ArtifactRef] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    manifest_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "run_id": self.run_id,
            "project": self.project,
            "subsystem": self.subsystem,
            "run_type": self.run_type,
            "created_at": self.created_at,
            "source_commit": self.source_commit,
            "parent_run": self.parent_run,
            "trust": self.trust.value if isinstance(self.trust, Trust) else self.trust,
            "evidence_grade": self.evidence_grade.value
            if isinstance(self.evidence_grade, EvidenceGrade)
            else self.evidence_grade,
            "isolation": self.isolation.value
            if isinstance(self.isolation, Isolation)
            else self.isolation,
            "sensitivity": self.sensitivity.value
            if isinstance(self.sensitivity, Sensitivity)
            else self.sensitivity,
            "inputs": [r.as_dict() for r in self.inputs],
            "outputs": [r.as_dict() for r in self.outputs],
            "checks": [c.as_dict() for c in self.checks],
            "provenance": dict(self.provenance),
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunManifest":
        required = (
            "schema",
            "version",
            "run_id",
            "project",
            "subsystem",
            "run_type",
            "created_at",
        )
        missing = [k for k in required if k not in d]
        if missing:
            raise ValueError(f"manifest missing required fields: {missing}")
        if d.get("schema") != MANIFEST_SCHEMA:
            raise ValueError(f"unknown manifest schema: {d.get('schema')!r}")
        if int(d.get("version", 0)) != MANIFEST_VERSION:
            raise ValueError(f"unsupported manifest version: {d.get('version')}")

        def _enum(enum_cls: type[Enum], key: str, default: Enum) -> Enum:
            raw = d.get(key, default.value)
            try:
                return enum_cls(raw)
            except ValueError as e:
                raise ValueError(f"invalid {key}: {raw!r}") from e

        return cls(
            schema=str(d["schema"]),
            version=int(d["version"]),
            run_id=str(d["run_id"]),
            project=str(d["project"]),
            subsystem=str(d["subsystem"]),
            run_type=str(d["run_type"]),
            created_at=str(d["created_at"]),
            source_commit=str(d.get("source_commit", "")),
            parent_run=d.get("parent_run"),
            trust=_enum(Trust, "trust", Trust.UNTRUSTED),  # type: ignore[arg-type]
            evidence_grade=_enum(EvidenceGrade, "evidence_grade", EvidenceGrade.EXPLORATORY),  # type: ignore[arg-type]
            isolation=_enum(Isolation, "isolation", Isolation.QUARANTINED),  # type: ignore[arg-type]
            sensitivity=_enum(Sensitivity, "sensitivity", Sensitivity.INTERNAL),  # type: ignore[arg-type]
            inputs=[ArtifactRef.from_dict(x) for x in d.get("inputs", [])],
            outputs=[ArtifactRef.from_dict(x) for x in d.get("outputs", [])],
            checks=[CheckResult.from_dict(x) for x in d.get("checks", [])],
            provenance=dict(d.get("provenance") or {}),
            status=_enum(RunStatus, "status", RunStatus.PENDING),  # type: ignore[arg-type]
            manifest_hash=str(d.get("manifest_hash", "")),
        )


@dataclass
class ArtifactRecord:
    """Registry record for a single stored artifact."""

    artifact_id: str
    run_id: str
    content_hash: str
    original_filename: str
    stored_location: str
    media_type: str
    size_bytes: int
    source_subsystem: str
    parent_run: str | None
    trust: Trust
    evidence_grade: EvidenceGrade
    isolation: Isolation
    sensitivity: Sensitivity
    created_at: str
    verification_history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "content_hash": self.content_hash,
            "original_filename": self.original_filename,
            "stored_location": self.stored_location,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "source_subsystem": self.source_subsystem,
            "parent_run": self.parent_run,
            "trust": self.trust.value,
            "evidence_grade": self.evidence_grade.value,
            "isolation": self.isolation.value,
            "sensitivity": self.sensitivity.value,
            "created_at": self.created_at,
            "verification_history": list(self.verification_history),
        }


@dataclass
class PromotionRecord:
    """Append-only promotion audit entry."""

    promotion_id: str
    artifact_id: str
    run_id: str
    previous_isolation: Isolation
    new_isolation: Isolation
    previous_evidence: EvidenceGrade
    new_evidence: EvidenceGrade
    previous_trust: Trust
    new_trust: Trust
    policy_rule: str
    actor: str
    reason: str
    decision: str  # ALLOWED | REJECTED
    timestamp: str
    verifier_evidence: dict[str, Any] = field(default_factory=dict)
    source_hashes: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "promotion_id": self.promotion_id,
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "previous_isolation": self.previous_isolation.value,
            "new_isolation": self.new_isolation.value,
            "previous_evidence": self.previous_evidence.value,
            "new_evidence": self.new_evidence.value,
            "previous_trust": self.previous_trust.value,
            "new_trust": self.new_trust.value,
            "policy_rule": self.policy_rule,
            "actor": self.actor,
            "reason": self.reason,
            "decision": self.decision,
            "timestamp": self.timestamp,
            "verifier_evidence": dict(self.verifier_evidence),
            "source_hashes": dict(self.source_hashes),
        }
