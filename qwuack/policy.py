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


def _energy(measurement: Mapping[str, Any]) -> float | None:
    """Return energy only when genuinely present. None = missing (not zero)."""
    if "energy" in measurement and measurement["energy"] is not None:
        raw = measurement["energy"]
    elif "csi_energy" in measurement and measurement["csi_energy"] is not None:
        raw = measurement["csi_energy"]
    elif "m:csi_energy" in measurement and measurement["m:csi_energy"] is not None:
        raw = measurement["m:csi_energy"]
    else:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _is_synthetic(measurement: Mapping[str, Any]) -> bool:
    return bool(measurement.get("synthetic", False))


def _body_status(measurement: Mapping[str, Any]) -> str:
    return str(measurement.get("status") or "UNKNOWN")


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
    energy_val = energy if energy is not None else -1.0
    synthetic = _is_synthetic(perception.measurement)
    body_status = _body_status(perception.measurement)
    is_shared = perception.modality == "shared_body" or "body_id" in perception.measurement
    meas_changed = bool(perception.measurement.get("measurement_changed"))
    is_new_body = bool(perception.measurement.get("is_new"))
    is_returning = bool(perception.measurement.get("is_returning"))

    # Stale / timed-out observations are not current evidence
    if is_shared and body_status in ("STALE", "TIMEOUT", "MISSING"):
        return ActionProposal(
            proposal_id=_proposal_id(perception.observation_id, "WAIT"),
            action_type="WAIT",
            parameters={},
            target="field",
            rationale=f"Observation status {body_status}; not treating as current.",
            confidence=0.95,
            originating_observation=perception.observation_id,
            agent_id=identity.agent_id,
            capability=ACTION_CAPABILITY["WAIT"],
        )

    # Synthetic fixtures must not authorize physical contact probes
    if synthetic and energy_val >= ENERGY_CONTACT:
        return ActionProposal(
            proposal_id=_proposal_id(perception.observation_id, "ATTEND"),
            action_type="ATTEND",
            parameters={"target": perception.source or "field", "synthetic": True},
            target=perception.source or "field",
            rationale="Synthetic fixture present; attend only — not physical evidence.",
            confidence=0.70,
            originating_observation=perception.observation_id,
            agent_id=identity.agent_id,
            capability=ACTION_CAPABILITY.get("ATTEND", "observe.field"),
        )

    # Unchanged returning body: do not re-attend the same data
    if is_shared and is_returning and not meas_changed and not is_new_body:
        return ActionProposal(
            proposal_id=_proposal_id(perception.observation_id, "WAIT"),
            action_type="WAIT",
            parameters={"body_id": perception.measurement.get("body_id")},
            target=perception.source or "field",
            rationale="Returning body with unchanged measurements; WAIT.",
            confidence=0.85,
            originating_observation=perception.observation_id,
            agent_id=identity.agent_id,
            capability=ACTION_CAPABILITY["WAIT"],
        )

    last_action = str(memory.get("last_action") or "")
    last_energy = memory.get("last_energy")
    try:
        last_energy_f = float(last_energy) if last_energy is not None else None
    except (TypeError, ValueError):
        last_energy_f = None

    action = "WAIT"
    params: dict[str, Any] = {}
    target = "field"
    rationale = "Nothing in the perception view warrants motion."
    confidence = 0.60

    if last_action == "PROBE" and last_energy_f is not None:
        if energy is not None and energy + 1e-9 >= last_energy_f:
            action = "PROBE"
            params = {"magnitude": 0.45}
            if perception.location:
                params["x"] = perception.location.get("x", 8)
                params["z"] = perception.location.get("z", 8)
            target = "field"
            rationale = (
                f"Prior probe held; energy {last_energy_f:.4f} → {energy_val:.4f}"
            )
            confidence = 0.82
        else:
            action = "ATTEND"
            params = {"target": "field"}
            target = "field"
            rationale = "Probe did not hold energy; attend before acting again."
            confidence = 0.80
    elif last_action == "ATTEND" and energy_val >= ENERGY_CONTACT:
        action = "PROBE"
        params = {"magnitude": 0.45}
        if perception.location:
            params["x"] = perception.location.get("x", 8)
            params["z"] = perception.location.get("z", 8)
        target = "field"
        rationale = "Attended the lake; curiosity authorizes a bounded probe."
        confidence = 0.78
    elif last_action == "" and energy_val >= ENERGY_CONTACT:
        action = "PROBE"
        params = {"magnitude": 0.45}
        if perception.location:
            params["x"] = perception.location.get("x", 8)
            params["z"] = perception.location.get("z", 8)
        target = "field"
        rationale = "First contact with a live measurement; bounded probe."
        confidence = 0.76
    elif energy_val >= ENERGY_ATTEND or perception.channels:
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
