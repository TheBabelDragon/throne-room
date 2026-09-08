"""Duck Gate observer surface.

Admission stays in qwuack.gate + OperatorAbi.
This package emits and materializes committed GateEvents.
It does not admit, clamp, budget, or write FieldTick.
"""

from duck_gate.bus import GateBus
from duck_gate.events import PROTOCOL, DisplayAck, GateEvent

__all__ = ["PROTOCOL", "GateBus", "GateEvent", "DisplayAck"]
__version__ = "0.1.0"
