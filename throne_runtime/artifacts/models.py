"""Independent classification dimensions and strict data models."""

from __future__ import annotations

import re
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

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)

KNOWN_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "version",
        "run_id",
        "project",
        "subsystem",
        "run_type",
        "created_at",
        "source_commit",
        "parent_run",
        "trust",
        "evidence_grade",
        "isolation",
        "sensitivity",
        "inputs",
        "outputs",
        "checks",
        "provenance",
        "status",
        "manifest_hash",
    }
)


def _require_str(d: dict[str, Any], key: str) -> str:
    if key not in d:
        raise ValueError(f"manifest missing required field: {key}")
    v = d[key]
    if not isinstance(v, str):
        raise ValueError(f"manifest field {key!r} must be str, got {type(v).__name__}")
    return v


def _require_int(d: dict[str, Any], key: str) -> int:
    if key not in d:
        raise ValueError(f"manifest missing required field: {key}")
    v = d[key]
    if type(v) is not int:  # reject bool subclassing int
        raise ValueError(f"manifest field {key!r} must be int, got {type(v).__name__}")
    return v


def _optional_str(d: dict[str, Any], key: str, default: str = "") -> str:
    if key not in d or d[key] is None:
        return default
    v = d[key]
    if not isinstance(v, str):
        raise ValueError(f"manifest field {key!r} must be str, got {type(v).__name__}")
    return v


def _validate_sha256(h: str, label: str) -> str:
    if h and not _SHA256_RE.match(h):
        raise ValueError(f"invalid SHA-256 for {label}: {h[:20]!r}...")
    return h


def _validate_timestamp(ts: str) -> str:
    if not _ISO_RE.match(ts):
        raise ValueError(f"malformed timestamp: {ts!r}")
    return ts


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    content_hash: str
    filename: str
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    role: str = "output"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArtifactRef":
        if not isinstance(d, dict):
            raise ValueError("artifact ref must be an object")
        unknown = set(d) - {
            "artifact_id",
            "content_hash",
            "filename",
            "media_type",
            "size_bytes",
            "role",
        }
        if unknown:
            raise ValueError(f"artifact ref unknown fields: {sorted(unknown)}")
        for k in ("artifact_id", "content_hash", "filename"):
            if k not in d:
                raise ValueError(f"artifact ref missing {k}")
            if not isinstance(d[k], str):
                raise ValueError(f"artifact ref {k} must be str")
        size = d.get("size_bytes", 0)
        if type(size) is not int:
            raise ValueError("artifact ref size_bytes must be int")
        media = d.get("media_type", "application/octet-stream")
        if not isinstance(media, str):
            raise ValueError("artifact ref media_type must be str")
        role = d.get("role", "output")
        if not isinstance(role, str):
            raise ValueError("artifact ref role must be str")
        return cls(
            artifact_id=d["artifact_id"],
            content_hash=_validate_sha256(d["content_hash"], "artifact_ref"),
            filename=d["filename"],
            media_type=media,
            size_bytes=size,
            role=role,
        )


@dataclass
class CheckResult:
    name: str
    status: str
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
        if not isinstance(d, dict):
            raise ValueError("check result must be an object")
        for k in ("name", "status"):
            if k not in d or not isinstance(d[k], str):
                raise ValueError(f"check result {k} must be str")
        ch = d.get("certificate_hash", "")
        if ch and not isinstance(ch, str):
            raise ValueError("certificate_hash must be str")
        if ch:
            _validate_sha256(ch, "certificate_hash")
        return cls(
            name=d["name"],
            status=d["status"],
            detail=d["detail"] if isinstance(d.get("detail", ""), str) else "",
            verifier_id=d["verifier_id"] if isinstance(d.get("verifier_id", ""), str) else "",
            verifier_version=d["verifier_version"]
            if isinstance(d.get("verifier_version", ""), str)
            else "",
            target=d["target"] if isinstance(d.get("target", ""), str) else "",
            certificate_hash=ch or "",
            timestamp=d["timestamp"] if isinstance(d.get("timestamp", ""), str) else "",
        )


@dataclass
class RunManifest:
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
        if not isinstance(d, dict):
            raise ValueError("manifest root must be an object")
        unknown = set(d) - KNOWN_MANIFEST_KEYS
        if unknown:
            raise ValueError(f"manifest unknown fields: {sorted(unknown)}")

        schema = _require_str(d, "schema")
        if schema != MANIFEST_SCHEMA:
            raise ValueError(f"unknown manifest schema: {schema!r}")
        version = _require_int(d, "version")
        if version != MANIFEST_VERSION:
            raise ValueError(f"unsupported manifest version: {version}")

        run_id = _require_str(d, "run_id")
        project = _require_str(d, "project")
        subsystem = _require_str(d, "subsystem")
        run_type = _require_str(d, "run_type")
        created_at = _validate_timestamp(_require_str(d, "created_at"))

        def _enum(enum_cls: type[Enum], key: str, default: Enum) -> Enum:
            if key not in d:
                return default
            raw = d[key]
            if not isinstance(raw, str):
                raise ValueError(f"invalid {key}: must be str")
            try:
                return enum_cls(raw)
            except ValueError as e:
                raise ValueError(f"invalid {key}: {raw!r}") from e

        parent = d.get("parent_run")
        if parent is not None and not isinstance(parent, str):
            raise ValueError("parent_run must be str or null")

        inputs_raw = d.get("inputs", [])
        outputs_raw = d.get("outputs", [])
        checks_raw = d.get("checks", [])
        if not isinstance(inputs_raw, list):
            raise ValueError("inputs must be a list")
        if not isinstance(outputs_raw, list):
            raise ValueError("outputs must be a list")
        if not isinstance(checks_raw, list):
            raise ValueError("checks must be a list")

        prov = d.get("provenance", {})
        if prov is None:
            prov = {}
        if not isinstance(prov, dict):
            raise ValueError("provenance must be an object")

        mh = _optional_str(d, "manifest_hash", "")
        if mh:
            _validate_sha256(mh, "manifest_hash")

        return cls(
            schema=schema,
            version=version,
            run_id=run_id,
            project=project,
            subsystem=subsystem,
            run_type=run_type,
            created_at=created_at,
            source_commit=_optional_str(d, "source_commit", ""),
            parent_run=parent,
            trust=_enum(Trust, "trust", Trust.UNTRUSTED),  # type: ignore[arg-type]
            evidence_grade=_enum(EvidenceGrade, "evidence_grade", EvidenceGrade.EXPLORATORY),  # type: ignore[arg-type]
            isolation=_enum(Isolation, "isolation", Isolation.QUARANTINED),  # type: ignore[arg-type]
            sensitivity=_enum(Sensitivity, "sensitivity", Sensitivity.INTERNAL),  # type: ignore[arg-type]
            inputs=[ArtifactRef.from_dict(x) for x in inputs_raw],
            outputs=[ArtifactRef.from_dict(x) for x in outputs_raw],
            checks=[CheckResult.from_dict(x) for x in checks_raw],
            provenance=dict(prov),
            status=_enum(RunStatus, "status", RunStatus.PENDING),  # type: ignore[arg-type]
            manifest_hash=mh,
        )


@dataclass
class ArtifactRecord:
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
    decision: str
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
