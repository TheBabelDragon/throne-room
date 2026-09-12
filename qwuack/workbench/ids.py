"""Immutable, enumerable IDs for every mathematical object on the desk.

Prefixes are kind-stable. Numbers are monotonic per store. An ID is never reused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


PREFIX = {
    "problem": "MATH-MP",
    "definition": "D",
    "fact": "F",
    "conjecture": "C",
    "claim": "C",
    "target": "T",
    "equation": "E",
    "lemma": "L",
    "proof": "P",
    "counterexample": "X",
    "experiment": "N",
    "attempt": "A",
    "dependency": "Y",
    "result": "R",
    "hypothesis": "H",
    "known": "K",
    "goal": "G",
    "session": "S",
    "certificate": "VC",
}


@dataclass
class IdAllocator:
    counters: dict[str, int] = field(default_factory=dict)

    def next(self, kind: str) -> str:
        prefix = PREFIX.get(kind, kind.upper()[:1] or "Z")
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        if prefix == "MATH-MP":
            return f"MATH-MP-{n:02d}"
        if prefix == "E":
            return f"E-{n:06d}"
        return f"{prefix}-{n:04d}"

    def seed(self, used: Mapping[str, int] | None = None) -> None:
        if used:
            for k, v in used.items():
                self.counters[k] = max(self.counters.get(k, 0), int(v))

    def as_dict(self) -> dict[str, int]:
        return dict(self.counters)
