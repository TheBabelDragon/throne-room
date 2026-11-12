"""SHARED_BODY schema v2 — versioned, validated, provenance-preserving."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "2.0"
SCHEMA_TYPE = "SHARED_BODY"

KNOWN_BODY_TYPES = frozenset({
    "optical", "lattice", "wifi_csi", "ultrasonic", "zvs", "hall", "sim", "other",
})

BUS_NODE_REGISTRY: dict[int, str] = {
    0x01: "host", 0x02: "optical", 0x03: "hall-sensor",
    0x04: "actuator", 0x05: "compute", 0x06: "expansion",
}

_BODY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$")


class SharedBodyError(Exception):
    pass


class SharedBodyValidationError(SharedBodyError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_observation_id(
    body_id: str, observed_at: str, source_system: str, regions_fingerprint: str = "",
) -> str:
    raw = f"{body_id}|{observed_at}|{source_system}|{regions_fingerprint}"
    return "obs_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def bus_node_to_body_id(node_id: int, instance: int | None = None) -> str:
    role = BUS_NODE_REGISTRY.get(int(node_id) & 0xFF, f"node-{int(node_id) & 0xFF:02x}")
    return role if instance is None else f"{role}-{int(instance):02d}"


def body_id_to_bus_node(body_id: str) -> int | None:
    if not body_id:
        return None
    lower = body_id.lower()
    for nid, role in BUS_NODE_REGISTRY.items():
        if lower == role or lower.startswith(role + "-"):
            return nid
    if lower.startswith("bus-0x"):
        try:
            return int(lower.split("0x", 1)[1], 16) & 0xFF
        except ValueError:
            return None
    return None


def infer_body_type(body_id: str, region_names: list[str] | None = None) -> str:
    bid = (body_id or "").lower()
    regs = [r.lower() for r in (region_names or [])]
    if any(k.startswith("csi_") or k == "rssi" for k in regs) or "cyd" in bid or "csi" in bid:
        return "wifi_csi"
    if "optical" in bid or any(k.startswith("detector_") for k in regs):
        return "optical"
    if "hall" in bid or any(k.startswith("hall_") for k in regs):
        return "hall"
    if "zvs" in bid:
        return "zvs"
    if "echo" in bid or "ultrasonic" in bid:
        return "ultrasonic"
    if "lattice" in bid or "hmc" in bid:
        return "lattice"
    if bid.startswith("synthetic") or "sim" in bid:
        return "sim"
    return "other"


@dataclass
class Measurement:
    region: str
    value: float | None
    confidence: float | None = None
    unit: str | None = None
    source_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"region": self.region}
        if self.value is not None:
            d["value"] = float(self.value)
        if self.confidence is not None:
            d["confidence"] = float(self.confidence)
        if self.unit is not None:
            d["unit"] = self.unit
        if self.source_key is not None:
            d["source_key"] = self.source_key
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Measurement":
        if not isinstance(data, dict) or "region" not in data:
            raise SharedBodyValidationError("Measurement requires 'region'")
        val = data.get("value")
        if val is not None:
            try:
                val = float(val)
            except (TypeError, ValueError) as e:
                raise SharedBodyValidationError(f"Measurement.value must be number or null: {e}") from e
        conf = data.get("confidence")
        if conf is not None:
            try:
                conf = float(conf)
            except (TypeError, ValueError) as e:
                raise SharedBodyValidationError(f"Measurement.confidence must be number or null: {e}") from e
        return cls(
            region=str(data["region"]),
            value=val,
            confidence=conf,
            unit=str(data["unit"]) if data.get("unit") is not None else None,
            source_key=str(data["source_key"]) if data.get("source_key") is not None else None,
        )


def measurement_from_region(
    region: str,
    observed: float | None,
    confidence: float | None = None,
    source_key: str | None = None,
) -> Measurement:
    return Measurement(
        region=str(region),
        value=None if observed is None else float(observed),
        confidence=None if confidence is None else float(confidence),
        source_key=source_key,
    )


@dataclass
class Provenance:
    packet_type: str | None = None
    raw_node: str | None = None
    device_timestamp: str | int | float | None = None
    synthetic: bool = False
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.packet_type is not None:
            d["packet_type"] = self.packet_type
        if self.raw_node is not None:
            d["raw_node"] = self.raw_node
        if self.device_timestamp is not None:
            d["device_timestamp"] = self.device_timestamp
        if self.synthetic:
            d["synthetic"] = True
        if self.notes is not None:
            d["notes"] = self.notes
        if self.extra:
            d["extra"] = dict(self.extra)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Provenance":
        if not data:
            return cls()
        extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
        known = {"packet_type", "raw_node", "device_timestamp", "synthetic", "notes", "extra"}
        for k, v in data.items():
            if k not in known and k not in extra:
                extra[k] = v
        return cls(
            packet_type=str(data["packet_type"]) if data.get("packet_type") is not None else None,
            raw_node=str(data["raw_node"]) if data.get("raw_node") is not None else None,
            device_timestamp=data.get("device_timestamp"),
            synthetic=bool(data.get("synthetic", False)),
            notes=str(data["notes"]) if data.get("notes") is not None else None,
            extra=extra,
        )


@dataclass
class SharedBody:
    body_id: str
    schema_version: str
    source_system: str
    source_node_id: str
    observation_id: str
    observed_at: str
    ingested_at: str
    regions: list[str]
    measurements: list[Measurement]
    provenance: Provenance
    body_type: str = "other"
    bus_node_id: int | None = None
    energy: float | None = None
    heat: float | None = None
    hot_cell: list[int] | None = None
    health: str | None = None
    geometry_state: str | None = None
    residual: float | None = None
    surprise: bool | None = None
    deposits: int | None = None
    last_seen: float | None = None
    status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "type": SCHEMA_TYPE,
            "body_id": self.body_id,
            "source_system": self.source_system,
            "source_node_id": self.source_node_id,
            "observation_id": self.observation_id,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "regions": list(self.regions),
            "measurements": [m.to_dict() for m in self.measurements],
            "provenance": self.provenance.to_dict(),
            "body_type": self.body_type,
        }
        if self.bus_node_id is not None:
            d["bus_node_id"] = self.bus_node_id
        if self.energy is not None:
            d["energy"] = float(self.energy)
        if self.heat is not None:
            d["heat"] = float(self.heat)
        if self.hot_cell is not None:
            d["hot_cell"] = list(self.hot_cell)
        if self.health is not None:
            d["health"] = self.health
        if self.geometry_state is not None:
            d["geometry_state"] = self.geometry_state
        if self.residual is not None:
            d["residual"] = float(self.residual)
        if self.surprise is not None:
            d["surprise"] = bool(self.surprise)
        if self.deposits is not None:
            d["deposits"] = int(self.deposits)
        if self.last_seen is not None:
            d["last_seen"] = float(self.last_seen)
        if self.status is not None:
            d["status"] = self.status
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SharedBody":
        return validate_shared_body(data)


def validate_shared_body(data: Any) -> SharedBody:
    if not isinstance(data, dict):
        raise SharedBodyValidationError("SHARED_BODY must be a JSON object")
    errors: list[str] = []
    body_id = data.get("body_id")
    if not body_id or not isinstance(body_id, str):
        errors.append("body_id is required and must be a non-empty string")
    elif not _BODY_ID_RE.match(body_id):
        errors.append(f"body_id '{body_id}' has invalid characters")
    schema_version = data.get("schema_version")
    if schema_version is None:
        errors.append("schema_version is required")
    else:
        schema_version = str(schema_version)
        if not schema_version.startswith("2."):
            errors.append(f"schema_version '{schema_version}' incompatible; expect 2.x")
    source_system = data.get("source_system")
    if not source_system or not isinstance(source_system, str):
        errors.append("source_system is required")
    source_node_id = data.get("source_node_id")
    if source_node_id is None:
        source_node_id = str(body_id) if body_id else ""
    else:
        source_node_id = str(source_node_id)
    observation_id = data.get("observation_id")
    if not observation_id or not isinstance(observation_id, str):
        errors.append("observation_id is required")
    observed_at = data.get("observed_at")
    if not observed_at or not isinstance(observed_at, str):
        errors.append("observed_at is required")
    ingested_at = data.get("ingested_at")
    if not ingested_at or not isinstance(ingested_at, str):
        errors.append("ingested_at is required")
    regions = data.get("regions") or []
    if not isinstance(regions, list):
        errors.append("regions must be a list")
        regions = []
    else:
        regions = [str(r) for r in regions]
    raw_meas = data.get("measurements") or []
    measurements: list[Measurement] = []
    if not isinstance(raw_meas, list):
        errors.append("measurements must be a list")
    else:
        for i, m in enumerate(raw_meas):
            try:
                measurements.append(Measurement.from_dict(m))
            except SharedBodyValidationError as e:
                errors.append(f"measurements[{i}]: {e}")
    try:
        provenance = Provenance.from_dict(data.get("provenance"))
    except Exception as e:
        errors.append(f"provenance: {e}")
        provenance = Provenance()
    if errors:
        raise SharedBodyValidationError(
            "SHARED_BODY validation failed:\n  - " + "\n  - ".join(errors)
        )
    body_type = str(data.get("body_type") or "other")
    if body_type not in KNOWN_BODY_TYPES:
        body_type = "other"
    bus_node_id = data.get("bus_node_id")
    if bus_node_id is not None:
        try:
            bus_node_id = int(bus_node_id)
        except (TypeError, ValueError):
            raise SharedBodyValidationError("bus_node_id must be int or null")

    def _opt_float(key: str) -> float | None:
        v = data.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError) as e:
            raise SharedBodyValidationError(f"{key} must be number or null: {e}") from e

    energy = _opt_float("energy")
    heat = _opt_float("heat")
    residual = _opt_float("residual")
    last_seen = _opt_float("last_seen")
    hot_cell = data.get("hot_cell")
    if hot_cell is not None:
        if not isinstance(hot_cell, (list, tuple)) or len(hot_cell) != 3:
            raise SharedBodyValidationError("hot_cell must be [z,y,x] or null")
        try:
            hot_cell = [int(x) for x in hot_cell]
        except (TypeError, ValueError) as e:
            raise SharedBodyValidationError(f"hot_cell values must be int: {e}") from e
    deposits = data.get("deposits")
    if deposits is not None:
        try:
            deposits = int(deposits)
        except (TypeError, ValueError) as e:
            raise SharedBodyValidationError(f"deposits must be int or null: {e}") from e
    surprise = data.get("surprise")
    if surprise is not None:
        surprise = bool(surprise)
    return SharedBody(
        body_id=str(body_id),
        schema_version=schema_version,
        source_system=str(source_system),
        source_node_id=source_node_id,
        observation_id=str(observation_id),
        observed_at=str(observed_at),
        ingested_at=str(ingested_at),
        regions=regions,
        measurements=measurements,
        provenance=provenance,
        body_type=body_type,
        bus_node_id=bus_node_id,
        energy=energy,
        heat=heat,
        hot_cell=hot_cell,
        health=str(data["health"]) if data.get("health") is not None else None,
        geometry_state=str(data["geometry_state"]) if data.get("geometry_state") is not None else None,
        residual=residual,
        surprise=surprise,
        deposits=deposits,
        last_seen=last_seen,
        status=str(data["status"]) if data.get("status") is not None else None,
    )


def compatibility_note(from_version: str, to_version: str = SCHEMA_VERSION) -> str:
    if from_version == to_version:
        return "identical"
    if from_version.startswith("1.") and to_version.startswith("2."):
        return (
            "v1→v2: intensity/heat may be present but energy is only set when "
            "a genuine source supplied it; observed_at/ingested_at split; "
            "observation_id required; provenance explicit."
        )
    return f"unknown migration path {from_version} → {to_version}"
