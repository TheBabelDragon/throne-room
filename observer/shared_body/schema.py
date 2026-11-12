"""SHARED_BODY schema v2 — versioned, validated, provenance-preserving.

Rules (locked):
- Stable identity across observations (body_id never from array position).
- No fabricated intensities, temperatures, positions, or energy.
- Missing values remain missing (None / omitted).
- observed_at and ingested_at are distinct.
- Original measurement provenance is preserved.
- Malformed records are rejected with actionable diagnostics.
- Unknown optional fields do not silently corrupt existing records.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "2.0"
SCHEMA_TYPE = "SHARED_BODY"

KNOWN_BODY_TYPES = frozenset(
    {
        "optical",
        "lattice",
        "wifi_csi",
        "ultrasonic",
        "zvs",
        "hall",
        "sim",
        "other",
    }
)

BUS_NODE_REGISTRY: dict[int, str] = {
    0x01: "host",
    0x02: "optical",
    0x03: "hall-sensor",
    0x04: "actuator",
    0x05: "compute",
    0x06: "expansion",
}

_BODY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$")


class SharedBodyError(Exception):
    """Base for SHARED_BODY errors."""


class SharedBodyValidationError(SharedBodyError):
    """Malformed or incomplete record. Message is actionable."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def make_observation_id(
    body_id: str,
    observed_at: str,
    source_system: str,
    regions_fingerprint: str = "",
) -> str:
    """Deterministic observation_id from identity + time + source.

    Never derived from array position. Stable under identical inputs.
    """
    raw = f"{body_id}|{observed_at}|{source_system}|{regions_fingerprint}"
    return "obs_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def bus_node_to_body_id(node_id: int, instance: int | None = None) -> str:
    role = BUS_NODE_REGISTRY.get(int(node_id) & 0xFF, f"node-{int(node_id) & 0xFF:02x}")
    if instance is None:
        return role
    return f"{role}-{int(instance):02d}"


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
