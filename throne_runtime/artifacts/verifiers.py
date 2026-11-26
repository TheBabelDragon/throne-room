"""Verifier adapter contract.

A caller cannot establish certification by passing verification_result=PASS.
The verifier must actually execute (or invoke) an independently trusted process.
Results are bound to exact artifact SHA-256, source commit, proof target,
verifier identity, and verifier version. Replayed or mismatched records
are rejected.

Unsupported verifier types remain unverified.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .hashing import sha256_bytes, sha256_file, sha256_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class VerificationRequest:
    """Inputs that must be bound into the execution record."""

    artifact_id: str
    content_hash: str
    source_commit: str
    proof_target: str
    certificate_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationExecutionRecord:
    """Immutable record of a verifier execution.

    Binding fields (artifact hash, source commit, target, verifier id/version)
    are hashed into record_hash so replay of a foreign PASS is detectable.
    """

    record_id: str
    verifier_id: str
    verifier_version: str
    artifact_id: str
    content_hash: str
    source_commit: str
    proof_target: str
    result: str  # PASS | FAIL | ERROR | UNSUPPORTED
    detail: str
    executed_at: str
    certificate_hash: str = ""
    record_hash: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def compute_record_hash(self) -> str:
        payload = {
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "artifact_id": self.artifact_id,
            "content_hash": self.content_hash,
            "source_commit": self.source_commit,
            "proof_target": self.proof_target,
            "result": self.result,
            "certificate_hash": self.certificate_hash,
            "executed_at": self.executed_at,
        }
        return sha256_json(payload)

    def seal(self) -> "VerificationExecutionRecord":
        self.record_hash = self.compute_record_hash()
        return self

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VerificationExecutionRecord":
        return cls(
            record_id=str(d["record_id"]),
            verifier_id=str(d["verifier_id"]),
            verifier_version=str(d["verifier_version"]),
            artifact_id=str(d["artifact_id"]),
            content_hash=str(d["content_hash"]),
            source_commit=str(d.get("source_commit", "")),
            proof_target=str(d.get("proof_target", "")),
            result=str(d["result"]),
            detail=str(d.get("detail", "")),
            executed_at=str(d["executed_at"]),
            certificate_hash=str(d.get("certificate_hash", "")),
            record_hash=str(d.get("record_hash", "")),
            raw=dict(d.get("raw") or {}),
        )


class VerifierAdapter(ABC):
    """Extensible verifier interface (Lean, Python tests, future checkers)."""

    verifier_id: str
    verifier_version: str

    @abstractmethod
    def execute(self, request: VerificationRequest) -> VerificationExecutionRecord:
        """Run the actual verification process and return a sealed record."""
        ...

    def supports(self, request: VerificationRequest) -> bool:
        return True


class UnsupportedVerifier(VerifierAdapter):
    """Placeholder that always returns UNSUPPORTED."""

    def __init__(self, verifier_id: str = "unsupported", version: str = "0") -> None:
        self.verifier_id = verifier_id
        self.verifier_version = version

    def execute(self, request: VerificationRequest) -> VerificationExecutionRecord:
        rec = VerificationExecutionRecord(
            record_id=f"ver-{uuid.uuid4().hex[:12]}",
            verifier_id=self.verifier_id,
            verifier_version=self.verifier_version,
            artifact_id=request.artifact_id,
            content_hash=request.content_hash,
            source_commit=request.source_commit,
            proof_target=request.proof_target,
            result="UNSUPPORTED",
            detail=f"verifier type {self.verifier_id!r} is not configured",
            executed_at=_utc_now(),
        )
        return rec.seal()


class HashBoundSelfCheckVerifier(VerifierAdapter):
    """Test/dev verifier: confirms blob exists and matches content_hash.

    Does NOT grant formal proof. Suitable only for VALIDATED-tier gates
    and regression tests that need a real execution path.
    """

    def __init__(self, blob_resolver: Any, version: str = "1.0") -> None:
        self.verifier_id = "hash_bound_self_check"
        self.verifier_version = version
        self._resolve = blob_resolver

    def execute(self, request: VerificationRequest) -> VerificationExecutionRecord:
        detail = ""
        result = "FAIL"
        cert_hash = ""
        try:
            path: Path = self._resolve(request.content_hash)
            actual = sha256_file(path)
            if actual != request.content_hash:
                detail = f"hash mismatch: expected {request.content_hash[:16]} got {actual[:16]}"
                result = "FAIL"
            else:
                size = path.stat().st_size
                detail = f"blob integrity ok size={size}"
                result = "PASS"
                if request.certificate_path and request.certificate_path.is_file():
                    cert_hash = sha256_file(request.certificate_path)
        except FileNotFoundError:
            detail = "blob not found"
            result = "FAIL"
        except Exception as e:
            detail = f"error: {e}"
            result = "ERROR"

        rec = VerificationExecutionRecord(
            record_id=f"ver-{uuid.uuid4().hex[:12]}",
            verifier_id=self.verifier_id,
            verifier_version=self.verifier_version,
            artifact_id=request.artifact_id,
            content_hash=request.content_hash,
            source_commit=request.source_commit,
            proof_target=request.proof_target,
            result=result,
            detail=detail,
            executed_at=_utc_now(),
            certificate_hash=cert_hash,
        )
        return rec.seal()


class LeanCertificateVerifier(VerifierAdapter):
    """Future Lean checker adapter.

    v0.1 does not invoke Lean. Always returns UNSUPPORTED so formal
    certification cannot be claimed without a real process.
    """

    def __init__(self, version: str = "0.0-stub") -> None:
        self.verifier_id = "lean_certificate"
        self.verifier_version = version

    def execute(self, request: VerificationRequest) -> VerificationExecutionRecord:
        rec = VerificationExecutionRecord(
            record_id=f"ver-{uuid.uuid4().hex[:12]}",
            verifier_id=self.verifier_id,
            verifier_version=self.verifier_version,
            artifact_id=request.artifact_id,
            content_hash=request.content_hash,
            source_commit=request.source_commit,
            proof_target=request.proof_target,
            result="UNSUPPORTED",
            detail=(
                "Lean certificate verification is not wired in v0.1; "
                "formal certification requires an actual Lean process"
            ),
            executed_at=_utc_now(),
        )
        return rec.seal()


class VerifierRegistry:
    """Lookup and execute registered verifier adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, VerifierAdapter] = {}

    def register(self, adapter: VerifierAdapter) -> None:
        self._adapters[adapter.verifier_id] = adapter

    def get(self, verifier_id: str) -> VerifierAdapter | None:
        return self._adapters.get(verifier_id)

    def execute(
        self, verifier_id: str, request: VerificationRequest
    ) -> VerificationExecutionRecord:
        adapter = self._adapters.get(verifier_id)
        if adapter is None:
            return UnsupportedVerifier(verifier_id).execute(request)
        return adapter.execute(request)

    def validate_record(
        self,
        record: VerificationExecutionRecord,
        *,
        expected_content_hash: str,
        expected_artifact_id: str,
        expected_source_commit: str | None = None,
        seen_record_hashes: set[str] | None = None,
    ) -> tuple[bool, str]:
        """Reject forged, mismatched, or replayed records."""
        if record.result != "PASS":
            return False, f"verification result is {record.result}, not PASS"
        if record.content_hash != expected_content_hash:
            return False, "verification record bound to wrong artifact hash"
        if record.artifact_id != expected_artifact_id:
            return False, "verification record bound to wrong artifact_id"
        if expected_source_commit is not None and record.source_commit != expected_source_commit:
            return False, "verification record source_commit mismatch"
        expected_hash = record.compute_record_hash()
        if not record.record_hash or record.record_hash != expected_hash:
            return False, "verification record_hash mismatch or missing (possible forgery)"
        if seen_record_hashes is not None and record.record_hash in seen_record_hashes:
            return False, "replayed verification record rejected"
        return True, "ok"
