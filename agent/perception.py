"""Perception adapters: synthetic CSI, FieldObservation → PerceptionEvent."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from agent.hashutil import uid
from agent.schemas import FieldObservation, FieldRegion, PerceptionEvent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_synthetic_csi(tick: int, body: str = "synthetic_cyd") -> FieldObservation:
    t = tick * 0.08
    rssi = -58 + 8 * math.sin(t * 0.35)
    csi: list[float] = []
    for i in range(32):
        k = i / 31
        v = (
            0.35
            + 0.25 * math.sin(t + k * 6.28)
            + 0.12 * math.sin(t * 2.2 + k * 12)
            + 0.05 * math.sin(t * 7 + i)
        )
        csi.append(max(0.0, min(1.0, v)))
    n = 32
    mean = sum(csi) / n
    energy = math.sqrt(sum(v * v for v in csi) / n)
    variance = sum((v - mean) ** 2 for v in csi) / n
    spread = math.sqrt(variance)
    rssi_n = max(0.0, min(1.0, (rssi + 90) / 60))
    return FieldObservation(
        body_id=body,
        body_type="wifi_csi",
        timestamp=str(tick),
        synthetic=True,
        valid=True,
        rssi_dbm=rssi,
        csi=csi,
        regions=[
            FieldRegion("rssi", rssi_n, 0.4),
            FieldRegion("csi_mean", mean, 0.4),
            FieldRegion("csi_peak", max(csi), 0.4),
            FieldRegion("csi_energy", energy, 0.4),
            FieldRegion("csi_spread", min(1.0, spread * 2), 0.4),
        ],
    )


def observation_to_perception(obs: FieldObservation, tick: int) -> PerceptionEvent:
    energy = next((r.observed for r in obs.regions if r.name == "csi_energy"), 0.0)
    return PerceptionEvent(
        id=uid("obs"),
        source=obs.body_id,
        timestamp=obs.timestamp,
        tick=tick,
        modality="csi",
        features={
            "rssi_dbm": obs.rssi_dbm,
            "energy": energy,
            "mean": next((r.observed for r in obs.regions if r.name == "csi_mean"), 0.0),
            "peak": next((r.observed for r in obs.regions if r.name == "csi_peak"), 0.0),
            "spread": next((r.observed for r in obs.regions if r.name == "csi_spread"), 0.0),
            "synthetic": obs.synthetic,
        },
        confidence=0.4 if obs.synthetic else 0.9,
    )


def chat_perception(text: str, tick: int) -> PerceptionEvent:
    return PerceptionEvent(
        id=uid("obs"),
        source="throne-room",
        timestamp=_now(),
        tick=tick,
        modality="language",
        features={"text": text},
        confidence=1.0,
    )
