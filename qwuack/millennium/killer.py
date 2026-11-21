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

        # Yang–Mills category-error defenses (structured evidence first)
        ym_verdict = self._yang_mills_category_errors(artifact)
        if ym_verdict is not None:
            return ym_verdict

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

    def _yang_mills_category_errors(self, artifact: Artifact) -> Verdict | None:
        """Reject YM category errors using structured evidence.

        Legitimate finite SU(2) experiments survive as computational evidence.
        Promotions to continuum / non-Abelian / theorem status die here.
        """
        if artifact.pond not in {"yang_mills", "lab"} and not self._looks_like_ym(artifact):
            return None

        ev = artifact.evidence or {}
        statement = (artifact.statement or "").lower()
        landed = 0

        forbidden = ev.get("forbidden_shortcut")
        if forbidden in {
            "u1_toy_as_nonabelian_ym",
            "finite_lattice_as_continuum",
            "numerical_gap_proxy_as_proof",
            "finite_scaling_as_continuum_proof",
            "single_volume_as_uniform_bound",
            "statistical_fit_as_theorem",
        }:
            landed += 1
            return Verdict(
                status="REJECTED",
                reason=str(forbidden),
                attacks_landed=landed,
                notes=(f"forbidden_shortcut:{forbidden}", "category_error"),
            )

        is_u1 = (
            ev.get("group") in {"U(1)", "U1", "u1"}
            or ev.get("family") == "u1_wilson_finite"
            or ev.get("legacy_baseline") is True
        )
        claims_nonabelian = (
            ev.get("is_nonabelian") is True
            or "nonabelian" in statement
            or "non-abelian" in statement
            or "su(2)" in statement
            or "su(3)" in statement
        )
        if is_u1 and claims_nonabelian:
            landed += 1
            return Verdict(
                status="REJECTED",
                reason="u1_toy_as_nonabelian_ym",
                attacks_landed=landed,
                notes=("U(1) toy is not non-Abelian Yang–Mills.",),
            )

        is_finite = (
            ev.get("is_continuum") is False
            or ev.get("evidence_level") in {
                "finite_lattice",
                "monte_carlo_finite_lattice",
                "finite_volume_correlation",
            }
            or "finite lattice" in statement
            or "finite_lattice" in str(ev.get("family", ""))
        )
        claims_continuum = (
            ev.get("is_continuum") is True
            or ev.get("evidence_level") == "continuum_construction"
            or "continuum construction" in statement
            or "continuum limit proven" in statement
            or ("in the continuum" in statement and artifact.kind != ArtifactKind.REJECTION)
        )
        if claims_continuum and is_finite and artifact.kind not in {
            ArtifactKind.REJECTION,
            ArtifactKind.TRANSFORM,
        }:
            landed += 1
            return Verdict(
                status="REJECTED",
                reason="finite_lattice_as_continuum",
                attacks_landed=landed,
                notes=("Finite lattice is not continuum construction.",),
            )
        if (
            artifact.kind in {ArtifactKind.FORMAL, ArtifactKind.LEMMA}
            and (ev.get("is_continuum") is True or "continuum" in statement)
            and not ev.get("certificate")
            and artifact.status in {"VERIFIED", "PROOF"}
        ):
            landed += 1
            return Verdict(
                status="KILLED",
                reason="finite_lattice_as_continuum",
                attacks_landed=landed,
                notes=("Continuum claim without formal continuum construction.",),
            )

        is_gap_proxy = (
            "gap_proxy" in ev
            or ev.get("evidence_level") in {"numerical_spectral_estimate", "finite_lattice"}
            or "gap_proxy" in statement
            or "effective-mass" in statement
            or "effective mass" in statement
        )
        claims_mass_gap_theorem = (
            artifact.kind in {ArtifactKind.FORMAL, ArtifactKind.LEMMA}
            and (
                "mass gap" in statement
                or "mass-gap" in statement
                or ev.get("is_proof") is True
            )
            and not (ev.get("certificate") and artifact.evidence.get("formal") == "PASS")
        )
        if is_gap_proxy and claims_mass_gap_theorem:
            landed += 1
            return Verdict(
                status="REJECTED",
                reason="numerical_gap_proxy_as_proof",
                attacks_landed=landed,
                notes=("Numerical gap proxy is not a mass-gap theorem.",),
            )
        if (
            artifact.kind == ArtifactKind.FORMAL
            and "mass gap" in statement
            and not ev.get("certificate")
        ):
            landed += 1
            return Verdict(
                status="KILLED",
                reason="numerical_gap_proxy_as_proof",
                attacks_landed=landed,
                notes=("Mass-gap formal claim requires a real certificate.",),
            )

        if (
            ev.get("result_class") in {"multi_lattice", "finite_volume", "scaling_hypothesis"}
            or ev.get("evidence_level") in {"multi_lattice", "scaling_hypothesis"}
        ) and (
            artifact.kind in {ArtifactKind.FORMAL, ArtifactKind.LEMMA}
            or ev.get("is_continuum") is True
            or "continuum limit" in statement
        ):
            if not ev.get("certificate"):
                landed += 1
                return Verdict(
                    status="REJECTED",
                    reason="finite_scaling_as_continuum_proof",
                    attacks_landed=landed,
                    notes=("Finite-volume scaling is not continuum proof.",),
                )

        if artifact.kind == ArtifactKind.FORMAL and (
            str(ev.get("evidence_level", "")).startswith("monte_carlo")
            or str(ev.get("family", "")).endswith("_finite")
            or "monte carlo" in statement
        ) and not ev.get("certificate"):
            landed += 1
            return Verdict(
                status="KILLED",
                reason="numerical_gap_proxy_as_proof",
                attacks_landed=landed,
                notes=("Monte Carlo output is not a formal certificate.",),
            )

        claims_su2 = (
            ev.get("group") in {"SU(2)", "SU2"}
            or "su(2)" in statement
            or ev.get("family") == "su2_wilson_finite"
        )
        if claims_su2 and artifact.kind not in {ArtifactKind.REJECTION, ArtifactKind.TRANSFORM}:
            missing = []
            if not ev.get("group"):
                missing.append("group")
            if not any(k in ev for k in ("L", "Lx", "lattice", "lattice_dims")):
                lat = ev.get("lattice") or {}
                if not (isinstance(lat, dict) and lat.get("Lx")):
                    if "L" not in ev:
                        missing.append("lattice")
            if missing and not ev.get("named"):
                landed += 1
                return Verdict(
                    status="REJECTED",
                    reason="missing_su2_provenance",
                    attacks_landed=landed,
                    notes=(f"missing_fields:{','.join(missing)}",),
                )

        return None

    def _looks_like_ym(self, artifact: Artifact) -> bool:
        ev = artifact.evidence or {}
        if ev.get("family") in {"u1_wilson_finite", "su2_wilson_finite"}:
            return True
        if ev.get("group") in {"SU(2)", "SU(3)", "U(1)", "SU2", "SU3", "U1"}:
            return True
        st = (artifact.statement or "").lower()
        return any(
            k in st
            for k in ("yang-mills", "yang–mills", "wilson", "plaquette", "mass gap", "gauge")
        )


def apply_verdict(artifact: Artifact, verdict: Verdict) -> Artifact:
    artifact.status = verdict.status
    artifact.notes = list(artifact.notes) + list(verdict.notes)
    artifact.evidence = dict(artifact.evidence)
    artifact.evidence["killer_reason"] = verdict.reason
    artifact.evidence["attacks_landed"] = verdict.attacks_landed
    return artifact
