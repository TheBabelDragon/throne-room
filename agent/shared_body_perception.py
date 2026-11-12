"""Read-only SHARED_BODY → PerceptionEvent adapter for Qwuack / agent.

Never writes FieldTick. Never grants capabilities. Never fabricates values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent.hashutil import uid
from agent.schemas import PerceptionEvent


@dataclass
class BodyView:
    body_id: str
    observation_id: str
    source_system: str
    source_node_id: str
    observed_at: str
    ingested_at: str
    status: str
    synthetic: bool
    body_type: str | None = None
    regions: list[str] = field(default_factory=list)
    measurements: dict[str, float | None] = field(default_factory=dict)
    energy: float | None = None
    previous_observation_id: str | None = None
    is_new: bool = False
    is_returning: bool = False
    measurement_changed: bool = False
    change_summary: str | None = None


@dataclass
class SharedBodyPerceptionState:
    mode: str = "OFFLINE"
    recognized: int = 0
    new_bodies: int = 0
    returning_bodies: int = 0
    alive: int = 0
    stale: int = 0
    timeout: int = 0
    latest_body_id: str | None = None
    latest_observation_id: str | None = None
    latest_change: str | None = None
    memory_updates: int = 0
    views: list[BodyView] = field(default_factory=list)


_prev_obs: dict[str, str] = {}
_prev_meas: dict[str, dict[str, float | None]] = {}


def reset_perception_memory() -> None:
    _prev_obs.clear()
    _prev_meas.clear()


def _body_to_view(body: Any) -> BodyView:
    d = body.to_dict() if hasattr(body, "to_dict") else dict(body)
    body_id = str(d.get("body_id") or "")
    obs_id = str(d.get("observation_id") or "")
    prov = d.get("provenance") or {}
    synthetic = bool(prov.get("synthetic", False))
    measurements: dict[str, float | None] = {}
    for m in d.get("measurements") or []:
        if not isinstance(m, dict):
            continue
        region = m.get("region")
        if not region:
            continue
        val = m.get("value")
        measurements[str(region)] = float(val) if val is not None else None
    energy = d.get("energy")
    if energy is not None:
        try:
            energy = float(energy)
        except (TypeError, ValueError):
            energy = None
    prev = _prev_obs.get(body_id)
    is_new = prev is None
    is_returning = prev is not None and prev != obs_id
    changed = False
    summary = None
    prev_m = _prev_meas.get(body_id)
    if prev_m is not None:
        for k, v in measurements.items():
            old = prev_m.get(k)
            if v is None and old is None:
                continue
            if v is None or old is None or abs(float(v) - float(old)) > 1e-9:
                changed = True
                summary = f"{k}:{old}->{v}"
                break
    return BodyView(
        body_id=body_id,
        observation_id=obs_id,
        source_system=str(d.get("source_system") or ""),
        source_node_id=str(d.get("source_node_id") or body_id),
        observed_at=str(d.get("observed_at") or ""),
        ingested_at=str(d.get("ingested_at") or ""),
        status=str(d.get("status") or "MISSING"),
        synthetic=synthetic,
        body_type=d.get("body_type"),
        regions=list(d.get("regions") or []),
        measurements=measurements,
        energy=energy,
        previous_observation_id=prev,
        is_new=is_new,
        is_returning=bool(is_returning and not is_new),
        measurement_changed=changed,
        change_summary=summary,
    )


def perceive_shared_bodies(
    tick: int,
    registry: Any | None = None,
    *,
    snapshot_path: str | None = None,
) -> list[PerceptionEvent]:
    bodies: list[Any] = []
    try:
        if registry is not None:
            bodies = list(registry.all())
        else:
            from observer.shared_body.registry import SharedBodyRegistry
            reg = SharedBodyRegistry(auto_persist=False)
            bodies = list(reg.all())
    except Exception:
        return []

    events: list[PerceptionEvent] = []
    for body in bodies:
        try:
            view = _body_to_view(body)
        except Exception:
            continue
        features: dict[str, Any] = {
            "body_id": view.body_id,
            "observation_id": view.observation_id,
            "source_system": view.source_system,
            "source_node_id": view.source_node_id,
            "observed_at": view.observed_at,
            "ingested_at": view.ingested_at,
            "status": view.status,
            "synthetic": view.synthetic,
            "body_type": view.body_type,
            "regions": view.regions,
            "is_new": view.is_new,
            "is_returning": view.is_returning,
            "measurement_changed": view.measurement_changed,
            "change_summary": view.change_summary,
            "previous_observation_id": view.previous_observation_id,
        }
        if view.energy is not None:
            features["energy"] = view.energy
        for k, v in view.measurements.items():
            features[f"m:{k}"] = v
        conf = 0.35 if view.synthetic else 0.9
        if view.status in ("STALE", "TIMEOUT", "MISSING"):
            conf *= 0.5
        events.append(
            PerceptionEvent(
                id=uid("sbody"),
                source=view.body_id,
                timestamp=view.observed_at or view.ingested_at,
                tick=tick,
                modality="shared_body",
                features=features,
                confidence=conf,
            )
        )
        _prev_obs[view.body_id] = view.observation_id
        _prev_meas[view.body_id] = dict(view.measurements)
    return events


def perception_status(
    registry: Any | None = None,
    events: list[PerceptionEvent] | None = None,
) -> SharedBodyPerceptionState:
    state = SharedBodyPerceptionState()
    try:
        if registry is not None:
            counts = registry.counts()
            bodies = registry.all()
        else:
            from observer.shared_body.registry import SharedBodyRegistry
            reg = SharedBodyRegistry(auto_persist=False)
            counts = reg.counts()
            bodies = reg.all()
    except Exception as e:
        state.mode = "ERROR"
        state.latest_change = str(e)[:120]
        return state

    state.recognized = counts.get("total", 0)
    state.alive = counts.get("alive", 0)
    state.stale = counts.get("stale", 0)
    state.timeout = counts.get("timeout", 0)
    if state.recognized == 0:
        state.mode = "OFFLINE"
        return state

    views = []
    any_synth = any_live = False
    for b in bodies:
        try:
            v = _body_to_view(b)
        except Exception:
            continue
        views.append(v)
        if v.synthetic:
            any_synth = True
        if v.status == "ALIVE" and not v.synthetic:
            any_live = True
        if v.is_new:
            state.new_bodies += 1
        if v.is_returning:
            state.returning_bodies += 1
        if v.measurement_changed:
            state.latest_change = v.change_summary
        state.latest_body_id = v.body_id
        state.latest_observation_id = v.observation_id
    state.views = views
    if any_live:
        state.mode = "LIVE"
    elif any_synth and state.alive > 0:
        state.mode = "FIXTURE"
    elif state.stale > 0 or state.timeout > 0:
        state.mode = "STALE"
    else:
        state.mode = "OFFLINE"
    return state
