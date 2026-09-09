"""Proof-killer — every claimed breakthrough dies here or is admitted as finite.

The Duck is structurally incapable of declaring a Millennium Prize solved.
Unbounded sentences never become Field state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qwuack.millennium.artifacts import Artifact, ArtifactKind, Memory


UNBOUNDED_MARKERS = (
    "for all integers",
    "for every integer",
    "all nontrivial zeros",
    "all non-trivial zeros",
    "in the continuum",
    "p = np",
    "p=np",
    "p != np",
    "p≠np",
    "mass gap exists",
    "smooth for all time",
    "all Hodge classes",
    "rank equals",
    "millennium prize is solved",
    "the prize is solved",
    "I have proved",
    "we have proved the millennium",
)

PRIZE_VICTORY_MARKERS = (
    "prize solved",
    "millennium solved",
    "declares victory",
    "proof of the millennium",
    "clay prize claimed",
)


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str
    attacks_landed: int
    notes: tuple[str, ...] = ()

    @property
    def admitted(self) -> bool:
        return self.status in {"VERIFIED", "REFUTED", "PROGRESS", "REJECTED"}


class ProofKiller:
    """Adversary sitting between a claim and MetaField admission."""

    def attack(self, artifact: Artifact, memory: Memory) -> Verdict:
        statement = artifact.statement.lower()
        notes: list[str] = []
        landed = 0

        if artifact.evidence.get("declares_prize_solved") or any(
            m in statement for m in PRIZE_VICTORY_MARKERS
        ):
            landed += 1
            return Verdict(
                status="KILLED",
                reason="victory_without_verification",
                attacks_landed=landed,
                notes=("Duck cannot declare a Millennium Prize solved.",),
            )

        unbounded = bool(artifact.evidence.get("unbounded")) or any(
            m in statement for m in UNBOUNDED_MARKERS
        )
        named = self._named_domain(artifact)
        if unbounded or (artifact.kind != ArtifactKind.REJECTION and not named):
            landed += 1
            notes.append("unbounded_or_unnamed")
            return Verdict(
                status="REJECTED",
                reason="unbounded_not_an_experiment",
                attacks_landed=landed,
                notes=tuple(notes),
            )

        if artifact.kind == ArtifactKind.FORMAL and not artifact.evidence.get("certificate"):
            landed += 1
            return Verdict(
                status="KILLED",
                reason="formal_without_certificate",
                attacks_landed=landed,
                notes=("Formal proofs require a checker certificate.",),
            )

        if self._contradicted(artifact, memory):
            landed += 1
            return Verdict(
                status="KILLED",
                reason="contradicted_by_memory",
                attacks_landed=landed,
                notes=("Stored counterexample kills the claim.",),
            )

        if artifact.recipe and artifact.evidence.get("replay_required"):
            ok = artifact.evidence.get("replay_ok")
            if ok is False:
                landed += 1
                return Verdict(
                    status="KILLED",
                    reason="replay_mismatch",
                    attacks_landed=landed,
                    notes=("Recipe did not reproduce the claimed evidence.",),
                )

        if artifact.status in {"VERIFIED", "REFUTED", "PROGRESS", "REJECTED"}:
            return Verdict(
                status=artifact.status,
                reason="survived_killer",
                attacks_landed=landed,
                notes=tuple(notes) or ("finite_named_experiment",),
            )
        return Verdict(
            status="KILLED",
            reason="unknown_status",
            attacks_landed=landed + 1,
            notes=("Claim status is not a finite experiment outcome.",),
        )

    def _named_domain(self, artifact: Artifact) -> bool:
        ev = artifact.evidence or {}
        recipe = artifact.recipe or {}
        keys = ("n", "lo", "hi", "t_lo", "t_hi", "L", "beta", "curve", "complex", "seed", "window")
        return any(k in ev or k in recipe for k in keys) or bool(ev.get("named"))

    def _contradicted(self, artifact: Artifact, memory: Memory) -> bool:
        family = artifact.evidence.get("family")
        if not family:
            return False
        for prior in memory.counterexamples(artifact.pond):
            if prior.evidence.get("family") == family and artifact.kind != ArtifactKind.COUNTEREXAMPLE:
                return True
        return False


def apply_verdict(artifact: Artifact, verdict: Verdict) -> Artifact:
    artifact.status = verdict.status
    artifact.notes = list(artifact.notes) + list(verdict.notes)
    artifact.evidence = dict(artifact.evidence)
    artifact.evidence["killer_reason"] = verdict.reason
    artifact.evidence["attacks_landed"] = verdict.attacks_landed
    return artifact
