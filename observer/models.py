"""Shared data models for Throne Room."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .measurement import FINE_LEN, SPARK_CELLS, decimate

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
    """Fine measurement ring + decimated spark for display.

    Stores full-fidelity samples (FINE_LEN ≈ sample_hz × window_s).
    Sparklines decimate to SPARK_CELLS — the ring is never the display width.
    """

    values: list[float] = field(default_factory=list)
    max_len: int = FINE_LEN

    def push(self, value: float) -> None:
        self.values.append(max(0.0, min(1.0, float(value))))
        if len(self.values) > self.max_len:
            # drop oldest in bulk if badly behind (file replay)
            overflow = len(self.values) - self.max_len
            if overflow > 1:
                del self.values[0:overflow]
            else:
                self.values.pop(0)

    def display_values(self) -> list[float]:
        return decimate(self.values, SPARK_CELLS)

    def cells(self) -> list[tuple[str, float]]:
        """Spark cells from decimated fine history."""
        series = self.display_values()
        if not series:
            return []
        out: list[tuple[str, float]] = []
        n = len(_BATTLE_CELLS) - 1
        for v in series:
            idx = int(round(v * n))
            out.append((_BATTLE_CELLS[idx], v))
        return out

    def sparkline(self) -> str:
        return "".join(g for g, _ in self.cells())


@dataclass
class BodyState:
    last_seen: float = 0.0
    regions: dict[str, Observation] = field(default_factory=dict)
    history: dict[str, RegionHistory] = field(default_factory=dict)
    packet_count: int = 0
