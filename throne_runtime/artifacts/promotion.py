"""PromotionGate with durable journal, process locks, exact audit reconcile."""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import sha256_file
from .journal import JournalEntry, JournalState, PromotionJournal
from .locks import ArtifactLockManager, LockTimeout
from .models import (
    ArtifactRecord,
    EvidenceGrade,
    Isolation,
    PromotionRecord,
    Trust,
)
from .registry import Registry
from .registry_ext import ensure_audit_record
from .router import ArtifactRouter
from .verifiers import (
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
        journal: PromotionJournal | None = None,
        lock_manager: ArtifactLockManager | None = None,
        lock_timeout_s: float = 30.0,
    ) -> None:
        self.registry = registry
        self.router = router or ArtifactRouter()
        self.isolation = isolation_manager
        self.storage = storage
        self.verifiers = verifier_registry or VerifierRegistry()
        self.journal = journal or PromotionJournal(
            registry.db_path, lock=registry._lock
        )
        self.locks = lock_manager or ArtifactLockManager(
            registry.db_path, lock=registry._lock
        )
        self.lock_timeout_s = lock_timeout_s
        self._thread_locks: dict[str, threading.Lock] = {}
        self._thread_guard = threading.Lock()

    def _thread_lock(self, artifact_id: str) -> threading.Lock:
        with self._thread_guard:
            if artifact_id not in self._thread_locks:
                self._thread_locks[artifact_id] = threading.Lock()
            return self._thread_locks[artifact_id]

    def _snapshot(self, artifact: ArtifactRecord) -> dict[str, Any]:
        return {
            "isolation": artifact.isolation.value,
            "evidence_grade": artifact.evidence_grade.value,
            "trust": artifact.trust.value,
            "stored_location": artifact.stored_location,
            "verification_history": deepcopy(artifact.verification_history),
            "content_hash": artifact.content_hash,
            "size_bytes": artifact.size_bytes,
            "original_filename": artifact.original_filename,
            "run_id": artifact.run_id,
        }

    def _restore_from_snapshot(
        self, artifact: ArtifactRecord, snap: dict[str, Any]
    ) -> None:
        artifact.isolation = Isolation(snap["isolation"])
        artifact.evidence_grade = EvidenceGrade(snap["evidence_grade"])
        artifact.trust = Trust(snap["trust"])
        artifact.stored_location = snap["stored_location"]
        artifact.verification_history = deepcopy(snap["verification_history"])

    def recover_incomplete(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for entry in self.journal.list_incomplete():
            results.append(self._recover_one(entry))
        return results

    def retry_recovery(self, promotion_id: str) -> dict[str, Any]:
        """Operator-directed recovery retry for a specific journal entry."""
        entry = self.journal.get(promotion_id)
        if entry is None:
            return {"promotion_id": promotion_id, "action": "missing"}
        return self._recover_one(entry)

    def _recover_one(self, entry: JournalEntry) -> dict[str, Any]:
        tlock = self._thread_lock(entry.artifact_id)
        with tlock:
            try:
                lease = self.locks.acquire(
                    entry.artifact_id, timeout_s=self.lock_timeout_s
                )
            except LockTimeout as e:
                return {
                    "promotion_id": entry.promotion_id,
                    "action": "lock_timeout",
                    "detail": str(e),
                }
            try:
                return self._recover_one_locked(entry)
            finally:
                self.locks.release(lease)

    def _recover_one_locked(self, entry: JournalEntry) -> dict[str, Any]:
        current = self.journal.get(entry.promotion_id)
        if current is None:
            return {"promotion_id": entry.promotion_id, "action": "missing"}
        # COMPLETED / ROLLED_BACK are terminal; RECOVERY_REQUIRED is retryable
        if current.state in (JournalState.COMPLETED, JournalState.ROLLED_BACK):
            return {"promotion_id": entry.promotion_id, "action": "already_terminal"}

        if current.state == JournalState.RECOVERY_REQUIRED:
            current.retry_count = int(current.retry_count or 0) + 1
            # Re-enter pipeline based on durable evidence, not the label alone
            # Prefer forward if dest+registry look good; else keep RECOVERY_REQUIRED

        art = self.registry.get_artifact(entry.artifact_id)
        snap = json.loads(entry.snapshot_json)

        try:
            if current.state == JournalState.PREPARED:
                current.state = JournalState.ROLLED_BACK
                current.detail = "recovered: prepared only"
                self.journal.put(current)
                return {"promotion_id": entry.promotion_id, "action": "rolled_back_prepared"}

            dest_ok = False
            if current.new_location:
                dest = Path(current.new_location)
                if dest.is_file() and not dest.is_symlink():
                    if sha256_file(dest) == current.content_hash:
                        if (
                            not current.size_bytes
                            or dest.stat().st_size == current.size_bytes
                        ):
                            dest_ok = True

            # From RECOVERY_REQUIRED: decide branch by verified state
            if current.state == JournalState.RECOVERY_REQUIRED:
                if dest_ok and art and art.stored_location == current.new_location:
                    current.state = JournalState.REGISTRY_UPDATED
                    self.journal.put(current)
                elif dest_ok:
                    current.state = JournalState.DESTINATION_VERIFIED
                    self.journal.put(current)
                else:
                    current.detail = (
                        f"retry {current.retry_count}: dest not verified; "
                        f"manual intervention may be required"
                    )
                    self.journal.put(current)
                    return {
                        "promotion_id": entry.promotion_id,
                        "action": "recovery_required",
                        "detail": current.detail,
                    }

            current = self.journal.get(entry.promotion_id) or current

            if current.state in (
                JournalState.DESTINATION_CREATED,
                JournalState.DESTINATION_VERIFIED,
            ):
                if not dest_ok:
                    if current.new_location:
                        p = Path(current.new_location)
                        if p.exists() and p.resolve() != Path(current.old_location).resolve():
                            try:
                                p.unlink()
                            except OSError:
                                pass
                    if art:
                        self._restore_from_snapshot(art, snap)
                        self.registry.put_artifact(art)
                    current.state = JournalState.ROLLED_BACK
                    current.detail = "recovered: dest missing/corrupt"
                    self.journal.put(current)
                    return {
                        "promotion_id": entry.promotion_id,
                        "action": "rolled_back_bad_dest",
                    }
                if art:
                    art.isolation = Isolation(current.new_isolation)
                    art.stored_location = current.new_location
                    self.registry.put_artifact(art)
                current.state = JournalState.REGISTRY_UPDATED
                self.journal.put(current)

            current = self.journal.get(entry.promotion_id) or current

            if current.state == JournalState.REGISTRY_UPDATED:
                promo = PromotionRecord(
                    promotion_id=current.promotion_id,
                    artifact_id=current.artifact_id,
                    run_id=current.run_id,
                    previous_isolation=Isolation(current.old_isolation),
                    new_isolation=Isolation(current.new_isolation),
                    previous_evidence=EvidenceGrade(snap["evidence_grade"]),
                    new_evidence=EvidenceGrade(
                        art.evidence_grade.value if art else snap["evidence_grade"]
                    ),
                    previous_trust=Trust(snap["trust"]),
                    new_trust=Trust(art.trust.value if art else snap["trust"]),
                    policy_rule="recovery",
                    actor=current.actor,
                    reason=current.reason or "recovery",
                    decision="ALLOWED",
                    timestamp=_utc_now(),
                )
                try:
                    status = ensure_audit_record(self.registry, promo)
                except ValueError as e:
                    current.state = JournalState.RECOVERY_REQUIRED
                    current.detail = f"audit conflict: {e}"
                    self.journal.put(current)
                    return {
                        "promotion_id": entry.promotion_id,
                        "action": "recovery_required",
                        "detail": current.detail,
                    }
                except Exception as e:
                    # Real DB failure — do not advance
                    current.state = JournalState.RECOVERY_REQUIRED
                    current.detail = f"audit write failed: {e}"
                    self.journal.put(current)
                    return {
                        "promotion_id": entry.promotion_id,
                        "action": "recovery_required",
                        "detail": current.detail,
                    }
                current.state = JournalState.AUDIT_COMMITTED
                current.detail = f"audit {status}"
                self.journal.put(current)

            current = self.journal.get(entry.promotion_id) or current

            if current.state == JournalState.AUDIT_COMMITTED:
                if current.old_location and current.new_location:
                    old_p = Path(current.old_location)
                    new_p = Path(current.new_location)
                    if old_p.exists() and old_p.resolve() != new_p.resolve():
                        try:
                            old_p.unlink()
                        except OSError as e:
                            current.state = JournalState.RECOVERY_REQUIRED
                            current.detail = f"old-tier removal failed: {e}"
                            self.journal.put(current)
                            return {
                                "promotion_id": entry.promotion_id,
                                "action": "recovery_required",
                                "detail": current.detail,
                            }
                current.state = JournalState.OLD_LOCATION_REMOVED
                self.journal.put(current)

            current = self.journal.get(entry.promotion_id) or current

            if current.state == JournalState.OLD_LOCATION_REMOVED:
                if current.old_location and current.new_location:
                    old_p = Path(current.old_location)
                    new_p = Path(current.new_location)
                    if old_p.exists() and old_p.resolve() != new_p.resolve():
                        current.state = JournalState.RECOVERY_REQUIRED
                        current.detail = "old-tier still exposed after removal"
                        self.journal.put(current)
                        return {
                            "promotion_id": entry.promotion_id,
                            "action": "recovery_required",
                            "detail": current.detail,
                        }
                    if not new_p.is_file() or sha256_file(new_p) != current.content_hash:
                        current.state = JournalState.RECOVERY_REQUIRED
                        current.detail = "new destination missing or corrupt"
                        self.journal.put(current)
                        return {
                            "promotion_id": entry.promotion_id,
                            "action": "recovery_required",
                            "detail": current.detail,
                        }
                current.state = JournalState.COMPLETED
                current.detail = "recovered to completed"
                self.journal.put(current)
                return {"promotion_id": entry.promotion_id, "action": "completed"}

            return {
                "promotion_id": entry.promotion_id,
                "action": f"state_{current.state.value}",
            }
        except Exception as e:
            current = self.journal.get(entry.promotion_id) or current
            current.state = JournalState.RECOVERY_REQUIRED
            current.detail = f"recovery exception: {e}"
            current.retry_count = int(current.retry_count or 0) + 1
            self.journal.put(current)
            return {
                "promotion_id": entry.promotion_id,
                "action": "recovery_required",
                "detail": str(e),
            }

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
        tlock = self._thread_lock(artifact.artifact_id)
        with tlock:
            lease = self.locks.acquire(
                artifact.artifact_id, timeout_s=self.lock_timeout_s
            )
            try:
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
            finally:
                self.locks.release(lease)

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
                        safe = {
                            k: v
                            for k, v in execution_record.as_dict().items()
                            if k not in ("signing_key", "key", "key_hex")
                        }
                        verifier_evidence = {**verifier_evidence, **safe}

        snap = self._snapshot(artifact)
        old_isolation = artifact.isolation
        old_location = artifact.stored_location
        promotion_id = f"promo-{uuid.uuid4().hex[:12]}"

        if decision != "ALLOWED":
            rec = PromotionRecord(
                promotion_id=promotion_id,
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

        journal = JournalEntry(
            promotion_id=promotion_id,
            artifact_id=artifact.artifact_id,
            run_id=artifact.run_id,
            state=JournalState.PREPARED,
            old_isolation=old_isolation.value,
            new_isolation=target_isolation.value,
            old_location=old_location,
            new_location="",
            content_hash=artifact.content_hash,
            size_bytes=artifact.size_bytes,
            original_filename=artifact.original_filename,
            actor=actor,
            reason=reason,
            snapshot_json=json.dumps(snap),
            updated_at=_utc_now(),
        )
        self.journal.put(journal)
        if _fail_at == "prepared":
            raise PromotionError("injected: prepared")

        placed_path: Path | None = None

        try:
            if self.storage is None or self.isolation is None:
                raise PromotionError("storage/isolation not configured")

            blob = self.storage.get_path(artifact.content_hash)
            if sha256_file(blob) != artifact.content_hash:
                raise PromotionError("source blob hash mismatch")
            if artifact.size_bytes and blob.stat().st_size != artifact.size_bytes:
                raise PromotionError("source blob size mismatch")
            if _fail_at == "source_verify":
                raise PromotionError("injected: source_verify")

            placed_path = self.isolation.place_link(
                artifact.run_id,
                target_isolation,
                artifact.original_filename,
                blob,
            )
            journal.state = JournalState.DESTINATION_CREATED
            journal.new_location = str(placed_path)
            self.journal.put(journal)
            if _fail_at == "destination_create":
                raise PromotionError("injected: destination_create")

            if sha256_file(placed_path) != artifact.content_hash:
                raise PromotionError("destination content hash mismatch")
            if artifact.size_bytes and placed_path.stat().st_size != artifact.size_bytes:
                raise PromotionError("destination size mismatch")
            journal.state = JournalState.DESTINATION_VERIFIED
            self.journal.put(journal)
            if _fail_at == "destination_verify":
                raise PromotionError("injected: destination_verify")

            new_location = str(placed_path)
            artifact.isolation = target_isolation
            artifact.evidence_grade = new_evidence
            artifact.trust = new_trust
            artifact.stored_location = new_location

            rec = PromotionRecord(
                promotion_id=promotion_id,
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                previous_isolation=old_isolation,
                new_isolation=target_isolation,
                previous_evidence=EvidenceGrade(snap["evidence_grade"]),
                new_evidence=new_evidence,
                previous_trust=Trust(snap["trust"]),
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
            journal.state = JournalState.REGISTRY_UPDATED
            self.journal.put(journal)

            if _fail_at == "audit_append":
                raise PromotionError("injected: audit_append")
            ensure_audit_record(self.registry, rec)
            journal.state = JournalState.AUDIT_COMMITTED
            self.journal.put(journal)

            if old_isolation != target_isolation and old_location:
                old_path = Path(old_location)
                if old_path.exists() and old_path.is_file():
                    if old_path.resolve() != Path(new_location).resolve():
                        if _fail_at == "old_tier_removal":
                            raise PromotionError("injected: old_tier_removal")
                        try:
                            old_path.unlink()
                        except OSError as e:
                            journal.state = JournalState.RECOVERY_REQUIRED
                            journal.detail = f"old-tier removal failed: {e}"
                            self.journal.put(journal)
                            raise PromotionError(journal.detail) from e
                if old_path.exists() and old_path.resolve() != Path(new_location).resolve():
                    journal.state = JournalState.RECOVERY_REQUIRED
                    journal.detail = "old-tier path still accessible"
                    self.journal.put(journal)
                    raise PromotionError(journal.detail)

            journal.state = JournalState.OLD_LOCATION_REMOVED
            self.journal.put(journal)

            if _fail_at == "before_completed":
                raise PromotionError("injected: before_completed")

            journal.state = JournalState.COMPLETED
            self.journal.put(journal)
            return rec

        except Exception as e:
            j = self.journal.get(promotion_id)
            if j and j.state in (
                JournalState.AUDIT_COMMITTED,
                JournalState.OLD_LOCATION_REMOVED,
                JournalState.COMPLETED,
            ):
                if j.state != JournalState.COMPLETED:
                    j.state = JournalState.RECOVERY_REQUIRED
                    j.detail = str(e)
                    self.journal.put(j)
                return PromotionRecord(
                    promotion_id=promotion_id,
                    artifact_id=artifact.artifact_id,
                    run_id=artifact.run_id,
                    previous_isolation=old_isolation,
                    new_isolation=old_isolation,
                    previous_evidence=EvidenceGrade(snap["evidence_grade"]),
                    new_evidence=EvidenceGrade(snap["evidence_grade"]),
                    previous_trust=Trust(snap["trust"]),
                    new_trust=Trust(snap["trust"]),
                    policy_rule="promotion_recovery_required",
                    actor=actor,
                    reason=f"RECOVERY_REQUIRED: {e}",
                    decision="REJECTED",
                    timestamp=_utc_now(),
                    verifier_evidence=verifier_evidence,
                    source_hashes=source_hashes,
                )

            if placed_path is not None and str(placed_path) != old_location:
                try:
                    if placed_path.exists() and placed_path.resolve() != Path(
                        old_location
                    ).resolve():
                        placed_path.unlink()
                except OSError:
                    pass

            try:
                self._restore_from_snapshot(artifact, snap)
                self.registry.put_artifact(artifact)
            except Exception as restore_err:
                if j:
                    j.state = JournalState.RECOVERY_REQUIRED
                    j.detail = f"promote={e}; restore={restore_err}"
                    self.journal.put(j)
                return PromotionRecord(
                    promotion_id=promotion_id,
                    artifact_id=artifact.artifact_id,
                    run_id=artifact.run_id,
                    previous_isolation=old_isolation,
                    new_isolation=old_isolation,
                    previous_evidence=EvidenceGrade(snap["evidence_grade"]),
                    new_evidence=EvidenceGrade(snap["evidence_grade"]),
                    previous_trust=Trust(snap["trust"]),
                    new_trust=Trust(snap["trust"]),
                    policy_rule="promotion_recovery_required",
                    actor=actor,
                    reason=f"RECOVERY_REQUIRED: {e}; restore={restore_err}",
                    decision="REJECTED",
                    timestamp=_utc_now(),
                    verifier_evidence=verifier_evidence,
                    source_hashes=source_hashes,
                )

            if old_location and not Path(old_location).exists() and self.storage:
                try:
                    blob = self.storage.get_path(artifact.content_hash)
                    if self.isolation:
                        restored = self.isolation.place_link(
                            artifact.run_id,
                            old_isolation,
                            artifact.original_filename,
                            blob,
                        )
                        artifact.stored_location = str(restored)
                        self.registry.put_artifact(artifact)
                except Exception:
                    pass

            if j:
                j.state = JournalState.ROLLED_BACK
                j.detail = str(e)
                self.journal.put(j)

            fail = PromotionRecord(
                promotion_id=promotion_id,
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                previous_isolation=old_isolation,
                new_isolation=old_isolation,
                previous_evidence=EvidenceGrade(snap["evidence_grade"]),
                new_evidence=EvidenceGrade(snap["evidence_grade"]),
                previous_trust=Trust(snap["trust"]),
                new_trust=Trust(snap["trust"]),
                policy_rule="promotion_rollback",
                actor=actor,
                reason=f"ROLLBACK: {e}; requested: {reason}",
                decision="REJECTED",
                timestamp=_utc_now(),
                verifier_evidence=verifier_evidence,
                source_hashes=source_hashes,
            )
            try:
                ensure_audit_record(self.registry, fail)
            except Exception:
                pass
            return fail
