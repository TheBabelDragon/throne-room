"""Authenticated verifier adapters with explicit capability authorization.

hash_bound_self_check may authorize INTEGRITY_CHECK only (VALIDATED tier).
It must never authorize FORMALLY_PROVED, CERTIFIED, or CERTIFIED_READ_ONLY.
Lean remains unavailable until a real Lean process is integrated.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .hashing import sha256_file, sha256_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class VerifierCapability(str, Enum):
    INTEGRITY_CHECK = "INTEGRITY_CHECK"
    FORMAL_CERTIFICATE_VERIFICATION = "FORMAL_CERTIFICATE_VERIFICATION"


# Promotion targets → required capability
CAPABILITY_FOR_TARGET: dict[str, VerifierCapability] = {
    "VALIDATED": VerifierCapability.INTEGRITY_CHECK,
    "CERTIFIED_READ_ONLY": VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION,
    "FORMALLY_PROVED": VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION,
    "CERTIFIED": VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION,
}


@dataclass(frozen=True)
class VerificationRequest:
    artifact_id: str
    content_hash: str
    source_commit: str
    proof_target: str
    certificate_path: Path | None = None
    required_capability: VerifierCapability | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationExecutionRecord:
    record_id: str
    verifier_id: str
    verifier_version: str
    artifact_id: str
    content_hash: str
    source_commit: str
    proof_target: str
    result: str
    detail: str
    executed_at: str
    capability: str = ""
    key_id: str = ""
    nonce: str = ""
    certificate_hash: str = ""
    signature: str = ""
    record_hash: str = ""
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
            "capability": self.capability,
            "key_id": self.key_id,
            "certificate_hash": self.certificate_hash,
            "executed_at": self.executed_at,
            "nonce": self.nonce,
        }

    def compute_record_hash(self) -> str:
        return sha256_json(self.canonical_payload())

    def sign(self, key: bytes, key_id: str = "") -> "VerificationExecutionRecord":
        if not self.nonce:
            self.nonce = secrets.token_hex(16)
        if key_id:
            self.key_id = key_id
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
        d = asdict(self)
        # Never expose raw key material
        return d

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
            capability=str(d.get("capability", "")),
            key_id=str(d.get("key_id", "")),
            nonce=str(d.get("nonce", "")),
            certificate_hash=str(d.get("certificate_hash", "")),
            signature=str(d.get("signature", "")),
            record_hash=str(d.get("record_hash", "")),
            raw=dict(d.get("raw") or {}),
        )


@dataclass
class KeyEntry:
    key_id: str
    key: bytes
    retired: bool = False


class TrustedKeyRegistry:
    """Maps verifier_id → active KeyEntry; retains retired keys for historical verify."""

    def __init__(self) -> None:
        # verifier_id -> list of KeyEntry (active first)
        self._keys: dict[str, list[KeyEntry]] = {}

    def register(
        self, verifier_id: str, key: bytes, *, key_id: str = "default", retired: bool = False
    ) -> None:
        if not key or len(key) < 16:
            raise ValueError("verifier key must be at least 16 bytes")
        entry = KeyEntry(key_id=key_id, key=key, retired=retired)
        lst = self._keys.setdefault(verifier_id, [])
        # Replace same key_id
        lst[:] = [e for e in lst if e.key_id != key_id]
        if retired:
            lst.append(entry)
        else:
            lst.insert(0, entry)

    def active_key(self, verifier_id: str) -> KeyEntry | None:
        for e in self._keys.get(verifier_id, []):
            if not e.retired:
                return e
        return None

    def find_key(self, verifier_id: str, key_id: str = "") -> KeyEntry | None:
        for e in self._keys.get(verifier_id, []):
            if key_id and e.key_id == key_id:
                return e
            if not key_id and not e.retired:
                return e
        return None

    def has_active(self, verifier_id: str) -> bool:
        return self.active_key(verifier_id) is not None

    def all_key_ids(self, verifier_id: str) -> list[str]:
        return [e.key_id for e in self._keys.get(verifier_id, [])]


def load_keys_from_file(path: Path) -> dict[str, list[tuple[str, bytes, bool]]]:
    """JSON format: {verifier_id: [{"key_id": "...", "key_hex": "...", "retired": false}]}.

    Never log or embed file contents in artifact metadata.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[tuple[str, bytes, bool]]] = {}
    if not isinstance(data, dict):
        raise ValueError("key file root must be object")
    for vid, entries in data.items():
        if not isinstance(entries, list):
            raise ValueError(f"keys for {vid} must be a list")
        parsed: list[tuple[str, bytes, bool]] = []
        for e in entries:
            kid = str(e["key_id"])
            key = bytes.fromhex(str(e["key_hex"]))
            retired = bool(e.get("retired", False))
            parsed.append((kid, key, retired))
        out[str(vid)] = parsed
    return out


class VerifierAdapter(ABC):
    verifier_id: str
    verifier_version: str
    capabilities: frozenset[VerifierCapability]

    def supports_capability(self, cap: VerifierCapability) -> bool:
        return cap in self.capabilities

    @abstractmethod
    def execute(
        self,
        request: VerificationRequest,
        *,
        signing_key: bytes,
        key_id: str,
    ) -> VerificationExecutionRecord:
        ...


class UnsupportedVerifier(VerifierAdapter):
    capabilities = frozenset()

    def __init__(self, verifier_id: str = "unsupported", version: str = "0") -> None:
        self.verifier_id = verifier_id
        self.verifier_version = version

    def execute(
        self,
        request: VerificationRequest,
        *,
        signing_key: bytes,
        key_id: str,
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
            capability="",
        )
        return rec.sign(signing_key, key_id=key_id)


class HashBoundSelfCheckVerifier(VerifierAdapter):
    """Integrity only — never formal certification."""

    capabilities = frozenset({VerifierCapability.INTEGRITY_CHECK})

    def __init__(self, blob_resolver: Any, version: str = "1.0") -> None:
        self.verifier_id = "hash_bound_self_check"
        self.verifier_version = version
        self._resolve = blob_resolver

    def execute(
        self,
        request: VerificationRequest,
        *,
        signing_key: bytes,
        key_id: str,
    ) -> VerificationExecutionRecord:
        # Capability gate at execution time
        if (
            request.required_capability
            and request.required_capability not in self.capabilities
        ):
            rec = VerificationExecutionRecord(
                record_id=f"ver-{uuid.uuid4().hex[:12]}",
                verifier_id=self.verifier_id,
                verifier_version=self.verifier_version,
                artifact_id=request.artifact_id,
                content_hash=request.content_hash,
                source_commit=request.source_commit,
                proof_target=request.proof_target,
                result="FAIL",
                detail=(
                    f"capability {request.required_capability.value} not authorized "
                    f"for {self.verifier_id}"
                ),
                executed_at=_utc_now(),
                capability=request.required_capability.value,
            )
            return rec.sign(signing_key, key_id=key_id)

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
            capability=VerifierCapability.INTEGRITY_CHECK.value,
            certificate_hash=cert_hash,
        )
        return rec.sign(signing_key, key_id=key_id)


class LeanCertificateVerifier(VerifierAdapter):
    """Stub: no formal capability exercised until real Lean integration."""

    # Declared for future wiring; execute always returns UNSUPPORTED
    capabilities = frozenset({VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION})

    def __init__(self, version: str = "0.0-stub") -> None:
        self.verifier_id = "lean_certificate"
        self.verifier_version = version

    def execute(
        self,
        request: VerificationRequest,
        *,
        signing_key: bytes,
        key_id: str,
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
            capability=VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION.value,
        )
        return rec.sign(signing_key, key_id=key_id)


class VerifierRegistry:
    def __init__(self, key_registry: TrustedKeyRegistry | None = None) -> None:
        self._adapters: dict[str, VerifierAdapter] = {}
        self.keys = key_registry or TrustedKeyRegistry()

    def register(
        self,
        adapter: VerifierAdapter,
        *,
        key: bytes | None = None,
        key_id: str = "default",
    ) -> None:
        self._adapters[adapter.verifier_id] = adapter
        if key is not None:
            self.keys.register(adapter.verifier_id, key, key_id=key_id)

    def get(self, verifier_id: str) -> VerifierAdapter | None:
        return self._adapters.get(verifier_id)

    def execute(
        self, verifier_id: str, request: VerificationRequest
    ) -> VerificationExecutionRecord:
        active = self.keys.active_key(verifier_id)
        if active is None:
            raise RuntimeError(
                f"no active trusted key for verifier {verifier_id!r}; "
                "configure THRONE_VERIFIER_KEYS_PATH or inject keys"
            )
        adapter = self._adapters.get(verifier_id)
        if adapter is None:
            return UnsupportedVerifier(verifier_id).execute(
                request, signing_key=active.key, key_id=active.key_id
            )
        if (
            request.required_capability
            and not adapter.supports_capability(request.required_capability)
        ):
            rec = VerificationExecutionRecord(
                record_id=f"ver-{uuid.uuid4().hex[:12]}",
                verifier_id=adapter.verifier_id,
                verifier_version=adapter.verifier_version,
                artifact_id=request.artifact_id,
                content_hash=request.content_hash,
                source_commit=request.source_commit,
                proof_target=request.proof_target,
                result="FAIL",
                detail=(
                    f"verifier lacks capability {request.required_capability.value}"
                ),
                executed_at=_utc_now(),
                capability=request.required_capability.value,
            )
            return rec.sign(active.key, key_id=active.key_id)
        return adapter.execute(
            request, signing_key=active.key, key_id=active.key_id
        )

    def validate_record(
        self,
        record: VerificationExecutionRecord,
        *,
        expected_content_hash: str,
        expected_artifact_id: str,
        expected_source_commit: str | None = None,
        expected_proof_target: str | None = None,
        required_capability: VerifierCapability | None = None,
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
        if (
            expected_proof_target is not None
            and record.proof_target != expected_proof_target
        ):
            return False, "verification record proof_target mismatch"
        if not record.signature or not record.nonce:
            return False, "verification record unsigned or missing nonce"

        if required_capability is not None:
            if record.capability != required_capability.value:
                return (
                    False,
                    f"record capability {record.capability!r} does not satisfy "
                    f"{required_capability.value}",
                )
            adapter = self._adapters.get(record.verifier_id)
            if adapter is None:
                return False, "unknown verifier identity"
            if not adapter.supports_capability(required_capability):
                return (
                    False,
                    f"verifier {record.verifier_id} not authorized for "
                    f"{required_capability.value}",
                )

        entry = self.keys.find_key(record.verifier_id, record.key_id)
        if entry is None:
            # try any key for verifier (rotation)
            for kid in self.keys.all_key_ids(record.verifier_id):
                e = self.keys.find_key(record.verifier_id, kid)
                if e and record.verify_signature(e.key):
                    entry = e
                    break
        if entry is None:
            return False, "verifier identity/key not in trusted key registry"
        if not record.verify_signature(entry.key):
            return False, "verification record signature invalid (possible forgery)"

        if seen_nonces is not None and record.nonce in seen_nonces:
            return False, "replayed verification record rejected (nonce)"
        if seen_record_hashes is not None and record.record_hash in seen_record_hashes:
            return False, "replayed verification record rejected"

        return True, "ok"
