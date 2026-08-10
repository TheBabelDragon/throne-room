"""Rich continuous body energy field for torch display.

Multi-scale soft Gaussians, temporal fade, mild inter-body bloom,
and a gentle pulse so the map feels alive at 25–40 Hz UI rates.
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np


def soft_blob(
    grid: np.ndarray,
    cx: float,
    cy: float,
    strength: float,
    sigma: float,
) -> None:
    """Isotropic Gaussian deposit in normalized [0, 1] coords."""
    h, w = grid.shape
    xs = (np.arange(w, dtype=np.float32) + 0.5) / w
    ys = (np.arange(h, dtype=np.float32) + 0.5) / h
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    g = np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2.0 * sigma * sigma))
    grid += strength * g


def body_energy_field(
    bodies: dict[str, Any],
    anchors: dict[str, tuple[float, float]],
    size: int = 48,
    prev: np.ndarray | None = None,
    blend: float = 0.22,
) -> np.ndarray:
    """
    Build a display-rich energy density map.

    - Multi-scale cores (tight peak + mid + soft halo)
    - Age-based fade
    - Mild temporal persistence via prev grid
    - Gentle time pulse keyed to body id so the field breathes
    - Cheap neighbour bloom for continuity
    """
    grid = np.zeros((size, size), dtype=np.float32)
    if not bodies:
        if prev is not None and prev.shape == grid.shape:
            return prev * 0.92
        return grid

    now = time.time()
    for bid, st in bodies.items():
        age = now - float(st.get("last", now))
        if age < 1.2:
            fade = 1.0
        elif age < 4.0:
            fade = 0.70
        elif age < 10.0:
            fade = 0.32
        elif age < 20.0:
            fade = 0.10
        else:
            fade = 0.03

        regs = st.get("regions") or {}
        energy = float(regs.get("csi_energy", regs.get("csi_mean", 0.0)))
        spread = float(regs.get("csi_spread", 0.15))
        peak = float(regs.get("csi_peak", energy))
        strength = max(energy, peak * 0.88) * fade
        if strength < 0.015:
            continue

        if bid not in anchors:
            h = abs(hash(bid))
            anchors[bid] = (
                0.11 + (h % 1000) / 1000.0 * 0.78,
                0.11 + ((h // 1000) % 1000) / 1000.0 * 0.78,
            )
        cx, cy = anchors[bid]

        # slight breathing so static anchors still feel dynamic
        phase = (hash(bid) % 1000) / 1000.0 * math.tau
        pulse = 1.0 + 0.11 * math.sin(now * 3.4 + phase)
        strength *= pulse

        sigma = 0.042 + 0.13 * min(1.0, spread + 0.12)
        # multi-scale deposit
        soft_blob(grid, cx, cy, strength * 1.00, sigma)          # main
        soft_blob(grid, cx, cy, strength * 0.55, sigma * 0.42)   # core
        soft_blob(grid, cx, cy, strength * 0.22, sigma * 1.55)   # halo

    # cheap isotropic bloom (keeps energy continuous between nearby bodies)
    grid = (
        grid
        + np.roll(grid, 1, 0) * 0.14
        + np.roll(grid, -1, 0) * 0.14
        + np.roll(grid, 1, 1) * 0.14
        + np.roll(grid, -1, 1) * 0.14
    ) / 1.56

    # temporal persistence — trails / afterglow
    if prev is not None and prev.shape == grid.shape:
        grid = (1.0 - blend) * grid + blend * prev

    mx = float(grid.max())
    if mx > 1.0:
        grid /= mx
    elif mx < 1e-6:
        pass
    else:
        # soft contrast lift so weak fields still read
        grid = np.clip(grid * (0.85 / max(mx, 0.25)), 0.0, 1.0)

    return grid
