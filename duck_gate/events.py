"""Canonical GateEvent. The display consumes this. It does not invent it."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

PROTOCOL = "duck-gate/v0.1"
GATE_TICK = "gate_tick"
DISPLAY_ACK = "display_ack"


@dataclass(frozen=True)
class GateEvent:
    sequence: int
    status: str
    state_hash: str
    protocol: str = PROTOCOL
    type: str = GATE_TICK
    observation: str = ""
    delta: str = ""
    delta_count: int = 0
    reason: str = ""
    last_ok_sequence: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DisplayAck:
    """Physical witness. Observation, not approval."""

    sequence: int
    state_hash: str
    display_id: str = "EINK-01"
    type: str = DISPLAY_ACK

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def gate_event(
    *,
    sequence: int,
    status: str,
    state_hash: str,
    observation: str = "",
    delta: str = "",
    delta_count: int = 0,
    reason: str = "",
    last_ok_sequence: int | None = None,
) -> GateEvent:
    return GateEvent(
        sequence=int(sequence),
        status=str(status or "REJECTED"),
        state_hash=_short_hash(state_hash),
        observation=str(observation or ""),
        delta=str(delta or ""),
        delta_count=int(delta_count),
        reason=str(reason or ""),
        last_ok_sequence=last_ok_sequence,
    )


def from_committed(
    *,
    sequence: int,
    tick_hash: str,
    accepted: bool,
    action: str = "",
    delta_count: int = 0,
    reason: str = "",
    observation_id: str = "",
    last_ok_sequence: int | None = None,
) -> GateEvent:
    status = "ADMITTED" if accepted else "HALTED"
    return gate_event(
        sequence=sequence,
        status=status,
        state_hash=tick_hash,
        observation=observation_id,
        delta=action,
        delta_count=delta_count,
        reason=reason,
        last_ok_sequence=last_ok_sequence if not accepted else sequence,
    )


def parse_event(raw: Any) -> GateEvent | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("type") not in (None, GATE_TICK):
        return None
    if raw.get("protocol") not in (None, PROTOCOL, "DG/v0.1"):
        return None
    try:
        sequence = int(raw["sequence"])
        status = str(raw["status"])
        state_hash = _short_hash(str(raw.get("state_hash") or raw.get("hash") or ""))
    except (KeyError, TypeError, ValueError):
        return None
    if not status or sequence < 0:
        return None
    last_ok = raw.get("last_ok_sequence")
    try:
        last_ok_i = None if last_ok is None else int(last_ok)
    except (TypeError, ValueError):
        last_ok_i = None
    try:
        delta_count = int(raw.get("delta_count") or 0)
    except (TypeError, ValueError):
        delta_count = 0
    return gate_event(
        sequence=sequence,
        status=status,
        state_hash=state_hash,
        observation=str(raw.get("observation") or ""),
        delta=str(raw.get("delta") or ""),
        delta_count=delta_count,
        reason=str(raw.get("reason") or ""),
        last_ok_sequence=last_ok_i,
    )


def _short_hash(value: str) -> str:
    text = "".join(ch for ch in str(value) if ch.isalnum())
    if not text:
        return "00000000"
    return text[:8].lower()
