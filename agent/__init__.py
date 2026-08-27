"""Agent-in-a-world loop for Throne Room.

Does not own live CSI ingest, torch HUD, or Aurora dispatch.
Those stay in observer/, visualization/, aurora/.

This package is the missing spine:

    PerceptionEvent → SelfState → ActionProposal → Operator ABI → FieldDelta → FieldTick
"""

__version__ = "0.7.3"
