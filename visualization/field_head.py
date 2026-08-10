"""
Throne field head — prediction + residual + surprise.

Two modes:
  1. OnlineFieldHead  — pure numpy, always available, multi-head aware
  2. ThroneFieldHead  — optional torch checkpoint (same contract as before)

Factory open_field_head() prefers a checkpoint when present, otherwise
online. Torch display and Aurora treat both behind the same interface:

  head.update(feats) -> {pred, actual, abs_residual, surprise, ready, ...}
  head.ready, head.surprise, head.last_pred, head.last_abs_residual
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Sequence, Tuple

import numpy as np

FEATURE_NAMES = [
    "csi_mean",
    "csi_energy",
    "csi_spread",
    "csi_peak",
    "rssi",
    "n_bodies",
    "mean_conf",
    "packet_rate_n",
]

# Extended multi-head features (appended when available)
HEAD_FEATURE_NAMES = [
    "head_fused_mean",
    "head_fused_energy",
    "head_fused_spread",
    "head_entropy",
    "head_dominant",
]


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Online adaptive head (default — no torch, no checkpoint)
# ---------------------------------------------------------------------------

class OnlineFieldHead:
    """
    Multi-head aware online predictor.

    Maintains a short temporal window of fused features and predicts the
    next csi_mean (and energy) via EMA + linear trend. Residual and
    surprise are measurement-grade, not a toy random walk.

    Multi-head signal:
      - uses head_fused_* + entropy when present in the feature vector
      - surprise threshold softens when routing entropy is high (uncertain band)
      - hardens when one dominant head owns the spectrum
    """

    def __init__(
        self,
        *,
        window: int = 12,
        threshold: float = 0.28,
        ema_alpha: float = 0.22,
    ) -> None:
        self.window = max(4, int(window))
        self.threshold = float(threshold)
        self.ema_alpha = float(ema_alpha)
        self.history: Deque[List[float]] = deque(maxlen=self.window)
        self._ema_mean = 0.0
        self._ema_energy = 0.0
        self._trend = 0.0
        self.last_pred = 0.0
        self.last_actual = 0.0
        self.last_abs_residual = 0.0
        self.surprise = False
        self.ready = False
        self.n_scored = 0
        self.mode = "online"
        print(
            f"[throne-head] online multi-head  window={self.window}  "
            f"thr={self.threshold:.2f}",
            flush=True,
        )

    def maybe_reload(self) -> None:
        return

    def update(self, feats: Sequence[float]) -> Dict[str, float]:
        base = [_clip01(float(x)) for x in list(feats)[: len(FEATURE_NAMES)]]
        while len(base) < len(FEATURE_NAMES):
            base.append(0.0)
        # optional multi-head tail
        extra = list(feats)[len(FEATURE_NAMES) : len(FEATURE_NAMES) + len(HEAD_FEATURE_NAMES)]
        while len(extra) < len(HEAD_FEATURE_NAMES):
            extra.append(0.0)
        extra = [_clip01(float(x)) for x in extra]

        mean = base[0]
        energy = base[1]
        spread = base[2]
        head_entropy = extra[3]
        head_dom = extra[4]

        if not self.history:
            self._ema_mean = mean
            self._ema_energy = energy

        # predictive step before observing (one-step-ahead)
        pred = _clip01(
            self._ema_mean * 0.70
            + self._ema_energy * 0.15
            + self._trend * 0.12
            + spread * 0.03
        )
        # multi-head bias: high entropy → trust fused less, lean on ema
        if head_entropy > 0.55:
            pred = _clip01(0.65 * pred + 0.35 * self._ema_mean)
        elif head_dom > 0.55:
            # concentrated band — lean harder on recent energy
            pred = _clip01(0.55 * pred + 0.45 * energy)

        actual = mean
        abs_r = abs(actual - pred)

        # adaptive threshold: tighter when spectrum is concentrated
        thr = self.threshold
        if head_entropy < 0.25:
            thr *= 0.85
        elif head_entropy > 0.65:
            thr *= 1.15

        self.history.append(base + extra)
        # update state after score
        prev_ema = self._ema_mean
        self._ema_mean = (1.0 - self.ema_alpha) * self._ema_mean + self.ema_alpha * mean
        self._ema_energy = (1.0 - self.ema_alpha) * self._ema_energy + self.ema_alpha * energy
        self._trend = 0.8 * self._trend + 0.2 * (self._ema_mean - prev_ema)

        self.last_pred = pred
        self.last_actual = actual
        self.last_abs_residual = abs_r
        self.surprise = abs_r >= thr and self.n_scored >= self.window
        self.ready = len(self.history) >= min(6, self.window)
        self.n_scored += 1

        return {
            "pred": pred,
            "actual": actual,
            "abs_residual": abs_r,
            "surprise": 1.0 if self.surprise else 0.0,
            "ready": 1.0 if self.ready else 0.0,
            "entropy": head_entropy,
            "dominant": head_dom,
            "mode": 0.0,  # 0 = online
        }


# ---------------------------------------------------------------------------
# Torch checkpoint head (optional upgrade)
# ---------------------------------------------------------------------------

class _NumpyMLP:
    def __init__(self, weights: List[Tuple[np.ndarray, np.ndarray]]):
        self.layers = weights

    def __call__(self, x: np.ndarray) -> np.ndarray:
        h = x.astype(np.float64)
        for i, (W, b) in enumerate(self.layers):
            h = h @ W.T + b
            if i < len(self.layers) - 1:
                h = np.maximum(h, 0.0)
            else:
                h = 1.0 / (1.0 + np.exp(-np.clip(h, -40.0, 40.0)))
        return h.astype(np.float32)


def _load_torch_mlp(path: Path) -> Tuple[_NumpyMLP, int, int]:
    try:
        import torch
    except ImportError as e:
        raise ImportError(
            "torch required once to load the head checkpoint — pip install torch"
        ) from e

    ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
    sd = ckpt["state_dict"]
    window = int(ckpt.get("window", 8))
    in_dim = int(ckpt.get("in_dim", window * len(FEATURE_NAMES)))
    layers = []
    for idx in (0, 2, 4):
        W = sd[f"net.{idx}.weight"].detach().cpu().numpy()
        b = sd[f"net.{idx}.bias"].detach().cpu().numpy()
        layers.append((W, b))
    return _NumpyMLP(layers), window, in_dim


class ThroneFieldHead:
    def __init__(self, model_path: str | Path, threshold: float = 0.30):
        self.path = Path(model_path)
        self.threshold = float(threshold)
        self.mlp, self.window, self.in_dim = _load_torch_mlp(self.path)
        self.history: Deque[List[float]] = deque(maxlen=self.window)
        self.last_pred = 0.0
        self.last_actual = 0.0
        self.last_abs_residual = 0.0
        self.surprise = False
        self.ready = False
        self.n_scored = 0
        self.mode = "torch"
        try:
            self._mtime = self.path.stat().st_mtime
        except OSError:
            self._mtime = 0.0
        print(
            f"[throne-head] torch checkpoint {self.path}  window={self.window}  "
            f"in_dim={self.in_dim}  thr={self.threshold:.2f}",
            flush=True,
        )

    def maybe_reload(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return
        if mtime <= self._mtime:
            return
        try:
            mlp, window, in_dim = _load_torch_mlp(self.path)
        except Exception as e:
            print(f"[throne-head] reload failed: {e}")
            return
        self.mlp, self.window, self.in_dim = mlp, window, in_dim
        self._mtime = mtime
        self.history = deque(maxlen=self.window)
        self.ready = False
        print(f"[throne-head] hot-reload {self.path}")

    def update(self, feats: Sequence[float]) -> Dict[str, float]:
        if self.n_scored and self.n_scored % 40 == 0:
            self.maybe_reload()
        feats_l = [_clip01(float(x)) for x in list(feats)[: len(FEATURE_NAMES)]]
        while len(feats_l) < len(FEATURE_NAMES):
            feats_l.append(0.0)

        if len(self.history) < self.window:
            self.history.append(feats_l)
            self.ready = False
            self.surprise = False
            return {
                "pred": 0.0,
                "actual": feats_l[0],
                "abs_residual": 0.0,
                "surprise": 0.0,
                "ready": 0.0,
            }

        x = np.array([v for row in self.history for v in row], dtype=np.float64)
        if x.shape[0] != self.in_dim:
            self.history.clear()
            self.history.append(feats_l)
            self.ready = False
            return {
                "pred": 0.0,
                "actual": feats_l[0],
                "abs_residual": 0.0,
                "surprise": 0.0,
                "ready": 0.0,
            }

        pred = float(self.mlp(x)[0])
        actual = float(feats_l[0])
        abs_r = abs(actual - pred)
        self.history.append(feats_l)
        self.last_pred = pred
        self.last_actual = actual
        self.last_abs_residual = abs_r
        self.surprise = abs_r >= self.threshold
        self.ready = True
        self.n_scored += 1
        return {
            "pred": pred,
            "actual": actual,
            "abs_residual": abs_r,
            "surprise": 1.0 if self.surprise else 0.0,
            "ready": 1.0,
            "mode": 1.0,  # 1 = torch
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def open_field_head(
    model_path: str | Path | None = None,
    *,
    threshold: float = 0.28,
    force_online: bool = False,
) -> OnlineFieldHead | ThroneFieldHead:
    """
    Prefer torch checkpoint when path exists and loads; otherwise online.
    Always returns a usable head — head is ON by default.
    """
    if force_online:
        return OnlineFieldHead(threshold=threshold)

    if model_path:
        p = Path(model_path)
        if p.exists():
            try:
                return ThroneFieldHead(p, threshold=threshold)
            except Exception as e:
                print(f"[throne-head] checkpoint load failed ({e}) — online fallback", flush=True)

    return OnlineFieldHead(threshold=threshold)
