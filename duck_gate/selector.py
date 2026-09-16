"""Pure candidate selection policy.

select(...) returns a CandidateExcitation recommendation only.
It never returns an ActionProposal and never mutates the world.

MODE=RANDOM requires an explicit seeded RNG so tests can prove
deterministic behaviour. MODE=DUCK is fully deterministic given
identical candidates + weights.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Mapping, Sequence

from duck_gate.candidates import CandidateExcitation
from duck_gate.scoring import score


class Mode(str, Enum):
    RANDOM = "RANDOM"
    DUCK = "DUCK"


Scorer = Callable[[CandidateExcitation, Mapping[str, float] | None], float]


def select(
    candidates: Sequence[CandidateExcitation],
    mode: Mode | str = Mode.DUCK,
    *,
    scorer: Scorer = score,
    weights: Mapping[str, float] | None = None,
    rng=None,
) -> CandidateExcitation:
    """Select one candidate according to mode.

    Parameters
    ----------
    candidates :
        Non-empty sequence of CandidateExcitation.
    mode :
        "RANDOM" or "DUCK".
    scorer :
        Pure scoring function. Defaults to duck_gate.scoring.score.
    weights :
        Optional weight override passed to scorer.
    rng :
        Required for MODE=RANDOM. Must expose .choice(seq).
        Injected so the caller (and tests) control determinism.

    Returns
    -------
    CandidateExcitation
        A recommendation only. Never an ActionProposal.
    """
    if not candidates:
        raise ValueError("select requires a non-empty candidate sequence")

    if isinstance(mode, Mode):
        mode_norm = mode
    else:
        mode_norm = Mode(str(mode).upper())

    if mode_norm is Mode.RANDOM:
        if rng is None:
            raise ValueError("MODE=RANDOM requires an explicit rng dependency")
        return rng.choice(list(candidates))

    # MODE=DUCK: argmax of score; stable tie-break by ascending candidate_id
    ranked = sorted(
        candidates,
        key=lambda c: (-scorer(c, weights), c.candidate_id),
    )
    return ranked[0]
