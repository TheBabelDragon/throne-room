"""Verification helpers.

Does not pretend to verify Lean certificates unless a real Lean process
is invoked and its result independently checked. v0.1 records evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_file
from .models import CheckResult, EvidenceGrade, RunManifest


@dataclass
class VerifyResult:
    ok: bool
    checks: list[CheckResult]
    messages: list[str]


class ArtifactVerifier:
    """Integrity and policy verification for a run."""

    def verify_run(
        self,
        manifest: RunManifest,
        blob_paths: dict[str, Path] | None = None,
    ) -> VerifyResult:
        messages: list[str] = []
        # Start from a copy so we never mutate caller's prior evidence in-place oddly
        checks: list[CheckResult] = list(manifest.checks)
        blob_paths = blob_paths or {}

        refs = list(manifest.outputs) + list(manifest.inputs)
        # Missing blobs must fail even when zero blobs / empty blob_paths
        for ref in refs:
            p = blob_paths.get(ref.content_hash)
            if p is None:
                messages.append(f"missing blob for {ref.artifact_id}")
                checks.append(
                    CheckResult(
                        name="blob_presence",
                        status="FAIL",
                        detail=f"missing {ref.content_hash[:16]}",
                    )
                )
                continue
            actual = sha256_file(p)
            size = p.stat().st_size
            if actual != ref.content_hash:
                messages.append(
                    f"hash mismatch for {ref.filename}: "
                    f"expected {ref.content_hash[:16]} got {actual[:16]}"
                )
                checks.append(
                    CheckResult(
                        name="blob_integrity",
                        status="FAIL",
                        detail=ref.filename,
                    )
                )
            elif ref.size_bytes and size != ref.size_bytes:
                messages.append(
                    f"size mismatch for {ref.filename}: "
                    f"expected {ref.size_bytes} got {size}"
                )
                checks.append(
                    CheckResult(
                        name="blob_size",
                        status="FAIL",
                        detail=ref.filename,
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        name="blob_integrity",
                        status="PASS",
                        detail=ref.filename,
                    )
                )

        if manifest.evidence_grade in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            formal_ok = any(
                c.status == "PASS" and c.verifier_id and c.certificate_hash
                for c in checks
            )
            if not formal_ok:
                messages.append(
                    "FORMALLY_PROVED/CERTIFIED declared without verifier "
                    "identity + certificate hash + PASS"
                )
                checks.append(
                    CheckResult(
                        name="formal_evidence",
                        status="FAIL",
                        detail="missing independent verifier evidence",
                    )
                )

        ok = all(c.status != "FAIL" for c in checks)
        return VerifyResult(ok=ok, checks=checks, messages=messages)
