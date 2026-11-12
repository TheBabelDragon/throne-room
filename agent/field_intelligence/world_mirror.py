"""World Mirror — persistent, queryable representation of observed environment.

Builds on SHARED_BODY registry + perception adapters.
Never invents coordinates, never turns missing measurements into zeroes.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from agent.hashutil import uid


class EntityStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    MISSING = "MISSING"
    ALIVE = "ALIVE"
    TIMEOUT = "TIMEOUT"


class EvidenceKind(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    SIMULATION = "SIMULATION"
    FIXTURE = "FIXTURE"
    OFFLINE = "OFFLINE"


@dataclass
class WorldEvidence:
    observation_id: str
    source_system: str
    source_node_id: str
    observed_at: str
    ingested_at: str
    synthetic: bool
    kind: EvidenceKind = EvidenceKind.LIVE

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class WorldEntity:
    body_id: str
    status: EntityStatus
    body_type: str | None = None
    regions: list[str] = field(default_factory=list)
    measurements: dict[str, float | None] = field(default_factory=dict)
    energy: float | None = None
    evidence: WorldEvidence | None = None
    previous_observation_id: str | None = None
    is_new: bool = False
    is_returning: bool = False
    measurement_changed: bool = False
    last_seen_ingest: float | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        if self.evidence is not None:
            d["evidence"] = self.evidence.as_dict()
        return d


@dataclass
class WorldChange:
    change_id: str
    body_id: str
    kind: str
    detail: str
    observation_id: str | None = None
    sequence: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorldRelation:
    relation_id: str
    kind: str
    left: str
    right: str
    evidence_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorldSnapshot:
    snapshot_id: str
    sequence: int
    created_at: float
    entities: list[WorldEntity]
    changes: list[WorldChange]
    relations: list[WorldRelation]
    mode: str = "LIVE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "sequence": self.sequence,
            "created_at": self.created_at,
            "mode": self.mode,
            "entities": [e.as_dict() for e in self.entities],
            "changes": [c.as_dict() for c in self.changes],
            "relations": [r.as_dict() for r in self.relations],
        }


def _map_status(raw: str | None, synthetic: bool) -> EntityStatus:
    s = (raw or "UNKNOWN").upper()
    if s in ("ALIVE", "OBSERVED"):
        return EntityStatus.ALIVE if s == "ALIVE" else EntityStatus.OBSERVED
    if s == "STALE":
        return EntityStatus.STALE
    if s in ("TIMEOUT", "MISSING"):
        return EntityStatus.TIMEOUT if s == "TIMEOUT" else EntityStatus.MISSING
    return EntityStatus.UNKNOWN


class WorldMirror:
    """Query surface over SHARED_BODY-derived state. Read-only w.r.t. FieldTick."""

    def __init__(self, *, root: Path | str | None = None, mode: str = "LIVE") -> None:
        self.root = Path(root) if root else Path("/tmp/metafield/world_mirror")
        self.root.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self._entities: dict[str, WorldEntity] = {}
        self._prev_obs: dict[str, str] = {}
        self._prev_meas: dict[str, dict[str, float | None]] = {}
        self._changes: list[WorldChange] = []
        self._relations: list[WorldRelation] = []
        self._sequence = 0
        self._load()

    def _load(self) -> None:
        path = self.root / "state.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._sequence = int(data.get("sequence") or 0)
        self._prev_obs = dict(data.get("prev_obs") or {})
        raw_meas = data.get("prev_meas") or {}
        self._prev_meas = {
            k: {rk: (float(rv) if rv is not None else None) for rk, rv in v.items()}
            for k, v in raw_meas.items()
            if isinstance(v, dict)
        }

    def _persist(self) -> None:
        path = self.root / "state.json"
        payload = {"sequence": self._sequence, "prev_obs": self._prev_obs, "prev_meas": self._prev_meas}
        try:
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    def ingest_body_view(self, view: Any) -> list[WorldChange]:
        changes: list[WorldChange] = []
        body_id = str(getattr(view, "body_id", "") or "")
        if not body_id:
            return changes
        obs_id = str(getattr(view, "observation_id", "") or "")
        synthetic = bool(getattr(view, "synthetic", False))
        status = _map_status(str(getattr(view, "status", "UNKNOWN") or "UNKNOWN"), synthetic)
        measurements = dict(getattr(view, "measurements", {}) or {})
        clean_meas: dict[str, float | None] = {}
        for k, v in measurements.items():
            if v is None:
                clean_meas[str(k)] = None
            else:
                try:
                    clean_meas[str(k)] = float(v)
                except (TypeError, ValueError):
                    clean_meas[str(k)] = None
        energy = getattr(view, "energy", None)
        if energy is not None:
            try:
                energy = float(energy)
            except (TypeError, ValueError):
                energy = None
        prev_obs = self._prev_obs.get(body_id)
        is_new = prev_obs is None and not synthetic
        is_returning = bool(getattr(view, "is_returning", False))
        if prev_obs and prev_obs != obs_id and status in (EntityStatus.ALIVE, EntityStatus.OBSERVED):
            if body_id in self._entities and self._entities[body_id].status in (
                EntityStatus.MISSING, EntityStatus.TIMEOUT, EntityStatus.STALE,
            ):
                is_returning = True
        prev_m = self._prev_meas.get(body_id, {})
        measurement_changed = False
        for k, v in clean_meas.items():
            if k not in prev_m:
                if v is not None:
                    measurement_changed = True
            elif prev_m[k] != v:
                measurement_changed = True
        evidence = WorldEvidence(
            observation_id=obs_id,
            source_system=str(getattr(view, "source_system", "") or ""),
            source_node_id=str(getattr(view, "source_node_id", "") or ""),
            observed_at=str(getattr(view, "observed_at", "") or ""),
            ingested_at=str(getattr(view, "ingested_at", "") or ""),
            synthetic=synthetic,
            kind=EvidenceKind.FIXTURE if synthetic else EvidenceKind.LIVE,
        )
        if self.mode == "REPLAY":
            evidence.kind = EvidenceKind.REPLAY
        elif self.mode == "SIMULATION":
            evidence.kind = EvidenceKind.SIMULATION
        entity = WorldEntity(
            body_id=body_id, status=status, body_type=getattr(view, "body_type", None),
            regions=list(getattr(view, "regions", []) or []), measurements=clean_meas,
            energy=energy, evidence=evidence, previous_observation_id=prev_obs,
            is_new=is_new, is_returning=is_returning, measurement_changed=measurement_changed,
            last_seen_ingest=time.time(),
        )
        self._entities[body_id] = entity
        self._sequence += 1
        seq = self._sequence
        if is_new:
            changes.append(WorldChange(change_id=uid("wch"), body_id=body_id, kind="NEW",
                detail=f"first observation {obs_id}", observation_id=obs_id, sequence=seq))
        if is_returning:
            changes.append(WorldChange(change_id=uid("wch"), body_id=body_id, kind="RETURNING",
                detail=f"reappeared as {obs_id}", observation_id=obs_id, sequence=seq))
        if measurement_changed and not is_new:
            changes.append(WorldChange(change_id=uid("wch"), body_id=body_id, kind="MEASUREMENT",
                detail="measurement values changed", observation_id=obs_id, sequence=seq))
        if prev_obs and obs_id and prev_obs != obs_id:
            self._relations.append(WorldRelation(relation_id=uid("wrel"), kind="TEMPORAL",
                left=prev_obs, right=obs_id, evidence_ids=[obs_id]))
            self._relations.append(WorldRelation(relation_id=uid("wrel"), kind="SAME_BODY",
                left=body_id, right=obs_id, evidence_ids=[obs_id]))
        src = evidence.source_node_id
        if src:
            self._relations.append(WorldRelation(relation_id=uid("wrel"), kind="SAME_SOURCE",
                left=body_id, right=src, evidence_ids=[obs_id] if obs_id else []))
        if obs_id:
            self._prev_obs[body_id] = obs_id
        self._prev_meas[body_id] = dict(clean_meas)
        self._changes.extend(changes)
        if len(self._changes) > 500:
            self._changes = self._changes[-500:]
        if len(self._relations) > 1000:
            self._relations = self._relations[-1000:]
        self._persist()
        return changes

    def mark_missing(self, body_id: str, reason: str = "no recent observation") -> WorldChange | None:
        ent = self._entities.get(body_id)
        if ent is None or ent.status == EntityStatus.MISSING:
            return None
        ent.status = EntityStatus.MISSING
        self._sequence += 1
        ch = WorldChange(change_id=uid("wch"), body_id=body_id, kind="DISAPPEAR", detail=reason, sequence=self._sequence)
        self._changes.append(ch)
        self._persist()
        return ch

    def snapshot(self) -> WorldSnapshot:
        return WorldSnapshot(
            snapshot_id=uid("wsnp"), sequence=self._sequence, created_at=time.time(),
            entities=list(self._entities.values()), changes=list(self._changes[-50:]),
            relations=list(self._relations[-100:]), mode=self.mode,
        )

    def get_entity(self, body_id: str) -> WorldEntity | None:
        return self._entities.get(body_id)

    def entities(self) -> list[WorldEntity]:
        return list(self._entities.values())
