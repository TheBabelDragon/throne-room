"""
SHARED_BODY — canonical cross-feed body record.

One shape for Throne Room, MetaField, Reverie, and Field Bus consumers.
Built from real FieldObservation regions + FieldCube heat + head residual.
No synthetic intensities; missing fields stay null/false, not invented.

See docs/SHARED_BODY.md for the identifier registry.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SHARED_BODIES = Path("/tmp/metafield/shared_bodies.json")
DEFAULT_HEAD_STATE = Path("/tmp/metafield/head_state.json")

# Field Bus role IDs (protocol/can_ids.h) → string body_id prefix
BUS_NODE_REGISTRY: dict[int, str] = {
    0x01: "host",
    0x02: "optical",
    0x03: "hall-sensor",
    0x04: "actuator",
    0x05: "compute",
    0x06: "expansion",
}

# body_type values accepted by MetaField FO schema
KNOWN_BODY_TYPES = frozenset(
    {"optical", "lattice", "wifi_csi", "ultrasonic", "zvs", "hall", "sim", "other"}
)

# Region names already live on the CSI path
CSI_REGION_NAMES = (
    "rssi",
    "csi_mean",
    "csi_peak",
    "csi_energy",
    "csi_spread",
    "head_fused_mean",
    "head_fused_energy",
    "head_fused_spread",
    "head_entropy",
    "head_dominant",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def bus_node_to_body_id(node_id: int, instance: int | None = None) -> str:
    """Map Field Bus numeric ID to a stable string body_id."""
    role = BUS_NODE_REGISTRY.get(int(node_id) & 0xFF, f"node-{int(node_id) & 0xFF:02x}")
    if instance is None:
        return role
    return f"{role}-{int(instance):02d}"


def body_id_to_bus_node(body_id: str) -> int | None:
    """Best-effort reverse lookup. Returns None if unknown."""
    if not body_id:
        return None
    lower = body_id.lower()
    for nid, role in BUS_NODE_REGISTRY.items():
        if lower == role or lower.startswith(role + "-"):
            return nid
    # explicit hex form e.g. "bus-0x03"
    if lower.startswith("bus-0x"):
        try:
            return int(lower.split("0x", 1)[1], 16) & 0xFF
        except ValueError:
            return None
    return None


def infer_body_type(body_id: str, regions: dict[str, float] | None = None) -> str:
    """Infer body_type from id / region vocabulary when not supplied."""
    bid = (body_id or "").lower()
    regs = regions or {}
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
    return "other"


@dataclass
class SharedBody:
    """Canonical body record for cross-system feed."""

    schema_version: int = 1
    type: str = "SHARED_BODY"
    body_id: str = ""
    body_type: str = "other"
    bus_node_id: int | None = None
    regions: dict[str, float] = field(default_factory=dict)
    heat: float = 0.0
    hot_cell: list[int] | None = None
    intensity: float = 0.0
    direction: dict[str, float] | None = None
    is_verified: bool = False
    health: str = "unknown"
    geometry_state: str = "unknown"
    last_seen: float | None = None
    deposits: int = 0
    residual: float | None = None
    surprise: bool = False
    pressure_contrib: float | None = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # drop pure-null noise for cleaner JSON
        if d.get("direction") is None:
            del d["direction"]
        if d.get("hot_cell") is None:
            del d["hot_cell"]
        if d.get("bus_node_id") is None:
            del d["bus_node_id"]
        if d.get("residual") is None:
            del d["residual"]
        if d.get("pressure_contrib") is None:
            del d["pressure_contrib"]
        if d.get("last_seen") is None:
            del d["last_seen"]
        return d


def _intensity_from_regions(regions: dict[str, float], heat: float) -> float:
    """Prefer fused energy / heat; never invent."""
    for key in ("head_fused_energy", "csi_energy", "csi_peak", "csi_mean"):
        if key in regions:
            return _clip01(float(regions[key]))
    if heat > 0:
        return _clip01(heat)
    return 0.0


def _direction_from_hot_cell(hot_cell: tuple[int, int, int] | list[int] | None) -> dict[str, float] | None:
    """Map 3×3×3 hot cell to a unit-ish direction in [-1, 1]^3."""
    if not hot_cell or len(hot_cell) != 3:
        return None
    z, y, x = (int(hot_cell[0]), int(hot_cell[1]), int(hot_cell[2]))
    return {
        "x": (x - 1) / 1.0,
        "y": (y - 1) / 1.0,
        "z": (z - 1) / 1.0,
    }


def build_shared_body(
    *,
    body_id: str,
    regions: dict[str, float] | None = None,
    body_type: str | None = None,
    bus_node_id: int | None = None,
    heat: float = 0.0,
    hot_cell: tuple[int, int, int] | list[int] | None = None,
    deposits: int = 0,
    last_seen: float | None = None,
    health: str = "ok",
    geometry_state: str = "unknown",
    residual: float | None = None,
    surprise: bool = False,
    is_verified: bool | None = None,
) -> SharedBody:
    regs = {k: _clip01(float(v)) for k, v in (regions or {}).items()}
    btype = body_type or infer_body_type(body_id, regs)
    if btype not in KNOWN_BODY_TYPES:
        btype = "other"
    bus_id = bus_node_id if bus_node_id is not None else body_id_to_bus_node(body_id)
    heat_c = _clip01(heat)
    intensity = _intensity_from_regions(regs, heat_c)
    direction = _direction_from_hot_cell(hot_cell)
    verified = (
        bool(is_verified)
        if is_verified is not None
        else (health == "ok" and geometry_state in {"calibrated", "unknown"} and intensity > 0.02)
    )
    return SharedBody(
        body_id=body_id,
        body_type=btype,
        bus_node_id=bus_id,
        regions=regs,
        heat=heat_c,
        hot_cell=list(hot_cell) if hot_cell is not None else None,
        intensity=intensity,
        direction=direction,
        is_verified=verified,
        health=health,
        geometry_state=geometry_state,
        last_seen=last_seen if last_seen is not None else time.time(),
        deposits=int(deposits),
        residual=None if residual is None else _clip01(float(residual)),
        surprise=bool(surprise),
    )


def bodies_from_cube_snapshot(
    field_snap: dict[str, Any],
    *,
    region_cache: dict[str, dict[str, float]] | None = None,
    head_snap: dict[str, Any] | None = None,
    health: str = "ok",
) -> list[SharedBody]:
    """Build SHARED_BODY list from FieldCubeEnsemble.snapshot() + optional region cache."""
    bodies_meta = (field_snap or {}).get("bodies") or {}
    region_cache = region_cache or {}
    head = head_snap or {}
    residual = head.get("abs_residual")
    surprise = bool(head.get("surprise"))
    out: list[SharedBody] = []
    for body_id, meta in bodies_meta.items():
        if not body_id:
            continue
        regs = dict(region_cache.get(body_id) or {})
        heat = float(meta.get("heat") or 0.0)
        hot = meta.get("hot_cell")
        deposits = int(meta.get("deposits") or 0)
        age_s = meta.get("age_s")
        last_seen = time.time() - float(age_s) if age_s is not None else time.time()
        out.append(
            build_shared_body(
                body_id=str(body_id),
                regions=regs,
                heat=heat,
                hot_cell=hot,
                deposits=deposits,
                last_seen=last_seen,
                health=health,
                residual=float(residual) if residual is not None else None,
                surprise=surprise,
            )
        )
    return out


def bodies_from_fo_packets(
    packets: list[dict[str, Any]],
    *,
    field_snap: dict[str, Any] | None = None,
    head_snap: dict[str, Any] | None = None,
) -> list[SharedBody]:
    """Collapse recent FO / bridge packets into per-body SHARED_BODY records."""
    by_id: dict[str, dict[str, Any]] = {}
    for pkt in packets:
        if not isinstance(pkt, dict):
            continue
        body_id = str(pkt.get("body_id") or "")
        if not body_id:
            continue
        slot = by_id.setdefault(
            body_id,
            {
                "regions": {},
                "body_type": pkt.get("body_type"),
                "health": pkt.get("health") or "ok",
                "geometry_state": pkt.get("geometry_state") or "unknown",
                "last_seen": time.time(),
            },
        )
        if pkt.get("body_type"):
            slot["body_type"] = pkt["body_type"]
        if pkt.get("health"):
            slot["health"] = pkt["health"]
        if pkt.get("geometry_state"):
            slot["geometry_state"] = pkt["geometry_state"]
        for r in pkt.get("field_regions") or []:
            if not isinstance(r, dict):
                continue
            name = str(r.get("region") or "")
            if not name:
                continue
            try:
                slot["regions"][name] = float(r.get("observed") or 0.0)
            except (TypeError, ValueError):
                continue
        # also accept flat region/value FO
        if pkt.get("region") and "value" in pkt:
            try:
                slot["regions"][str(pkt["region"])] = float(pkt["value"])
            except (TypeError, ValueError):
                pass

    cube_bodies = ((field_snap or {}).get("bodies") or {}) if field_snap else {}
    head = head_snap or {}
    residual = head.get("abs_residual")
    surprise = bool(head.get("surprise"))
    out: list[SharedBody] = []
    seen = set()
    for body_id, slot in by_id.items():
        meta = cube_bodies.get(body_id) or {}
        out.append(
            build_shared_body(
                body_id=body_id,
                regions=slot["regions"],
                body_type=slot.get("body_type"),
                heat=float(meta.get("heat") or 0.0),
                hot_cell=meta.get("hot_cell"),
                deposits=int(meta.get("deposits") or 0),
                last_seen=slot.get("last_seen"),
                health=str(slot.get("health") or "ok"),
                geometry_state=str(slot.get("geometry_state") or "unknown"),
                residual=float(residual) if residual is not None else None,
                surprise=surprise,
            )
        )
        seen.add(body_id)
    # include cube-only bodies that had no recent packet
    for body_id, meta in cube_bodies.items():
        if body_id in seen:
            continue
        out.append(
            build_shared_body(
                body_id=str(body_id),
                regions={},
                heat=float(meta.get("heat") or 0.0),
                hot_cell=meta.get("hot_cell"),
                deposits=int(meta.get("deposits") or 0),
                residual=float(residual) if residual is not None else None,
                surprise=surprise,
            )
        )
    return out


def write_shared_bodies(
    bodies: list[SharedBody],
    path: Path = DEFAULT_SHARED_BODIES,
    *,
    pressure: float | None = None,
    n_bodies: int | None = None,
) -> dict[str, Any]:
    """Write envelope + body list for Reverie / external consumers."""
    envelope = {
        "schema_version": 1,
        "type": "SHARED_BODY_SET",
        "timestamp": _now_iso(),
        "source": "throne-room.shared_body",
        "pressure": None if pressure is None else round(float(pressure), 4),
        "n_bodies": n_bodies if n_bodies is not None else len(bodies),
        "bodies": [b.to_dict() for b in bodies],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, indent=2))
    return envelope


def read_head_snap(path: Path = DEFAULT_HEAD_STATE) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if data.get("type") == "HEAD_STATE" else {}
    except Exception:
        return {}


def export_from_digest_inputs(
    *,
    packets: list[dict[str, Any]],
    field_snap: dict[str, Any] | None,
    head_snap: dict[str, Any] | None = None,
    path: Path = DEFAULT_SHARED_BODIES,
) -> dict[str, Any]:
    """One-shot: packets + cube snapshot → shared_bodies.json."""
    head = head_snap if head_snap is not None else read_head_snap()
    bodies = bodies_from_fo_packets(packets, field_snap=field_snap, head_snap=head)
    pressure = (field_snap or {}).get("pressure")
    return write_shared_bodies(
        bodies,
        path,
        pressure=float(pressure) if pressure is not None else None,
        n_bodies=(field_snap or {}).get("n_bodies"),
    )
