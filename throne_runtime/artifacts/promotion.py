"""PromotionGate with recoverable filesystem/registry transaction.

Sequence:
1. Snapshot mutable fields
2. Verify source blob
3. Create destination (no overwrite of unrelated content)
4. Verify destination
5. Update registry metadata (old path still present)
6. Append audit
7. Only then remove old-tier path

Failure before step 7 restores metadata and removes dest; original path kept.
"""

from __future__ import annotations

import threading
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
from .verifiers import (
    CAPABILITY_FOR_TARGET,
    VerificationExecutionRecord,
    VerifierCapability,
    VerifierRegistry,
)


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
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _artifact_lock(self, artifact_id: str) -> threading.Lock:
        with self._locks_guard:
            if artifact_id not in self._locks:
                self._locks[artifact_id] = threading.Lock()
            return self._locks[artifact_id]

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
        proof_target: str = "",
        _fail_at: str | None = None,
    ) -> PromotionRecord:
        lock = self._artifact_lock(artifact.artifact_id)
        with lock:
            return self._promote_locked(
                artifact,
                target_isolation=target_isolation,
                target_evidence=target_evidence,
                target_trust=target_trust,
                actor=actor,
                reason=reason,
                policy_rule=policy_rule,
                verifier_evidence=verifier_evidence,
                source_hashes=source_hashes,
                execution_record=execution_record,
                source_commit=source_commit,
                proof_target=proof_target,
                _fail_at=_fail_at,
            )

    def _promote_locked(
        self,
        artifact: ArtifactRecord,
        *,
        target_isolation: Isolation,
        target_evidence: EvidenceGrade | None,
        target_trust: Trust | None,
        actor: str,
        reason: str,
        policy_rule: str,
        verifier_evidence: dict[str, Any] | None,
        source_hashes: dict[str, str] | None,
        execution_record: VerificationExecutionRecord | None,
        source_commit: str,
        proof_target: str,
        _fail_at: str | None,
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

        # Capability requirements
        required_cap: VerifierCapability | None = None
        if target_isolation == Isolation.VALIDATED:
            required_cap = VerifierCapability.INTEGRITY_CHECK
        if target_isolation == Isolation.CERTIFIED_READ_ONLY or new_evidence in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            required_cap = VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION

        if decision == "ALLOWED" and required_cap is not None:
            if execution_record is None:
                decision = "REJECTED"
                reject_reason = (
                    f"{target_isolation.value} requires authenticated verifier "
                    f"execution with {required_cap.value}"
                )
            else:
                seen_hashes = self.registry.seen_verification_hashes(artifact.artifact_id)
                seen_nonces = self.registry.seen_verification_nonces(artifact.artifact_id)
                ok, msg = self.verifiers.validate_record(
                    execution_record,
                    expected_content_hash=artifact.content_hash,
                    expected_artifact_id=artifact.artifact_id,
                    expected_source_commit=source_commit or None,
                    expected_proof_target=proof_target or None,
                    required_capability=required_cap,
                    seen_record_hashes=seen_hashes,
                    seen_nonces=seen_nonces,
                )
                if not ok:
                    decision = "REJECTED"
                    reject_reason = msg
                elif execution_record.result == "UNSUPPORTED":
                    decision = "REJECTED"
                    reject_reason = "unsupported verifier cannot authorize target"
                else:
                    try:
                        self.registry.persist_verification_record(
                            execution_record.as_dict()
                        )
                    except ValueError as e:
                        decision = "REJECTED"
                        reject_reason = str(e)
                    else:
                        # Strip any raw secrets if present
                        safe = {
                            k: v
                            for k, v in execution_record.as_dict().items()
                            if k not in ("signing_key", "key", "key_hex")
                        }
                        verifier_evidence = {**verifier_evidence, **safe}

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

        placed_path: Path | None = None
        registry_updated = False
        audit_written = False

        try:
            if self.storage is None or self.isolation is None:
                raise PromotionError("storage/isolation not configured")

            # 1–2 source
            blob = self.storage.get_path(artifact.content_hash)
            if sha256_file(blob) != artifact.content_hash:
                raise PromotionError("source blob hash mismatch")
            if artifact.size_bytes and blob.stat().st_size != artifact.size_bytes:
                raise PromotionError("source blob size mismatch")
            if _fail_at == "source_verify":
                raise PromotionError("injected: source_verify")

            # 3 destination
            placed_path = self.isolation.place_link(
                artifact.run_id,
                target_isolation,
                artifact.original_filename,
                blob,
            )
            if _fail_at == "destination_create":
                raise PromotionError("injected: destination_create")

            # 4 dest verify
            if sha256_file(placed_path) != artifact.content_hash:
                raise PromotionError("destination content hash mismatch")
            if artifact.size_bytes and placed_path.stat().st_size != artifact.size_bytes:
                raise PromotionError("destination size mismatch")
            if _fail_at == "destination_verify":
                raise PromotionError("injected: destination_verify")

            new_location = str(placed_path)

            # 5 registry (old path still present)
            artifact.isolation = target_isolation
            artifact.evidence_grade = new_evidence
            artifact.trust = new_trust
            artifact.stored_location = new_location

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

            if _fail_at == "registry_update":
                raise PromotionError("injected: registry_update")
            self.registry.put_artifact(artifact)
            registry_updated = True

            # 6 audit BEFORE old-tier removal
            if _fail_at == "audit_append":
                raise PromotionError("injected: audit_append")
            self.registry.append_promotion(rec)
            audit_written = True

            # 7 remove old tier only after durable commit
            if old_isolation != target_isolation and old_location:
                old_path = Path(old_location)
                if old_path.exists() and old_path.is_file():
                    if old_path.resolve() != Path(new_location).resolve():
                        if _fail_at == "old_tier_removal":
                            raise PromotionError("injected: old_tier_removal")
                        try:
                            old_path.unlink()
                        except OSError as e:
                            # Not success if old exposure remains and is distinct
                            raise PromotionError(
                                f"old-tier removal failed: {e}"
                            ) from e

            return rec

        except Exception as e:
            # Rollback dest link
            if placed_path is not None and str(placed_path) != old_location:
                try:
                    if placed_path.exists():
                        if placed_path.resolve() != Path(old_location).resolve():
                            placed_path.unlink()
                except OSError:
                    pass

            # Restore metadata
            try:
                self._restore(artifact, snap)
                self.registry.put_artifact(artifact)
            except Exception as restore_err:
                # Recovery-required
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
                    policy_rule="promotion_recovery_required",
                    actor=actor,
                    reason=(
                        f"RECOVERY_REQUIRED: promote failed ({e}); "
                        f"restore failed ({restore_err}); "
                        f"snapshot_location={old_location}"
                    ),
                    decision="REJECTED",
                    timestamp=_utc_now(),
                    verifier_evidence={
                        **verifier_evidence,
                        "recovery_snapshot": {
                            "isolation": old_isolation.value,
                            "stored_location": old_location,
                        },
                    },
                    source_hashes=source_hashes,
                )
                try:
                    self.registry.append_promotion(fail)
                except Exception:
                    pass
                return fail

            # Ensure original path still exists when possible
            if old_location and not Path(old_location).exists() and self.storage:
                try:
                    blob = self.storage.get_path(artifact.content_hash)
                    # Re-place original exposure
                    if self.isolation:
                        restored = self.isolation.place_link(
                            artifact.run_id,
                            old_isolation,
                            artifact.original_filename,
                            blob,
                        )
                        artifact.stored_location = str(restored)
                        self.registry.put_artifact(artifact)
                except Exception as re_err:
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
                        policy_rule="promotion_recovery_required",
                        actor=actor,
                        reason=(
                            f"RECOVERY_REQUIRED: path restore failed ({re_err}); "
                            f"promote error ({e})"
                        ),
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

            if _fail_at == "rollback_restore":
                # Force recovery path for tests
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
                    policy_rule="promotion_recovery_required",
                    actor=actor,
                    reason="RECOVERY_REQUIRED: injected rollback_restore",
                    decision="REJECTED",
                    timestamp=_utc_now(),
                    verifier_evidence=verifier_evidence,
                    source_hashes=source_hashes,
                )
                self.registry.append_promotion(fail)
                return fail

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
                # Audit failure after successful restore still reports REJECTED
                pass
            return fail
