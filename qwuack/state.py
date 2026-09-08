"""QwuackState — tenant snapshot. Not authority. Not FieldTick."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from qwuack.gate import GATE_POLICY, GATE_VERSION
from qwuack.identity import QWUACK, QwuackIdentity

STATE_SCHEMA = "throne.qwuack.state"
STATE_VERSION = 1


@dataclass
class QwuackState:
    """Bounded view of the tenant after one admission cycle."""

    schema: str = STATE_SCHEMA
    version: int = STATE_VERSION
    gate_policy: str = GATE_POLICY
    gate_version: str = GATE_VERSION
    awake: bool = False
    habitat: str = QWUACK.habitat
    agent_id: str = QWUACK.agent_id
    sequence: int = 0
    live: bool = False
    perception: str = "idle"
    observation_id: str | None = None
    proposal_id: str | None = None
    last_action: str = "WAIT"
    authorization: str = "none"
    admission_status: str = "none"
    reason_code: str = "none"
    consequence: str = "none"
    requested_magnitude: float = 0.0
    admitted_magnitude: float = 0.0
    energy: float = 0.0
    energy_delta: float = 0.0
    tick_hash: str | None = None
    identity: dict[str, str] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        return (
            "QWUACKSTATE\n"
            "-----------\n"
            f"state:          {'awake' if self.awake else 'asleep'}\n"
            f"habitat:        {self.habitat}\n"
            f"sequence:       {self.sequence}\n"
            f"last_action:    {self.last_action}\n"
            f"admission:      {self.admission_status}\n"
            f"reason:         {self.reason_code}\n"
            f"consequence:    {self.consequence}\n"
            f"requested_Δ:    {self.requested_magnitude:.4f}\n"
            f"admitted_Δ:     {self.admitted_magnitude:.4f}\n"
        )


def identity_blob(identity: QwuackIdentity = QWUACK) -> dict[str, str]:
    return {
        "name": identity.name,
        "species": identity.species,
        "habitat": identity.habitat,
        "role": identity.role,
        "agent_id": identity.agent_id,
    }
