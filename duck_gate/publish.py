"""Build a GateEvent from a committed world turn. Call only after FieldTick."""

from __future__ import annotations

from typing import Any

from duck_gate.bus import GateBus
from duck_gate.events import GateEvent, from_committed


def event_after_commit(
    *,
    sequence: int,
    tick_hash: str,
    decision: Any | None = None,
    observation_id: str = "",
    last_ok_sequence: int | None = None,
) -> GateEvent:
    accepted = True
    action = ""
    delta_count = 0
    reason = ""
    if decision is not None:
        accepted = bool(getattr(decision, "accepted", False))
        action = str(getattr(getattr(decision, "proposal", None), "action_type", "") or "")
        deltas = getattr(decision, "deltas", None) or []
        delta_count = len(deltas)
        reason = str(getattr(decision, "reason", "") or "")
        status = str(getattr(decision, "status", "") or "")
        if not accepted and status and status != "REJECTED":
            reason = reason or status
    return from_committed(
        sequence=sequence,
        tick_hash=tick_hash,
        accepted=accepted,
        action=action,
        delta_count=delta_count,
        reason=reason,
        observation_id=observation_id,
        last_ok_sequence=last_ok_sequence,
    )


def publish_after_commit(bus: GateBus, event: GateEvent) -> GateEvent:
    bus.publish(event)
    return event
