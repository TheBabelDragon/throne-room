"""Deterministic scoring of CandidateExcitation records.

score(candidate, weights) is pure: identical inputs → identical float.
No hidden RNG, wall-clock, filesystem, or external imports.
"""

from __future__ import annotations

from typing import Mapping

from duck_gate.candidates import CandidateExcitation

# Explicit, boring defaults. No hidden Duck magic.
DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 1.0,
    "uncertainty": 1.0,
    "information_gain": 1.0,
    "cost": 1.0,
}


def score(
    candidate: CandidateExcitation,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Return weighted excitation score.

    a = w_n * N + w_u * U + w_i * I - w_c * C
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        w.update({k: float(v) for k, v in weights.items()})

    return (
        w["novelty"] * float(candidate.novelty)
        + w["uncertainty"] * float(candidate.uncertainty)
        + w["information_gain"] * float(candidate.information_gain)
        - w["cost"] * float(candidate.cost)
    )
