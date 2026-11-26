"""Verification helpers.

Does not pretend to verify Lean certificates unless a real Lean process
is invoked and its result independently checked. v0.1 records evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import CheckResult, EvidenceGrade, RunManifest
from .hashing import sha256_file
from pathlib import Path


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
        checks: list[CheckResult] = list(manifest.checks)

        # Integrity: re-hash outputs if paths provided
        if blob_paths:
            for ref in manifest.outputs + manifest.inputs:
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
                else:
                    checks.append(
                        CheckResult(
                            name="blob_integrity",
                            status="PASS",
                            detail=ref.filename,
                        )
                    )

        # Self-declared high grades without verifier evidence are flagged
        if manifest.evidence_grade in (
            EvidenceGrade.FORMALLY_PROVED,
            EvidenceGrade.CERTIFIED,
        ):
            formal_ok = any(
                c.status == "PASS"
                and c.verifier_id
                and c.certificate_hash
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

        ok = all(c.status != "FAIL" for c in checks) and not any(
            "mismatch" in m or "missing" in m for m in messages
        )
        return VerifyResult(ok=ok, checks=checks, messages=messages)
