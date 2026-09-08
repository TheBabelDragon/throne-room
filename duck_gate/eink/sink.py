"""EInkSink. Receives committed GateEvents. Never generates state."""

from __future__ import annotations

from duck_gate.eink.display import MemoryDisplay
from duck_gate.eink.snapshot import GateDisplaySnapshot
from duck_gate.events import DisplayAck, GateEvent, parse_event


class EInkSink:
    def __init__(self, display: MemoryDisplay | None = None, display_id: str = "EINK-01") -> None:
        self.display = display or MemoryDisplay()
        self.display_id = display_id
        self.last_sequence: int | None = None
        self.last_snapshot: GateDisplaySnapshot | None = None
        self.last_committed: GateDisplaySnapshot | None = None
        self.dropped = 0

    def accept(self, gate_event: GateEvent | dict) -> bool:
        event = gate_event if isinstance(gate_event, GateEvent) else parse_event(gate_event)
        if event is None:
            self.dropped += 1
            return False
        if self.last_sequence is not None and event.sequence == self.last_sequence:
            return False
        snapshot = GateDisplaySnapshot.from_event(event)
        if snapshot is None:
            self.dropped += 1
            return False
        self.display.render(snapshot)
        self.display.refresh()
        self.last_sequence = snapshot.sequence
        self.last_snapshot = snapshot
        if snapshot.committed:
            self.last_committed = snapshot
        return True

    def acknowledge(self) -> DisplayAck | None:
        """Witness the last rendered committed state. Does not approve a proposal."""
        snap = self.last_committed or self.last_snapshot
        if snap is None:
            return None
        return DisplayAck(
            sequence=snap.sequence,
            state_hash=snap.state_hash,
            display_id=self.display_id,
        )
