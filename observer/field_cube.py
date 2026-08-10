"""
Field cube ensemble — measurement-grade multi-body energy lattice.

Pure Python (no numpy) so observer.startup works with the base venv.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from .measurement import FINE_LEN
except ImportError:
    from measurement import FINE_LEN  # type: ignore


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def _zeros_3() -> list[list[list[float]]]:
    return [[[0.0 for _ in range(3)] for _ in range(3)] for _ in range(3)]


def _max_heat_w(w: list[list[list[float]]]) -> float:
    m = 0.0
    for z in range(3):
        for y in range(3):
            for x in range(3):
                v = w[z][y][x]
                if v > m:
                    m = v
    return m


def _argmax_w(w: list[list[list[float]]]) -> tuple[tuple[int, int, int], float]:
    best = (0, 0, 0)
    m = -1.0
    for z in range(3):
        for y in range(3):
            for x in range(3):
                v = w[z][y][x]
                if v > m:
                    m = v
                    best = (z, y, x)
    return best, max(0.0, m)


@dataclass
class FieldCube:
    """One body's soft 3×3×3 energy lattice."""

    body_id: str
    weights: list[list[list[float]]] = field(default_factory=_zeros_3)
    last_touch: float = 0.0
    deposits: int = 0

    def encode(self, text_or_key: str, strength: float = 0.13) -> None:
        h = hashlib.sha256(text_or_key.encode("utf-8")).digest()
        for i in range(min(9, len(h))):
            idx = h[i] % 27
            z, y, x = idx // 9, (idx // 3) % 3, idx % 3
            self.weights[z][y][x] = min(1.0, self.weights[z][y][x] + strength)
        self.last_touch = time.time()
        self.deposits += 1

    def encode_regions(self, regions: dict[str, float], strength: float = 0.2) -> None:
        if not regions:
            return
        for name in sorted(regions.keys()):
            val = _clip01(float(regions[name]))
            if val <= 0:
                continue
            idx = (hash(name) & 0x7FFFFFFF) % 27
            z, y, x = idx // 9, (idx // 3) % 3, idx % 3
            self.weights[z][y][x] = min(
                1.0, self.weights[z][y][x] + strength * val
            )
        self.last_touch = time.time()
        self.deposits += 1

    def decay(self, rate: float = 0.995) -> None:
        for z in range(3):
            for y in range(3):
                for x in range(3):
                    self.weights[z][y][x] *= rate

    def hot(self) -> tuple[tuple[int, int, int], float]:
        return _argmax_w(self.weights)

    def max_heat(self) -> float:
        return _max_heat_w(self.weights)


@dataclass
class FieldCubeEnsemble:
    """Ordered multi-body cubes with path propagation (snake-aware)."""

    cubes: dict[str, FieldCube] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    path_cycle: int = 0
    pressure_hist: list[float] = field(default_factory=list)

    def ensure(self, body_id: str) -> FieldCube:
        if body_id not in self.cubes:
            self.cubes[body_id] = FieldCube(body_id=body_id)
            self.order.append(body_id)
        return self.cubes[body_id]

    def observe(self, body_id: str, regions: dict[str, float]) -> None:
        cube = self.ensure(body_id)
        cube.encode_regions(regions)
        self._propagate(start=body_id, strength=1.0)
        self.path_cycle = (self.path_cycle + 1) % max(1, len(self.order))

    def _propagate(self, start: str, strength: float = 1.0) -> None:
        if len(self.order) < 2:
            return
        try:
            start_idx = self.order.index(start)
        except ValueError:
            start_idx = 0
        n = len(self.order)
        scale = 0.12 * strength
        for step in range(n - 1):
            a = self.cubes[self.order[(start_idx + step) % n]]
            b = self.cubes[self.order[(start_idx + step + 1) % n]]
            for z in range(3):
                for y in range(3):
                    for x in range(3):
                        transfer = a.weights[z][y][x] * scale
                        b.weights[z][y][x] = min(
                            1.0, b.weights[z][y][x] + transfer * 0.5
                        )
                        a.weights[z][y][x] *= 0.97

    def decay_all(self, rate: float = 0.995) -> None:
        for c in self.cubes.values():
            c.decay(rate)

    def field_pressure(self) -> float:
        if not self.cubes:
            return 0.0
        heats = [c.max_heat() for c in self.cubes.values()]
        total = sum(heats)
        peak = max(heats)
        active = sum(1 for h in heats if h > 0.15)
        score = (
            (total / max(1, len(heats))) * 0.45
            + peak * 0.40
            + min(1.0, active / 4.0) * 0.15
        )
        p = _clip01(score)
        self.pressure_hist.append(p)
        if len(self.pressure_hist) > FINE_LEN:
            self.pressure_hist = self.pressure_hist[-FINE_LEN:]
        return p

    def snapshot(self) -> dict[str, Any]:
        bodies: dict[str, Any] = {}
        for bid, c in self.cubes.items():
            pos, heat = c.hot()
            bodies[bid] = {
                "heat": round(heat, 4),
                "hot_cell": pos,
                "deposits": c.deposits,
                "age_s": round(time.time() - c.last_touch, 2) if c.last_touch else None,
            }
        return {
            "pressure": round(self.field_pressure(), 4),
            "bodies": bodies,
            "path_cycle": self.path_cycle,
            "n_bodies": len(self.cubes),
        }


def density_impinge(
    grid: list[list[float]],
    x: float,
    y: float,
    strength: float = 1.0,
    sigma: float = 2.5,
) -> None:
    """Gaussian deposit onto a 2D density grid (coords 0..1). Pure Python."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    if h == 0 or w == 0:
        return
    cx = int(max(0.0, min(1.0, x)) * (w - 1))
    cy = int(max(0.0, min(1.0, y)) * (h - 1))
    rad = max(1, int(math.ceil(sigma * 3)))
    for dy in range(-rad, rad + 1):
        for dx in range(-rad, rad + 1):
            yy, xx = cy + dy, cx + dx
            if 0 <= yy < h and 0 <= xx < w:
                g = math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))
                grid[yy][xx] = min(1.0, grid[yy][xx] + strength * g)
