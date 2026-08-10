"""
Fine measurement standard for Throne Room histories.

Pre-tuned defaults (not placeholders):

  Nominal CSI body rate on the snake path is ~4–10 Hz.
  We lock the analysis window to wall-clock seconds, then derive
  sample counts so the ring always covers the same physical duration
  regardless of burst rate.

  THRONE_SAMPLE_HZ      nominal body rate          (default 8)
  THRONE_WINDOW_S       fine analysis window (s)   (default 90)
  THRONE_SPARK_CELLS    TUI spark display cells     (default 64)
  THRONE_DISPLAY_S      torch-display history (s)   (default 150)

Derived:
  FINE_LEN    = ceil(SAMPLE_HZ * WINDOW_S)     # full-fidelity ring
  DISPLAY_LEN = ceil(SAMPLE_HZ * DISPLAY_S)

Multi-head field pooling (see multi_head_field.py) uses the same
window so head residuals and sparklines stay time-aligned.
"""

from __future__ import annotations

import math
import os


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return max(1, int(round(_env_float(name, float(default)))))


# Pre-tuned for live CSI swarm (CYD × bridges × host)
SAMPLE_HZ: float = _env_float("THRONE_SAMPLE_HZ", 8.0)
WINDOW_S: float = _env_float("THRONE_WINDOW_S", 90.0)
DISPLAY_S: float = _env_float("THRONE_DISPLAY_S", 150.0)
SPARK_CELLS: int = _env_int("THRONE_SPARK_CELLS", 64)

# Full-fidelity rings — never a small placeholder
FINE_LEN: int = max(128, int(math.ceil(SAMPLE_HZ * WINDOW_S)))
DISPLAY_LEN: int = max(FINE_LEN, int(math.ceil(SAMPLE_HZ * DISPLAY_S)))

# Policy / multi-head tail: one full fine window
POLICY_TAIL_LINES: int = FINE_LEN

# Multi-head field geometry (substance, not LLM toy dims)
FIELD_HEADS: int = _env_int("THRONE_FIELD_HEADS", 8)
FIELD_SUBCARRIERS: int = _env_int("THRONE_FIELD_SC", 32)


def decimate(values: list[float], cells: int = SPARK_CELLS) -> list[float]:
    """Downsample a fine ring to a display-width series (mean bins)."""
    if not values:
        return []
    if len(values) <= cells:
        return list(values)
    n = len(values)
    out: list[float] = []
    for i in range(cells):
        a = int(i * n / cells)
        b = int((i + 1) * n / cells)
        chunk = values[a:b] or [values[min(a, n - 1)]]
        out.append(sum(chunk) / len(chunk))
    return out


def standard_banner() -> str:
    return (
        f"measurement: {SAMPLE_HZ:g} Hz × {WINDOW_S:g}s = {FINE_LEN} samples  "
        f"spark={SPARK_CELLS}  display={DISPLAY_LEN}  heads={FIELD_HEADS}"
    )
