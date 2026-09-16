"""Duck Gate observer surface + additive candidate selection.

Admission stays in qwuack.gate + OperatorAbi.
This package emits and materializes committed GateEvents.
It does not admit, clamp, budget, or write FieldTick.

Additive selection (candidates / scoring / selector) is pure:
returns CandidateExcitation recommendations only.
It never produces ActionProposal and never mutates the world.
"""

from duck_gate.bus import GateBus
from duck_gate.events import PROTOCOL, DisplayAck, GateEvent

# Additive pure selection surface (no authority)
from duck_gate.candidates import CandidateExcitation
from duck_gate.scoring import DEFAULT_WEIGHTS, score
from duck_gate.selector import Mode, select

__all__ = [
    "PROTOCOL",
    "GateBus",
    "GateEvent",
    "DisplayAck",
    "CandidateExcitation",
    "DEFAULT_WEIGHTS",
    "score",
    "Mode",
    "select",
]
__version__ = "0.1.0"
