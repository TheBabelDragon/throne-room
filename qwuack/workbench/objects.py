"""First-class mathematical objects. The Duck does not emit vibes; it emits these."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ObjectKind(str, Enum):
    PROBLEM = "problem"
    DEFINITION = "definition"
    CLAIM = "claim"
    EQUATION = "equation"
    LEMMA = "lemma"
    PROOF = "proof"
    COUNTEREXAMPLE = "counterexample"
    EXPERIMENT = "experiment"
    ATTEMPT = "attempt"
    DEPENDENCY = "dependency"
    RESULT = "result"
    CONJECTURE = "conjecture"
    FACT = "fact"
    TARGET = "target"
    HYPOTHESIS = "hypothesis"
    KNOWN = "known"
    GOAL = "goal"


class ClaimStatus(str, Enum):
    OBSERVATION = "observation"
    CONJECTURE = "conjecture"
    COMPUTATIONAL_EVIDENCE = "computational_evidence"
    LEMMA = "lemma"
    CONDITIONAL_RESULT = "conditional_result"
    VERIFIED_DERIVATION = "verified_derivation"
    FORMALLY_VERIFIED = "formally_verified"
    PROOF = "proof"
    DISPROOF = "disproof"
    REJECTED = "rejected"
    KILLED = "killed"
    FAILED = "failed"
    OPEN = "open"
    EXPLORING = "exploring"


PROOF_STATUSES = {
    ClaimStatus.PROOF,
    ClaimStatus.DISPROOF,
    ClaimStatus.FORMALLY_VERIFIED,
}


@dataclass
class MathObject:
    id: str
    kind: ObjectKind
    statement: str
    problem: str = ""
    status: ClaimStatus = ClaimStatus.OPEN
    derived_from: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    worker: str = ""
    session: str = ""
    ts: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            self.kind = ObjectKind(self.kind)
        if isinstance(self.status, str):
            self.status = ClaimStatus(self.status)
        if not self.ts:
            self.ts = utcnow()
        self.verification.setdefault("symbolic", "NOT_RUN")
        self.verification.setdefault("numerical", "NOT_RUN")
        self.verification.setdefault("literature", "NOT_RUN")
        self.verification.setdefault("formal", "NOT_VERIFIED")

    @property
    def is_proof(self) -> bool:
        if self.status not in PROOF_STATUSES:
            return False
        if self.verification.get("formal") != "PASS":
            return False
        return True

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["kind"] = self.kind.value
        row["status"] = self.status.value
        return row

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MathObject":
        payload = dict(data)
        payload.pop("progress", None)
        return cls(**payload)
