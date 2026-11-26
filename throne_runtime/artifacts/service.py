"""ArtifactService — primary Python interface for the runtime artifact store.

On startup, incomplete promotion journal entries are reconciled before the
service accepts new promotions.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .isolation import IsolationManager
from .manifest import attach_manifest_hash, write_manifest
from .models import (
    ArtifactRecord,
    ArtifactRef,
    CheckResult,
    EvidenceGrade,
    Isolation,
    RunManifest,
    RunStatus,
    Sensitivity,
    Trust,
)
from .paths import PathContainmentError, ensure_under, is_under, reject_symlink
from .policy import PolicyError, load_routing_policy_loose
from .promotion import PromotionGate
from .registry import Registry
from .router import ArtifactRouter
from .scanner import ArtifactScanner, ScanError, ScanLimits
from .storage import LocalBlobStorage, StorageBackend
from .verifier import ArtifactVerifier
from .verifiers import (
    HashBoundSelfCheckVerifier,
    LeanCertificateVerifier,
    TrustedKeyRegistry,
    VerificationRequest,
    VerifierCapability,
    VerifierRegistry,
    load_keys_from_file,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _new_artifact_id() -> str:
    return f"art-{uuid.uuid4().hex[:12]}"


class ArtifactService:
    """Shared runtime artifact distribution service."""

    def __init__(
        self,
        root: Path | str = Path("runtime/artifacts"),
        storage: StorageBackend | None = None,
        policy_dir: Path | str | None = None,
        scan_limits: ScanLimits | None = None,
        *,
        require_policy: bool = True,
        verifier_keys: dict[str, bytes] | None = None,
        verifier_keys_path: Path | str | None = None,
        allow_ephemeral_keys: bool = False,
        run_recovery: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.storage: StorageBackend = storage or LocalBlobStorage(self.root)
        self.isolation = IsolationManager(self.root)
        self.registry = Registry(self.root / "registry.sqlite3")
        self.scanner = ArtifactScanner(self.root, limits=scan_limits)
        self.router = ArtifactRouter()

        key_reg = TrustedKeyRegistry()
        keys_loaded = False

        path_env = verifier_keys_path or os.environ.get("THRONE_VERIFIER_KEYS_PATH")
        if path_env:
            loaded = load_keys_from_file(Path(path_env))
            for vid, entries in loaded.items():
                for kid, key, retired in entries:
                    key_reg.register(vid, key, key_id=kid, retired=retired)
            keys_loaded = True

        if verifier_keys:
            for vid, key in verifier_keys.items():
                key_reg.register(vid, key, key_id="injected")
            keys_loaded = True

        if not keys_loaded:
            if not allow_ephemeral_keys:
                raise RuntimeError(
                    "verifier keys not configured; set THRONE_VERIFIER_KEYS_PATH "
                    "or pass verifier_keys= / allow_ephemeral_keys=True for tests"
                )
            for vid in ("hash_bound_self_check", "lean_certificate"):
                key_reg.register(vid, secrets.token_bytes(32), key_id="ephemeral")

        self.verifiers = VerifierRegistry(key_registry=key_reg)
        hk = key_reg.active_key("hash_bound_self_check")
        lk = key_reg.active_key("lean_certificate")
        self.verifiers.register(
            HashBoundSelfCheckVerifier(blob_resolver=self.storage.get_path),
            key=hk.key if hk else None,
            key_id=hk.key_id if hk else "default",
        )
        self.verifiers.register(
            LeanCertificateVerifier(),
            key=lk.key if lk else None,
            key_id=lk.key_id if lk else "default",
        )
        self.promotion_gate = PromotionGate(
            self.registry,
            self.router,
            isolation_manager=self.isolation,
            storage=self.storage,
            verifier_registry=self.verifiers,
        )
        self.verifier = ArtifactVerifier()
        self._policy_dir = Path(policy_dir) if policy_dir else self._default_policy_dir()
        self.routing_policy = None
        self._require_policy = require_policy
        self._load_policies()

        self.recovery_log: list[dict[str, Any]] = []
        if run_recovery:
            self.recovery_log = self.promotion_gate.recover_incomplete()

    def _default_policy_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "policies"

    def _load_policies(self) -> None:
        path = self._policy_dir / "artifact_routing.yaml"
        try:
            self.routing_policy = load_routing_policy_loose(path)
            self.router.policy = self.routing_policy
        except PolicyError:
            if self._require_policy:
                raise
            self.routing_policy = None

    def create_run(
        self,
        *,
        project: str,
        subsystem: str,
        run_type: str,
        source_commit: str = "",
        parent_run: str | None = None,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
        trust: Trust = Trust.UNTRUSTED,
        evidence_grade: EvidenceGrade = EvidenceGrade.EXPLORATORY,
    ) -> RunManifest:
        if trust != Trust.UNTRUSTED:
            trust = Trust.UNTRUSTED
        if evidence_grade in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            evidence_grade = EvidenceGrade.EXPLORATORY

        run_id = _new_run_id()
        manifest = RunManifest(
            run_id=run_id,
            project=project,
            subsystem=subsystem,
            run_type=run_type,
            created_at=_utc_now(),
            source_commit=source_commit,
            parent_run=parent_run,
            trust=trust,
            evidence_grade=evidence_grade,
            isolation=Isolation.QUARANTINED,
            sensitivity=sensitivity,
            status=RunStatus.PENDING,
        )
        attach_manifest_hash(manifest)
        self.registry.put_run(manifest)
        run_dir = self.isolation.run_dir(run_id, Isolation.QUARANTINED)
        write_manifest(run_dir / "manifest.json", manifest)
        return manifest

    def get_run(self, run_id: str) -> RunManifest | None:
        return self.registry.get_run(run_id)

    def list_runs(self, project: str | None = None) -> list[RunManifest]:
        return self.registry.list_runs(project=project)

    def ingest(
        self,
        *,
        run_id: str,
        path: Path | str,
        role: str = "output",
        filename: str | None = None,
    ) -> ArtifactRecord:
        manifest = self.registry.get_run(run_id)
        if manifest is None:
            raise KeyError(f"unknown run_id: {run_id}")

        existing = self.registry.list_artifacts(run_id)
        total_bytes = sum(a.size_bytes for a in existing)
        if len(existing) >= self.scanner.limits.max_files:
            raise ScanError("per-run file count limit exceeded")

        path = Path(path)
        scanned = self.scanner.scan_file(path, relative_name=filename)
        if total_bytes + scanned.size_bytes > self.scanner.limits.max_total_bytes:
            raise ScanError("per-run total size limit exceeded")

        for a in existing:
            if a.original_filename == scanned.relative:
                raise ScanError(
                    f"artifact filename already present in run: {scanned.relative}"
                )

        content_hash = self.storage.put_file(path, content_hash=scanned.content_hash)
        blob_path = self.storage.get_path(content_hash)
        decision = self.router.route_new_ingest(manifest)

        art_id = _new_artifact_id()
        stored = self.isolation.place_link(
            run_id, decision.isolation, scanned.relative, blob_path
        )

        rec = ArtifactRecord(
            artifact_id=art_id,
            run_id=run_id,
            content_hash=content_hash,
            original_filename=scanned.relative,
            stored_location=str(stored),
            media_type=scanned.media_type,
            size_bytes=scanned.size_bytes,
            source_subsystem=manifest.subsystem,
            parent_run=manifest.parent_run,
            trust=Trust.UNTRUSTED,
            evidence_grade=EvidenceGrade.EXPLORATORY,
            isolation=decision.isolation,
            sensitivity=manifest.sensitivity,
            created_at=_utc_now(),
        )
        self.registry.put_artifact(rec)

        ref = ArtifactRef(
            artifact_id=art_id,
            content_hash=content_hash,
            filename=scanned.relative,
            media_type=scanned.media_type,
            size_bytes=scanned.size_bytes,
            role=role,
        )
        if role == "input":
            manifest.inputs.append(ref)
        else:
            manifest.outputs.append(ref)
        if manifest.status == RunStatus.PENDING:
            manifest.status = RunStatus.RUNNING
        attach_manifest_hash(manifest)
        self.registry.put_run(manifest)
        write_manifest(
            self.isolation.run_dir(run_id, decision.isolation) / "manifest.json",
            manifest,
        )
        return rec

    def add_check(
        self,
        *,
        run_id: str,
        name: str,
        status: str,
        detail: str = "",
        verifier_id: str = "",
        verifier_version: str = "",
        target: str = "",
        certificate_hash: str = "",
    ) -> CheckResult:
        manifest = self.registry.get_run(run_id)
        if manifest is None:
            raise KeyError(f"unknown run_id: {run_id}")
        check = CheckResult(
            name=name,
            status=status,
            detail=detail,
            verifier_id=verifier_id,
            verifier_version=verifier_version,
            target=target,
            certificate_hash=certificate_hash,
            timestamp=_utc_now(),
        )
        manifest.checks.append(check)
        attach_manifest_hash(manifest)
        self.registry.put_run(manifest)
        return check

    def verify(self, run_id: str) -> dict[str, Any]:
        manifest = self.registry.get_run(run_id)
        if manifest is None:
            raise KeyError(f"unknown run_id: {run_id}")
        blob_paths: dict[str, Path] = {}
        refs = list(manifest.inputs) + list(manifest.outputs)
        for ref in refs:
            if self.storage.exists(ref.content_hash):
                blob_paths[ref.content_hash] = self.storage.get_path(ref.content_hash)
        result = self.verifier.verify_run(manifest, blob_paths=blob_paths)

        if not result.ok:
            manifest.status = RunStatus.FAILED
            route = self.router.route_after_checks(manifest)
        else:
            if manifest.status != RunStatus.FAILED:
                manifest.status = RunStatus.COMPLETED
            route = self.router.route_after_checks(manifest)

        seen = {(c.name, c.detail, c.status) for c in manifest.checks}
        for c in result.checks:
            key = (c.name, c.detail, c.status)
            if key not in seen:
                manifest.checks.append(c)
        attach_manifest_hash(manifest)
        self.registry.put_run(manifest)
        return {
            "ok": result.ok,
            "messages": result.messages,
            "checks": [c.as_dict() for c in result.checks],
            "status": manifest.status.value,
            "route": {"isolation": route.isolation.value, "rule": route.rule},
            "policy_hash": getattr(self.routing_policy, "content_hash", "") or "",
        }

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        return self.registry.list_artifacts(run_id)

    def promote(
        self,
        artifact_id: str,
        *,
        target: str,
        actor: str = "operator",
        reason: str = "",
        verifier_evidence: dict[str, Any] | None = None,
        verifier_id: str | None = None,
        proof_target: str = "",
        source_commit: str = "",
    ) -> dict[str, Any]:
        rec = self.registry.get_artifact(artifact_id)
        if rec is None:
            raise KeyError(f"unknown artifact_id: {artifact_id}")
        try:
            target_iso = Isolation(target.upper())
        except ValueError as e:
            raise ValueError(
                f"unknown isolation target: {target}; "
                f"expected one of {[i.value for i in Isolation]}"
            ) from e

        run = self.registry.get_run(rec.run_id)
        sc = source_commit or (run.source_commit if run else "")
        pt = proof_target

        required_cap = None
        if target_iso == Isolation.VALIDATED:
            required_cap = VerifierCapability.INTEGRITY_CHECK
            if not pt:
                pt = "integrity"
        elif target_iso == Isolation.CERTIFIED_READ_ONLY:
            required_cap = VerifierCapability.FORMAL_CERTIFICATE_VERIFICATION

        execution_record = None
        if verifier_id:
            req = VerificationRequest(
                artifact_id=rec.artifact_id,
                content_hash=rec.content_hash,
                source_commit=sc,
                proof_target=pt,
                required_capability=required_cap,
            )
            execution_record = self.verifiers.execute(verifier_id, req)
        elif target_iso == Isolation.VALIDATED:
            req = VerificationRequest(
                artifact_id=rec.artifact_id,
                content_hash=rec.content_hash,
                source_commit=sc,
                proof_target=pt or "integrity",
                required_capability=VerifierCapability.INTEGRITY_CHECK,
            )
            execution_record = self.verifiers.execute("hash_bound_self_check", req)

        promo = self.promotion_gate.promote(
            rec,
            target_isolation=target_iso,
            actor=actor,
            reason=reason or f"promote to {target_iso.value}",
            verifier_evidence=None,
            execution_record=execution_record,
            source_commit=sc,
            proof_target=pt,
        )
        return promo.as_dict()

    def export_run(self, run_id: str, destination: Path | str) -> Path:
        manifest = self.registry.get_run(run_id)
        if manifest is None:
            raise KeyError(f"unknown run_id: {run_id}")
        dest_raw = Path(destination)
        if dest_raw.exists():
            reject_symlink(dest_raw, "export destination")
        dest = dest_raw.resolve()
        dest.mkdir(parents=True, exist_ok=True)
        reject_symlink(dest, "export destination")
        write_manifest(dest / "manifest.json", manifest)
        art_dir = dest / "artifacts"
        art_dir.mkdir(exist_ok=True)
        reject_symlink(art_dir, "export artifacts dir")
        art_dir_res = art_dir.resolve()
        for rec in self.registry.list_artifacts(run_id):
            src = self.storage.get_path(rec.content_hash)
            safe_name = Path(rec.original_filename).name
            out = art_dir / safe_name
            out_res = ensure_under(art_dir_res, out, "export path")
            out_res.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out_res)
        promos = self.registry.list_promotions(run_id=run_id)
        (dest / "promotions.json").write_text(
            json.dumps([p.as_dict() for p in promos], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return dest

    def audit(self, run_id: str) -> list[dict[str, Any]]:
        return [p.as_dict() for p in self.registry.list_promotions(run_id=run_id)]

    def init_layout(self) -> Path:
        for name in (
            "intake",
            "quarantine",
            "sandbox",
            "validated",
            "certified",
            "rejected",
            "blobs",
            "runs",
        ):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        _ = self.registry
        return self.root
