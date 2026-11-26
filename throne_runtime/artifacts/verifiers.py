"""Authenticated verifier adapter contract.

Execution records are HMAC-SHA256 signed by a trusted verifier key held
outside caller-controlled artifact metadata. A public SHA-256 digest alone
is not authentication — anyone can recompute it for a forged payload.

Unsupported Lean verification cannot produce formal-proof or certification.
"""

from __future__ import annotations

import hmac
import hashlib
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import sha256_file, sha256_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class VerificationRequest:
    artifact_id: str
    content_hash: str
    source_commit: str
    proof_target: str
    certificate_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationExecutionRecord:
    """Signed verification execution record.

    Binding fields are covered by HMAC signature. signature is hex HMAC-SHA256
    over the canonical payload (excluding signature itself).
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
    nonce: str = ""
    certificate_hash: str = ""
    signature: str = ""
    record_hash: str = ""  # retained for audit; not authentication
    raw: dict[str, Any] = field(default_factory=dict)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "artifact_id": self.artifact_id,
            "content_hash": self.content_hash,
            "source_commit": self.source_commit,
            "proof_target": self.proof_target,
            "result": self.result,
            "certificate_hash": self.certificate_hash,
            "executed_at": self.executed_at,
            "nonce": self.nonce,
        }

    def compute_record_hash(self) -> str:
        return sha256_json(self.canonical_payload())

    def sign(self, key: bytes) -> "VerificationExecutionRecord":
        if not self.nonce:
            self.nonce = secrets.token_hex(16)
        payload = sha256_json(self.canonical_payload()).encode("utf-8")
        self.signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
        self.record_hash = self.compute_record_hash()
        return self

    def verify_signature(self, key: bytes) -> bool:
        if not self.signature or not self.nonce:
            return False
        payload = sha256_json(self.canonical_payload()).encode("utf-8")
        expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

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
            nonce=str(d.get("nonce", "")),
            certificate_hash=str(d.get("certificate_hash", "")),
            signature=str(d.get("signature", "")),
            record_hash=str(d.get("record_hash", "")),
            raw=dict(d.get("raw") or {}),
        )


class TrustedKeyRegistry:
    """Maps verifier_id → HMAC key material (bytes).

    Keys are service-held secrets, never taken from caller artifact metadata.
    """

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def register(self, verifier_id: str, key: bytes) -> None:
        if not key or len(key) < 16:
            raise ValueError("verifier key must be at least 16 bytes")
        self._keys[verifier_id] = key

    def get(self, verifier_id: str) -> bytes | None:
        return self._keys.get(verifier_id)

    def has(self, verifier_id: str) -> bool:
        return verifier_id in self._keys


class VerifierAdapter(ABC):
    verifier_id: str
    verifier_version: str

    @abstractmethod
    def execute(
        self, request: VerificationRequest, *, signing_key: bytes
    ) -> VerificationExecutionRecord:
        ...


class UnsupportedVerifier(VerifierAdapter):
    def __init__(self, verifier_id: str = "unsupported", version: str = "0") -> None:
        self.verifier_id = verifier_id
        self.verifier_version = version

    def execute(
        self, request: VerificationRequest, *, signing_key: bytes
    ) -> VerificationExecutionRecord:
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
        return rec.sign(signing_key)


class HashBoundSelfCheckVerifier(VerifierAdapter):
    """Integrity self-check. Suitable for VALIDATED tier only, not formal proof."""

    def __init__(self, blob_resolver: Any, version: str = "1.0") -> None:
        self.verifier_id = "hash_bound_self_check"
        self.verifier_version = version
        self._resolve = blob_resolver

    def execute(
        self, request: VerificationRequest, *, signing_key: bytes
    ) -> VerificationExecutionRecord:
        detail = ""
        result = "FAIL"
        cert_hash = ""
        try:
            path: Path = self._resolve(request.content_hash)
            actual = sha256_file(path)
            if actual != request.content_hash:
                detail = (
                    f"hash mismatch: expected {request.content_hash[:16]} "
                    f"got {actual[:16]}"
                )
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
        return rec.sign(signing_key)


class LeanCertificateVerifier(VerifierAdapter):
    """Stub: does not invoke Lean; always UNSUPPORTED."""

    def __init__(self, version: str = "0.0-stub") -> None:
        self.verifier_id = "lean_certificate"
        self.verifier_version = version

    def execute(
        self, request: VerificationRequest, *, signing_key: bytes
    ) -> VerificationExecutionRecord:
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
        return rec.sign(signing_key)


class VerifierRegistry:
    def __init__(self, key_registry: TrustedKeyRegistry | None = None) -> None:
        self._adapters: dict[str, VerifierAdapter] = {}
        self.keys = key_registry or TrustedKeyRegistry()

    def register(self, adapter: VerifierAdapter, *, key: bytes | None = None) -> None:
        self._adapters[adapter.verifier_id] = adapter
        if key is not None:
            self.keys.register(adapter.verifier_id, key)

    def get(self, verifier_id: str) -> VerifierAdapter | None:
        return self._adapters.get(verifier_id)

    def execute(
        self, verifier_id: str, request: VerificationRequest
    ) -> VerificationExecutionRecord:
        key = self.keys.get(verifier_id)
        if key is None:
            # No trusted key → cannot produce authenticable PASS
            ephemeral = secrets.token_bytes(32)
            return UnsupportedVerifier(verifier_id).execute(
                request, signing_key=ephemeral
            )
        adapter = self._adapters.get(verifier_id)
        if adapter is None:
            return UnsupportedVerifier(verifier_id).execute(request, signing_key=key)
        return adapter.execute(request, signing_key=key)

    def validate_record(
        self,
        record: VerificationExecutionRecord,
        *,
        expected_content_hash: str,
        expected_artifact_id: str,
        expected_source_commit: str | None = None,
        seen_nonces: set[str] | None = None,
        seen_record_hashes: set[str] | None = None,
    ) -> tuple[bool, str]:
        if record.result != "PASS":
            return False, f"verification result is {record.result}, not PASS"
        if record.content_hash != expected_content_hash:
            return False, "verification record bound to wrong artifact hash"
        if record.artifact_id != expected_artifact_id:
            return False, "verification record bound to wrong artifact_id"
        if (
            expected_source_commit is not None
            and record.source_commit != expected_source_commit
        ):
            return False, "verification record source_commit mismatch"
        if not record.signature or not record.nonce:
            return False, "verification record unsigned or missing nonce"

        key = self.keys.get(record.verifier_id)
        if key is None:
            return False, "verifier identity not in trusted key registry"
        if not record.verify_signature(key):
            return False, "verification record signature invalid (possible forgery)"

        if seen_nonces is not None and record.nonce in seen_nonces:
            return False, "replayed verification record rejected (nonce)"
        if seen_record_hashes is not None and record.record_hash in seen_record_hashes:
            return False, "replayed verification record rejected"

        return True, "ok"
