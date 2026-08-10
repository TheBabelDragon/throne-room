"""
Throne field head — prediction + residual + surprise.

Spatial learning rules (hard):
  - NO placeholder memory caps (FINE_LEN / DISPLAY_LEN / HEAD_LEN only)
  - NO slope-to-start: first observation seeds state
  - BOTH HANDS equal base weight (mean 0.40 + energy 0.40)
  - multi-head entropy modulates threshold, not base weight balance

Obscure limits fixed for initial-AI learning:
  - HEAD_LEN = rate × HEAD_WINDOW_S (not magic 12 samples)
  - residual-calibrated surprise threshold (noise floor aware)
  - adaptive EMA alpha (settles when stable, tracks when residual high)
  - head_state.json so Aurora can couple to residual (closed loop)
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Sequence, Tuple

import numpy as np

try:
    from observer.measurement import HEAD_LEN, HEAD_STATE_PATH_DEFAULT, HEAD_WINDOW_S, SAMPLE_HZ
except ImportError:
    try:
        from measurement import HEAD_LEN, HEAD_STATE_PATH_DEFAULT, HEAD_WINDOW_S, SAMPLE_HZ  # type: ignore
    except ImportError:
        HEAD_LEN = 96
        HEAD_WINDOW_S = 12.0
        SAMPLE_HZ = 8.0
        HEAD_STATE_PATH_DEFAULT = "/tmp/metafield/head_state.json"

FEATURE_NAMES = [
    "csi_mean", "csi_energy", "csi_spread", "csi_peak",
    "rssi", "n_bodies", "mean_conf", "packet_rate_n",
]
HEAD_FEATURE_NAMES = [
    "head_fused_mean", "head_fused_energy", "head_fused_spread",
    "head_entropy", "head_dominant",
]


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


class OnlineFieldHead:
    """Multi-head aware online predictor tuned for initial spatial learning."""

    def __init__(
        self,
        *,
        window: int | None = None,
        threshold: float = 0.28,
        ema_alpha: float = 0.18,
        state_path: str | Path | None = HEAD_STATE_PATH_DEFAULT,
    ) -> None:
        self.window = max(24, int(window if window is not None else HEAD_LEN))
        self.base_threshold = float(threshold)
        self.threshold = float(threshold)
        self.base_alpha = float(ema_alpha)
        self.ema_alpha = float(ema_alpha)
        self.state_path = Path(state_path) if state_path else None
        self.history: Deque[List[float]] = deque(maxlen=self.window)
        self.resid_hist: Deque[float] = deque(maxlen=self.window)
        self._ema_mean = None
        self._ema_energy = None
        self._trend = 0.0
        self._resid_ema = 0.0
        self.last_pred = 0.0
        self.last_actual = 0.0
        self.last_abs_residual = 0.0
        self.surprise = False
        self.ready = False
        self.n_scored = 0
        self.mode = "online"
        self._last_state_write = 0.0
        print(
            f"[throne-head] online multi-head  window={self.window} "
            f"({HEAD_WINDOW_S:g}s @ {SAMPLE_HZ:g}Hz)  "
            f"thr={self.threshold:.2f}  both-hands=equal  no-slope-start  "
            f"resid-calibrated",
            flush=True,
        )

    def maybe_reload(self) -> None:
        return

    def _calibrate_threshold(self) -> float:
        if len(self.resid_hist) < max(12, self.window // 4):
            return self.base_threshold
        arr = np.asarray(self.resid_hist, dtype=float)
        med = float(np.median(arr))
        mad = float(np.median(np.abs(arr - med))) + 1e-6
        thr = med + 3.5 * mad
        thr = max(self.base_threshold * 0.60, min(self.base_threshold * 1.40, thr))
        return float(thr)

    def _adapt_alpha(self, abs_r: float) -> float:
        a = self.base_alpha
        if abs_r > self.threshold * 1.2:
            a = min(0.32, a * 1.35)
        elif abs_r < self.threshold * 0.4 and self.n_scored > self.window:
            a = max(0.08, a * 0.85)
        return a

    def _write_state(self) -> None:
        if self.state_path is None:
            return
        now = time.time()
        if now - self._last_state_write < 0.4:
            return
        self._last_state_write = now
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "type": "HEAD_STATE",
                "mode": self.mode,
                "ready": self.ready,
                "surprise": self.surprise,
                "pred": round(self.last_pred, 4),
                "actual": round(self.last_actual, 4),
                "abs_residual": round(self.last_abs_residual, 4),
                "threshold": round(self.threshold, 4),
                "ema_alpha": round(self.ema_alpha, 4),
                "window": self.window,
                "n_scored": self.n_scored,
                "resid_ema": round(self._resid_ema, 4),
                "timestamp": now,
            }
            self.state_path.write_text(json.dumps(payload, separators=(",", ":")))
        except OSError:
            pass

    def update(self, feats: Sequence[float]) -> Dict[str, float]:
        base = [_clip01(float(x)) for x in list(feats)[: len(FEATURE_NAMES)]]
        while len(base) < len(FEATURE_NAMES):
            base.append(0.0)
        extra = list(feats)[len(FEATURE_NAMES) : len(FEATURE_NAMES) + len(HEAD_FEATURE_NAMES)]
        while len(extra) < len(HEAD_FEATURE_NAMES):
            extra.append(0.0)
        extra = [_clip01(float(x)) for x in extra]

        mean, energy, spread = base[0], base[1], base[2]
        head_entropy, head_dom = extra[3], extra[4]

        if self._ema_mean is None:
            self._ema_mean = mean
            self._ema_energy = energy
            self._trend = 0.0
            self.history.append(base + extra)
            self.n_scored = 1
            self.ready = False
            self.surprise = False
            self.last_pred = mean
            self.last_actual = mean
            self.last_abs_residual = 0.0
            self._write_state()
            return {
                "pred": mean, "actual": mean, "abs_residual": 0.0,
                "surprise": 0.0, "ready": 0.0,
                "entropy": head_entropy, "dominant": head_dom, "mode": 0.0,
            }

        pred = _clip01(
            self._ema_mean * 0.40 + self._ema_energy * 0.40
            + self._trend * 0.12 + spread * 0.08
        )
        if head_entropy > 0.55:
            pred = _clip01(0.55 * pred + 0.25 * self._ema_mean + 0.20 * self._ema_energy)
        elif head_dom > 0.55:
            pred = _clip01(0.50 * pred + 0.20 * self._ema_mean + 0.30 * energy)

        actual = mean
        abs_r = abs(actual - pred)
        self.resid_hist.append(abs_r)
        self._resid_ema = 0.9 * self._resid_ema + 0.1 * abs_r

        thr = self._calibrate_threshold()
        if head_entropy < 0.25:
            thr *= 0.85
        elif head_entropy > 0.65:
            thr *= 1.15
        self.threshold = thr

        self.history.append(base + extra)
        a = self._adapt_alpha(abs_r)
        self.ema_alpha = a
        prev_ema = self._ema_mean
        self._ema_mean = (1.0 - a) * self._ema_mean + a * mean
        self._ema_energy = (1.0 - a) * self._ema_energy + a * energy
        self._trend = 0.8 * self._trend + 0.2 * (self._ema_mean - prev_ema)

        self.last_pred = pred
        self.last_actual = actual
        self.last_abs_residual = abs_r
        self.surprise = abs_r >= thr and self.n_scored >= min(self.window, max(24, self.window // 2))
        self.ready = len(self.history) >= min(12, self.window // 2)
        self.n_scored += 1
        self._write_state()

        return {
            "pred": pred, "actual": actual, "abs_residual": abs_r,
            "surprise": 1.0 if self.surprise else 0.0,
            "ready": 1.0 if self.ready else 0.0,
            "entropy": head_entropy, "dominant": head_dom,
            "mode": 0.0, "threshold": thr,
        }


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
        raise ImportError("torch required once to load the head checkpoint") from e
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
            f"in_dim={self.in_dim}  thr={self.threshold:.2f}", flush=True,
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
            self.n_scored += 1
            return {"pred": feats_l[0], "actual": feats_l[0], "abs_residual": 0.0, "surprise": 0.0, "ready": 0.0}
        x = np.array([v for row in self.history for v in row], dtype=np.float64)
        if x.shape[0] != self.in_dim:
            self.history.clear()
            self.history.append(feats_l)
            self.ready = False
            return {"pred": feats_l[0], "actual": feats_l[0], "abs_residual": 0.0, "surprise": 0.0, "ready": 0.0}
        pred = float(self.mlp(x)[0])
        actual = float(feats_l[0])
        abs_r = abs(actual - pred)
        self.history.append(feats_l)
        self.last_pred, self.last_actual, self.last_abs_residual = pred, actual, abs_r
        self.surprise = abs_r >= self.threshold
        self.ready = True
        self.n_scored += 1
        return {"pred": pred, "actual": actual, "abs_residual": abs_r, "surprise": 1.0 if self.surprise else 0.0, "ready": 1.0, "mode": 1.0}


def open_field_head(
    model_path: str | Path | None = None,
    *,
    threshold: float = 0.28,
    force_online: bool = False,
) -> OnlineFieldHead | ThroneFieldHead:
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
