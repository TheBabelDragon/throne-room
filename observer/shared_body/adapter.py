"""FieldObservation / CSI packet → SHARED_BODY converter.

Consumes existing FO packets only. No second UDP socket.
No fabricated energy. Missing stays missing.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .schema import (
    SCHEMA_VERSION,
    Measurement,
    Provenance,
    SharedBody,
    infer_body_type,
    make_observation_id,
    body_id_to_bus_node,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def from_field_observation_packet(
    packet: dict[str, Any],
    *,
    field_snap: dict[str, Any] | None = None,
    head_snap: dict[str, Any] | None = None,
    source_system: str = "throne-room.metafield_bridge",
) -> tuple[SharedBody | None, str]:
    if not isinstance(packet, dict):
        return None, "not_a_dict"

    body_id = (
        packet.get("body_id")
        or packet.get("node")
        or packet.get("source")
        or packet.get("device_id")
    )
    if not body_id:
        return None, "missing_body_id"
    body_id = str(body_id)

    observed_at = packet.get("timestamp") or packet.get("observed_at") or packet.get("t")
    observed_at = str(observed_at) if observed_at is not None else _now_iso()
    ingested_at = _now_iso()

    regions_raw = packet.get("regions") or []
    region_names: list[str] = []
    measurements: list[Measurement] = []
    energy: float | None = None

    if isinstance(regions_raw, list):
        for r in regions_raw:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or r.get("region") or "")
            if not name:
                continue
            region_names.append(name)
            observed = r.get("observed", r.get("value"))
            conf = r.get("confidence")
            val = _as_float(observed)
            conf_f = _as_float(conf)
            measurements.append(
                Measurement(region=name, value=val, confidence=conf_f, source_key=name)
            )
            if (name.endswith("energy") or name == "csi_energy") and val is not None:
                energy = val

    for k, v in packet.items():
        if k.startswith("csi_") or k in ("rssi", "rssi_dbm"):
            if k not in region_names:
                region_names.append(k)
                val = _as_float(v)
                measurements.append(Measurement(region=k, value=val, source_key=k))
                if k.endswith("energy") and val is not None:
                    energy = val

    fingerprint = ",".join(sorted(region_names))
    observation_id = make_observation_id(body_id, observed_at, source_system, fingerprint)

    synthetic = bool(packet.get("synthetic", False))
    provenance = Provenance(
        packet_type=str(packet.get("type") or "FieldObservation"),
        raw_node=str(packet.get("node") or body_id),
        device_timestamp=packet.get("device_timestamp") or packet.get("timestamp"),
        synthetic=synthetic,
        extra={k: packet[k] for k in ("rssi_dbm", "valid", "body_type") if k in packet},
    )

    body_type = str(packet.get("body_type") or infer_body_type(body_id, region_names))
    bus = body_id_to_bus_node(body_id)

    heat = residual = None
    hot_cell = deposits = None
    surprise = None
    if isinstance(field_snap, dict):
        heat = _as_float(field_snap.get("heat") or field_snap.get("pressure"))
        hc = field_snap.get("hot_cell")
        if isinstance(hc, (list, tuple)) and len(hc) == 3:
            try:
                hot_cell = [int(x) for x in hc]
            except (TypeError, ValueError):
                hot_cell = None
        deposits = field_snap.get("deposits")
        if deposits is not None:
            try:
                deposits = int(deposits)
            except (TypeError, ValueError):
                deposits = None
    if isinstance(head_snap, dict):
        residual = _as_float(head_snap.get("abs_residual") or head_snap.get("residual"))
        if "surprise" in head_snap:
            surprise = bool(head_snap.get("surprise"))

    body = SharedBody(
        body_id=body_id,
        schema_version=SCHEMA_VERSION,
        source_system=source_system,
        source_node_id=str(packet.get("node") or body_id),
        observation_id=observation_id,
        observed_at=observed_at,
        ingested_at=ingested_at,
        regions=region_names,
        measurements=measurements,
        provenance=provenance,
        body_type=body_type,
        bus_node_id=bus,
        energy=energy,
        heat=heat,
        hot_cell=hot_cell,
        residual=residual,
        surprise=surprise,
        deposits=deposits,
        last_seen=time.time(),
        status="ALIVE",
    )
    return body, "ok"


def ingest_packet(
    packet: dict[str, Any],
    registry: Any,
    *,
    field_snap: dict[str, Any] | None = None,
    head_snap: dict[str, Any] | None = None,
) -> tuple[Any, str]:
    body, reason = from_field_observation_packet(
        packet, field_snap=field_snap, head_snap=head_snap
    )
    if body is None:
        return None, reason
    ok, reg_reason = registry.register(body)
    if not ok:
        return None, reg_reason
    return body, reg_reason


def from_observation_rows(rows: list[dict[str, Any]], registry: Any, **kwargs: Any) -> list[Any]:
    out = []
    for row in rows:
        body, reason = ingest_packet(row, registry, **kwargs)
        if body is not None:
            out.append(body)
    return out
