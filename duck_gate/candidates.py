"""Pure immutable candidate excitation records.

No filesystem, Redis, hardware, wall-clock, or imports into
agent/, qwuack/, aurora/, or the engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CandidateExcitation:
    """A scored attention / probe candidate.

    This is a recommendation only. It is never an ActionProposal
    and never commits the world.
    """

    candidate_id: str
    stimulus: str
    predicted_response: str = ""
    uncertainty: float = 0.0
    novelty: float = 0.0
    information_gain: float = 0.0
    cost: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CandidateExcitation":
        return cls(
            candidate_id=str(data["candidate_id"]),
            stimulus=str(data.get("stimulus", "")),
            predicted_response=str(data.get("predicted_response", "")),
            uncertainty=float(data.get("uncertainty", 0.0)),
            novelty=float(data.get("novelty", 0.0)),
            information_gain=float(data.get("information_gain", 0.0)),
            cost=float(data.get("cost", 0.0)),
        )
