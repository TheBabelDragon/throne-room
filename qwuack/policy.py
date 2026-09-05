"""Pure Qwuack policy. Proposes. Never writes the Field.

Inputs are a perception *view* (measurements already on the observer
bridge), a SELF snapshot, the ABI capability set, and the last FieldTick.
Output is an ActionProposal — including WAIT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent.hashutil import fnv1a
from agent.schemas import (
    ACTION_CAPABILITY,
    ActionProposal,
    FieldTick,
    PerceptionEvent,
)
from qwuack.identity import HABITAT_ACTIONS, QWUACK, QwuackIdentity

ENERGY_CONTACT = 0.30
ENERGY_ATTEND = 0.20


@dataclass(frozen=True)
class QwuackPerception:
    """Bounded view of a PerceptionEvent. Measurements, not omniscience."""

    observation_id: str
    timestamp: str
    sequence: int
    source: str
    modality: str
    location: dict[str, int] | None
    channels: tuple[str, ...]
    measurement: dict[str, Any]
    confidence: float
    provenance: str


def perception_view(event: PerceptionEvent) -> QwuackPerception:
    """Project an existing PerceptionEvent. Do not invent semantics."""
    features = dict(event.features or {})
    location = None
    if event.coordinates is not None:
        location = event.coordinates.as_dict()
    channels = tuple(sorted(str(k) for k in features.keys()))
    return QwuackPerception(
        observation_id=event.id,
        timestamp=event.timestamp,
        sequence=int(event.tick),
        source=event.source,
        modality=event.modality,
        location=location,
        channels=channels,
        measurement=features,
        confidence=float(event.confidence),
        provenance=f"{event.schema}:{event.source}:{event.id}",
    )


def _proposal_id(observation_id: str, action_type: str) -> str:
    return f"prp_qwuack_{fnv1a(f'{observation_id}:{action_type}')}"


def _energy(measurement: Mapping[str, Any]) -> float:
    raw = measurement.get("energy", measurement.get("csi_energy", 0.0))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _working(self_state: Mapping[str, Any]) -> dict[str, Any]:
    working = self_state.get("working") or {}
    if not isinstance(working, dict):
        return {}
    q = working.get("qwuack") or {}
    return q if isinstance(q, dict) else {}


def decide(
    perception: QwuackPerception,
    self_state: Mapping[str, Any],
    capabilities: frozenset[str] | set[str] | tuple[str, ...],
    last_tick: FieldTick | None = None,
    identity: QwuackIdentity = QWUACK,
    **kwargs: Any,
) -> ActionProposal:
    """Deterministic policy. Same perception + SELF → same proposal.

    Rejects a Field write handle if one is smuggled in.
    """
    if "field" in kwargs or "scheduler" in kwargs or "voxel" in kwargs:
        raise PermissionError("Qwuack has no Field write handle")
    if kwargs:
        raise TypeError(f"unexpected policy inputs: {sorted(kwargs)}")

    caps = set(capabilities)
    memory = _working(self_state)
    energy = _energy(perception.measurement)
    last_action = str(memory.get("last_action") or "")
    last_energy = memory.get("last_energy")
    try:
        last_energy_f = float(last_energy) if last_energy is not None else None
    except (TypeError, ValueError):
        last_energy_f = None

    text = str(perception.measurement.get("text") or "").strip()

    if perception.modality == "language" and text:
        action = "SPEAK"
        params: dict[str, Any] = {
            "text": "Qwuack heard the operator. Attending the lake.",
        }
        target = "chat"
        rationale = "Language perception arrived on the existing chat actuator."
        confidence = 0.84
    elif last_action == "PROBE" and last_energy_f is not None:
        if energy + 1e-9 >= last_energy_f:
            action = "REMEMBER"
            params = {
                "note": (
                    f"tick {perception.sequence}: probe consequence held "
                    f"energy {last_energy_f:.4f} → {energy:.4f}"
                )
            }
            target = "memory"
            rationale = "Observed probe consequence; retain it in SELF."
            confidence = 0.88
        else:
            action = "ATTEND"
            params = {"target": "field"}
            target = "field"
            rationale = "Probe did not hold energy; attend before acting again."
            confidence = 0.80
    elif last_action == "ATTEND" and energy >= ENERGY_CONTACT:
        action = "PROBE"
        params = {"magnitude": 0.45}
        if perception.location:
            params["x"] = perception.location.get("x", 8)
            params["z"] = perception.location.get("z", 8)
        target = "field"
        rationale = "Attended the lake; curiosity authorizes a bounded probe."
        confidence = 0.78
    elif last_action == "" and energy >= ENERGY_CONTACT:
        action = "PROBE"
        params = {"magnitude": 0.45}
        if perception.location:
            params["x"] = perception.location.get("x", 8)
            params["z"] = perception.location.get("z", 8)
        target = "field"
        rationale = "First contact with a live measurement; bounded probe."
        confidence = 0.76
    elif energy >= ENERGY_ATTEND or perception.channels:
        action = "ATTEND"
        params = {"target": perception.source or "field"}
        target = perception.source or "field"
        rationale = "Measurement present; attend before proposing work."
        confidence = 0.72
    else:
        action = "WAIT"
        params = {}
        target = "field"
        rationale = "Nothing in the perception view warrants motion."
        confidence = 0.60

    if action not in HABITAT_ACTIONS or not identity.allows_action(action):
        action = "WAIT"
        params = {}
        target = "field"
        rationale = "Action outside habitat scope; WAIT."
        confidence = 0.99

    capability = ACTION_CAPABILITY.get(action, "observe.field")
    if capability not in caps or not identity.allows_capability(capability):
        action = "WAIT"
        params = {}
        target = "field"
        rationale = f"Missing capability {capability}; WAIT."
        confidence = 0.99
        capability = ACTION_CAPABILITY["WAIT"]

    if last_tick is not None:
        sum(1 for d in last_tick.deltas if d.system_id == 6)

    return ActionProposal(
        proposal_id=_proposal_id(perception.observation_id, action),
        action_type=action,
        parameters=params,
        target=target,
        rationale=rationale,
        confidence=confidence,
        originating_observation=perception.observation_id,
        agent_id=identity.agent_id,
        capability=capability,
    )
