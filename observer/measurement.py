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
  THRONE_HEAD_WINDOW_S  online head temporal span  (default 12)

Derived:
  FINE_LEN    = ceil(SAMPLE_HZ * WINDOW_S)       # full-fidelity ring
  DISPLAY_LEN = ceil(SAMPLE_HZ * DISPLAY_S)
  HEAD_LEN    = ceil(SAMPLE_HZ * HEAD_WINDOW_S)  # learner sees real seconds

High-tune value preserved: never a placeholder integer cap.
Obscure limit fixed: head no longer stuck at magic window=12 samples
while the rest of the stack thinks in 90s fine windows.
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


SAMPLE_HZ: float = _env_float("THRONE_SAMPLE_HZ", 8.0)
WINDOW_S: float = _env_float("THRONE_WINDOW_S", 90.0)
DISPLAY_S: float = _env_float("THRONE_DISPLAY_S", 150.0)
HEAD_WINDOW_S: float = _env_float("THRONE_HEAD_WINDOW_S", 12.0)
SPARK_CELLS: int = _env_int("THRONE_SPARK_CELLS", 64)

FINE_LEN: int = max(128, int(math.ceil(SAMPLE_HZ * WINDOW_S)))
DISPLAY_LEN: int = max(FINE_LEN, int(math.ceil(SAMPLE_HZ * DISPLAY_S)))
HEAD_LEN: int = max(24, min(FINE_LEN, int(math.ceil(SAMPLE_HZ * HEAD_WINDOW_S))))

POLICY_TAIL_LINES: int = FINE_LEN

FIELD_HEADS: int = _env_int("THRONE_FIELD_HEADS", 8)
FIELD_SUBCARRIERS: int = _env_int("THRONE_FIELD_SC", 32)

HEAD_STATE_PATH_DEFAULT = "/tmp/metafield/head_state.json"
AURORA_BASE_COOLDOWN_S: float = _env_float("THRONE_AURORA_COOLDOWN", 5.0)
AURORA_DECIDE_INTERVAL_S: float = _env_float("THRONE_AURORA_INTERVAL", 1.25)


def decimate(values: list[float], cells: int = SPARK_CELLS) -> list[float]:
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
        f"spark={SPARK_CELLS}  display={DISPLAY_LEN}  "
        f"head={HEAD_LEN} ({HEAD_WINDOW_S:g}s)  heads={FIELD_HEADS}"
    )
