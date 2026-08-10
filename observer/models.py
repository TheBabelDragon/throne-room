"""Shared data models for Throne Room."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Battleship-style intensity cells (time → right, strength → fill)
# Absolute 0..1 scale so regions are comparable.
_BATTLE_CELLS = "·░▒▓█"  # empty → light → mid → heavy → solid


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
    """Rolling measurement history for battleship-style time sparks."""

    values: list[float] = field(default_factory=list)
    max_len: int = 32

    def push(self, value: float) -> None:
        self.values.append(max(0.0, min(1.0, float(value))))
        if len(self.values) > self.max_len:
            self.values.pop(0)

    def cells(self) -> list[tuple[str, float]]:
        """Return (glyph, intensity) pairs for each time step."""
        if not self.values:
            return []
        out: list[tuple[str, float]] = []
        n = len(_BATTLE_CELLS) - 1
        for v in self.values:
            idx = int(round(v * n))
            out.append((_BATTLE_CELLS[idx], v))
        return out

    def sparkline(self) -> str:
        """Plain-string fallback (no colour)."""
        return "".join(g for g, _ in self.cells())


@dataclass
class BodyState:
    last_seen: float = 0.0
    regions: dict[str, Observation] = field(default_factory=dict)
    history: dict[str, RegionHistory] = field(default_factory=dict)
    packet_count: int = 0
