"""Immutable Qwuack identity. Who the duck is — not where the duck is.

World facts (temperature, position, water) belong to perception / MetaField.
Identity does not encode them and cannot write the Field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from agent.schemas import ACTION_CAPABILITY, Capability

# Habitat is a jurisdiction label. It is not god-mode.
# "The lake belongs to Daddy" — substrate + commit/authority rules own the Field.
HABITAT_LAKE = "lake"

# Actions Qwuack may *propose*. Authorization still belongs to the Operator ABI.
HABITAT_ACTIONS: tuple[str, ...] = (
    "QUERY_FIELD",
    "ATTEND",
    "PROBE",
    "REMEMBER",
    "SPEAK",
    "WAIT",
)

# act.device stays outside the default set. Aurora / ESCAPE owns hardware.
HABITAT_CAPABILITIES: FrozenSet[Capability] = frozenset(
    ACTION_CAPABILITY[action] for action in HABITAT_ACTIONS
)


@dataclass(frozen=True)
class QwuackIdentity:
    name: str = "Qwuack"
    species: str = "duck"
    habitat: str = HABITAT_LAKE
    role: str = "embodied_field_agent"
    agent_id: str = "qwuack-0"

    def permitted_actions(self) -> tuple[str, ...]:
        return HABITAT_ACTIONS

    def permitted_capabilities(self) -> FrozenSet[Capability]:
        return HABITAT_CAPABILITIES

    def allows_action(self, action_type: str) -> bool:
        return action_type in HABITAT_ACTIONS

    def allows_capability(self, capability: str) -> bool:
        return capability in HABITAT_CAPABILITIES


QWUACK = QwuackIdentity()
