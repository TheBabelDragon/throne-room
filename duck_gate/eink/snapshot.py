"""Tiny projection of a GateEvent. The renderer never sees Duck Gate internals."""

from __future__ import annotations

from dataclasses import dataclass

from duck_gate.events import PROTOCOL, GateEvent, parse_event

DISPLAY_PROTOCOL = "DG/v0.1"


@dataclass(frozen=True)
class GateDisplaySnapshot:
    sequence: int
    status: str
    state_hash: str
    delta_count: int
    protocol: str = DISPLAY_PROTOCOL
    reason: str = ""
    last_ok_sequence: int | None = None
    observation: str = ""
    delta: str = ""

    @classmethod
    def from_event(cls, event: GateEvent | dict) -> GateDisplaySnapshot | None:
        parsed = event if isinstance(event, GateEvent) else parse_event(event)
        if parsed is None:
            return None
        last_ok = parsed.last_ok_sequence
        if parsed.status == "ADMITTED" and last_ok is None:
            last_ok = parsed.sequence
        return cls(
            sequence=parsed.sequence,
            status=parsed.status,
            state_hash=parsed.state_hash,
            delta_count=parsed.delta_count,
            protocol=DISPLAY_PROTOCOL if parsed.protocol == PROTOCOL else DISPLAY_PROTOCOL,
            reason=parsed.reason,
            last_ok_sequence=last_ok,
            observation=parsed.observation,
            delta=parsed.delta,
        )

    @property
    def committed(self) -> bool:
        return self.status == "ADMITTED"
