"""Rich continuous body energy field for torch display."""

from __future__ import annotations

import time
from typing import Any

import numpy as np


def soft_blob(grid: np.ndarray, cx: float, cy: float, strength: float, sigma: float) -> None:
    h, w = grid.shape
    xs = (np.arange(w) + 0.5) / w
    ys = (np.arange(h) + 0.5) / h
    X, Y = np.meshgrid(xs, ys)
    g = np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sigma * sigma))
    grid += strength * g


def body_energy_field(
    bodies: dict[str, Any],
    anchors: dict[str, tuple[float, float]],
    size: int = 48,
) -> np.ndarray:
    grid = np.zeros((size, size), dtype=np.float32)
    if not bodies:
        return grid
    now = time.time()
    for bid, st in bodies.items():
        age = now - st["last"]
        fade = 1.0 if age < 1.5 else (0.55 if age < 5 else (0.2 if age < 12 else 0.06))
        regs = st["regions"]
        energy = float(regs.get("csi_energy", regs.get("csi_mean", 0.0)))
        spread = float(regs.get("csi_spread", 0.15))
        peak = float(regs.get("csi_peak", energy))
        strength = max(energy, peak * 0.85) * fade
        if strength < 0.02:
            continue
        if bid not in anchors:
            h = abs(hash(bid))
            anchors[bid] = (
                0.12 + (h % 1000) / 1000.0 * 0.76,
                0.12 + ((h // 1000) % 1000) / 1000.0 * 0.76,
            )
        cx, cy = anchors[bid]
        sigma = 0.05 + 0.12 * min(1.0, spread + 0.15)
        soft_blob(grid, cx, cy, strength, sigma)
        soft_blob(grid, cx, cy, strength * 0.45, sigma * 0.45)
    grid = (
        grid
        + np.roll(grid, 1, 0) * 0.15
        + np.roll(grid, -1, 0) * 0.15
        + np.roll(grid, 1, 1) * 0.15
        + np.roll(grid, -1, 1) * 0.15
    ) / 1.6
    mx = float(grid.max())
    if mx > 1.0:
        grid /= mx
    return grid
