"""E-ink adapter. Renders admitted snapshots. Never admits."""

from duck_gate.eink.display import FileDisplay, MemoryDisplay
from duck_gate.eink.sink import EInkSink
from duck_gate.eink.snapshot import GateDisplaySnapshot
from duck_gate.eink.worker import EInkWorker

__all__ = [
    "EInkSink",
    "EInkWorker",
    "FileDisplay",
    "GateDisplaySnapshot",
    "MemoryDisplay",
]
