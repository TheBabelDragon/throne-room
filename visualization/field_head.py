"""
Optional torch field head for Throne Room display.

Loads a MetaField-style TinyFieldHead checkpoint once via torch,
then runs pure numpy forward for residual / surprise scoring.

Checkpoint contract (same family as echo_head.pt):
  {
    "state_dict": { "net.0.weight", "net.0.bias", "net.2.*", "net.4.*" },
    "window": int,
    "in_dim": int,
  }

Feature vector (len 8, windowable):
  csi_mean, csi_energy, csi_spread, csi_peak, rssi,
  n_bodies, mean_conf, packet_rate_n
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Tuple

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


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


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
        try:
            self._mtime = self.path.stat().st_mtime
        except OSError:
            self._mtime = 0.0
        print(
            f"[throne-head] loaded {self.path}  window={self.window}  "
            f"in_dim={self.in_dim}  thr={self.threshold:.2f}"
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

    def update(self, feats: List[float]) -> Dict[str, float]:
        if self.n_scored and self.n_scored % 40 == 0:
            self.maybe_reload()
        feats = [_clip01(float(x)) for x in feats[: len(FEATURE_NAMES)]]
        while len(feats) < len(FEATURE_NAMES):
            feats.append(0.0)

        if len(self.history) < self.window:
            self.history.append(feats)
            self.ready = False
            self.surprise = False
            return {
                "pred": 0.0,
                "actual": feats[0],
                "abs_residual": 0.0,
                "surprise": 0.0,
                "ready": 0.0,
            }

        x = np.array([v for row in self.history for v in row], dtype=np.float64)
        if x.shape[0] != self.in_dim:
            self.history.clear()
            self.history.append(feats)
            self.ready = False
            return {
                "pred": 0.0,
                "actual": feats[0],
                "abs_residual": 0.0,
                "surprise": 0.0,
                "ready": 0.0,
            }

        pred = float(self.mlp(x)[0])
        actual = float(feats[0])
        abs_r = abs(actual - pred)
        self.history.append(feats)
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
        }
