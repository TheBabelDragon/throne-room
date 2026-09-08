"""Qwuack — embodied identity/runtime inhabiting the Throne Room loop.

The lake already exists. Qwuack does not build it. Qwuack lives in it.

Qwuack proposes. Duck Gate / ABI admits. FieldTick commits. World responds.
"""

from qwuack.gate import GATE_POLICY, GATE_VERSION, AdmissionResult, GateConfig
from qwuack.identity import QWUACK, QwuackIdentity
from qwuack.policy import QwuackPerception, decide, perception_view
from qwuack.state import QwuackState

__all__ = [
    "QWUACK",
    "QwuackIdentity",
    "QwuackPerception",
    "QwuackState",
    "GateConfig",
    "AdmissionResult",
    "GATE_POLICY",
    "GATE_VERSION",
    "decide",
    "perception_view",
]

__version__ = "0.1.0"
