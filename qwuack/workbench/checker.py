"""Stub formal checker. Issues and verifies certificate blobs.

This is not Lean. It is the smallest fail-closed adapter that can
emit `formal: PASS` only when a signed certificate blob verifies.

A raw verification tag is never authority. The blob is.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

CHECKER_ID = "throne.checker.v0"
# Lab-local signing secret for the stub. Not a network credential.
# Real checkers replace issue/verify with an external kernel.
_STUB_SECRET = b"throne.checker.v0.fail-closed"


def _canonical(payload: dict[str, Any]) -> bytes:
    body = {k: payload[k] for k in sorted(payload) if k != "token"}
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _token(payload: dict[str, Any]) -> str:
    return hmac.new(_STUB_SECRET, _canonical(payload), hashlib.sha256).hexdigest()


def statement_hash(statement: str) -> str:
    return hashlib.sha256((statement or "").encode("utf-8")).hexdigest()


def recipe_hash(recipe: dict[str, Any] | None) -> str:
    blob = json.dumps(recipe or {}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class CheckerCertificate:
    """Machine-checkable witness that a named claim passed a checker."""

    checker_id: str
    claim_id: str
    problem_id: str
    statement_hash: str
    recipe_hash: str
    status: str
    token: str

    def as_dict(self) -> dict[str, str]:
        return {
            "checker_id": self.checker_id,
            "claim_id": self.claim_id,
            "problem_id": self.problem_id,
            "statement_hash": self.statement_hash,
            "recipe_hash": self.recipe_hash,
            "status": self.status,
            "token": self.token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CheckerCertificate | None":
        if not isinstance(data, dict):
            return None
        try:
            return cls(
                checker_id=str(data["checker_id"]),
                claim_id=str(data["claim_id"]),
                problem_id=str(data["problem_id"]),
                statement_hash=str(data["statement_hash"]),
                recipe_hash=str(data["recipe_hash"]),
                status=str(data["status"]),
                token=str(data["token"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


def issue_certificate(
    *,
    claim_id: str,
    problem_id: str,
    statement: str,
    recipe: dict[str, Any] | None = None,
    status: str = "PASS",
) -> CheckerCertificate:
    """Mint a stub certificate. Tests and the admission path use this."""
    payload = {
        "checker_id": CHECKER_ID,
        "claim_id": claim_id,
        "problem_id": problem_id,
        "statement_hash": statement_hash(statement),
        "recipe_hash": recipe_hash(recipe),
        "status": status,
    }
    return CheckerCertificate(token=_token(payload), **payload)


def verify_certificate(blob: dict[str, Any] | CheckerCertificate | None) -> tuple[bool, str]:
    """Fail-closed verification of a checker blob."""
    cert = blob if isinstance(blob, CheckerCertificate) else CheckerCertificate.from_dict(blob)
    if cert is None:
        return False, "invalid_certificate"
    if cert.checker_id != CHECKER_ID:
        return False, "unknown_checker"
    if cert.status != "PASS":
        return False, "checker_status_not_pass"
    if not cert.claim_id or not cert.problem_id:
        return False, "certificate_missing_ids"
    if not cert.token or len(cert.token) != 64:
        return False, "invalid_token"
    expected = _token(cert.as_dict())
    if not hmac.compare_digest(expected, cert.token):
        return False, "token_mismatch"
    return True, "checker_pass"
