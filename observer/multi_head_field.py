"""
Multi-head field pooling over CSI subcarriers.

Substance taken from the multi-head / MoE sketch — not the recursive-
immortal persona, not self-editing weights, not a toy LLM.

What transfers:
  • split spectrum into HEADS contiguous bands (like head dims)
  • per-head energy / mean / spread
  • soft routing weights across heads (load-balanced attention over bands)
  • fused scalar + head vector for Aurora / torch display

Feature vector order is locked to HEAD_FEATURE_NAMES in field_head:
  head_fused_mean, head_fused_energy, head_fused_spread, head_entropy, head_dominant
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

try:
    from .measurement import FIELD_HEADS, FIELD_SUBCARRIERS
except ImportError:
    from measurement import FIELD_HEADS, FIELD_SUBCARRIERS  # type: ignore


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def _softmax(xs: list[float], temp: float = 1.0) -> list[float]:
    if not xs:
        return []
    t = max(1e-6, float(temp))
    m = max(xs)
    ex = [math.exp((v - m) / t) for v in xs]
    s = sum(ex) or 1.0
    return [v / s for v in ex]


@dataclass
class HeadSummary:
    index: int
    mean: float
    energy: float
    spread: float
    peak: float
    weight: float  # routing mass


@dataclass
class FieldPool:
    """Fused multi-head view of one CSI snapshot."""

    heads: list[HeadSummary] = field(default_factory=list)
    fused_mean: float = 0.0
    fused_energy: float = 0.0
    fused_spread: float = 0.0
    dominant_head: int = 0
    entropy: float = 0.0  # routing entropy (0 = one head owns all)

    def as_features(self) -> list[float]:
        """Compact feature vector — order matches HEAD_FEATURE_NAMES."""
        return [
            self.fused_mean,
            self.fused_energy,
            self.fused_spread,
            self.entropy,
            float(self.dominant_head) / max(1, len(self.heads)),
        ]


def pool_subcarriers(
    csi: Sequence[float],
    *,
    heads: int = FIELD_HEADS,
    expected_sc: int = FIELD_SUBCARRIERS,
    routing_temp: float = 0.85,
) -> FieldPool:
    """Split CSI into heads, score each, soft-route, fuse."""
    vals = [float(x) for x in csi[:expected_sc]]
    if len(vals) < heads:
        vals = vals + [0.0] * (heads - len(vals))
    n = len(vals)
    heads = max(1, min(heads, n))
    width = n // heads

    summaries: list[HeadSummary] = []
    raw_scores: list[float] = []

    for h in range(heads):
        a = h * width
        b = n if h == heads - 1 else (h + 1) * width
        band = vals[a:b] or [0.0]
        mean = sum(band) / len(band)
        peak = max(band)
        energy = math.sqrt(sum(v * v for v in band) / len(band))
        if len(band) > 1:
            mu = mean
            spread = math.sqrt(sum((v - mu) ** 2 for v in band) / len(band))
        else:
            spread = 0.0
        score = energy * 0.7 + peak * 0.3
        raw_scores.append(score)
        summaries.append(
            HeadSummary(
                index=h,
                mean=_clip01(mean),
                energy=_clip01(energy),
                spread=_clip01(spread * 2.0),
                peak=_clip01(peak),
                weight=0.0,
            )
        )

    weights = _softmax(raw_scores, temp=routing_temp)
    for s, w in zip(summaries, weights):
        s.weight = w

    fused_mean = sum(s.mean * s.weight for s in summaries)
    fused_energy = sum(s.energy * s.weight for s in summaries)
    fused_spread = sum(s.spread * s.weight for s in summaries)
    dominant = max(range(len(summaries)), key=lambda i: summaries[i].weight)
    ent = -sum(w * math.log(w + 1e-12) for w in weights)
    ent_n = ent / math.log(len(weights)) if len(weights) > 1 else 0.0

    return FieldPool(
        heads=summaries,
        fused_mean=_clip01(fused_mean),
        fused_energy=_clip01(fused_energy),
        fused_spread=_clip01(fused_spread),
        dominant_head=dominant,
        entropy=_clip01(ent_n),
    )
