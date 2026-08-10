"""Shared data models for Throne Room."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Observation:
    timestamp: str
    body_id: str
    region: str
    value: float
    confidence: float = 1.0
    meta: dict[str, Any] | None = None


@dataclass
class RegionHistory:
    """Keep a short rolling history for sparklines."""
    values: list[float] = field(default_factory=list)
    max_len: int = 24

    def push(self, value: float) -> None:
        self.values.append(value)
        if len(self.values) > self.max_len:
            self.values.pop(0)

    def sparkline(self) -> str:
        if not self.values:
            return ""
        blocks = " ▁▂▃▄▅▆▇█"
        lo = min(self.values)
        hi = max(self.values)
        span = hi - lo if hi > lo else 1.0
        chars = []
        for v in self.values:
            idx = int((v - lo) / span * (len(blocks) - 1))
            chars.append(blocks[idx])
        return "".join(chars)


@dataclass
class BodyState:
    last_seen: float = 0.0
    regions: dict[str, Observation] = field(default_factory=dict)
    history: dict[str, RegionHistory] = field(default_factory=dict)
    packet_count: int = 0
