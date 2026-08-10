#!/usr/bin/env python3
"""
MetaField observation path

Listens for real wifi_csi (UDP :4210) and/or JSONL, expands to the
canonical MetaField FieldObservation schema, and writes JSONL that
optical_serial_consumer.py can promote into FieldMemoryEntry.

Path:

  CYD / bridge → UDP :4210 → this bridge → JSONL
       → metafield/optical_serial_consumer.py --file … --follow --save …

Usage:

  python -m observer.metafield_bridge --udp --out /tmp/metafield/csi.jsonl
  python -m observer.metafield_bridge --file raw.jsonl --out /tmp/metafield/csi.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .ingest import parse_line, udp_lines, tail_file, _from_wifi_csi
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ingest import parse_line, udp_lines, tail_file, _from_wifi_csi  # type: ignore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def flat_obs_to_metafield_packet(rows: list) -> dict | None:
    """Collapse flat Throne rows that share body_id/timestamp into one MetaField packet."""
    if not rows:
        return None
    body_id = rows[0].body_id
    ts = rows[0].timestamp or _now()
    regions = []
    for r in rows:
        regions.append(
            {
                "region": r.region,
                "observed": float(r.value),
                "expected": None,
                "confidence": float(r.confidence),
                "anomaly": 0.0,
            }
        )
    meta = rows[0].meta or {}
    return {
        "schema_version": 1,
        "body_id": body_id,
        "body_type": "wifi_csi",
        "excitation_id": None,
        "field_regions": regions,
        "geometry_state": "calibrated",
        "timestamp": ts if not isinstance(ts, (int, float)) else _now(),
        "modality": {"wifi_csi": meta},
        "health": "ok",
    }


def wifi_csi_dict_to_metafield(data: dict) -> dict:
    """Direct wifi_csi JSON → canonical MetaField FieldObservation."""
    rows = _from_wifi_csi(data)
    packet = flat_obs_to_metafield_packet(rows)
    if packet is None:
        return {
            "schema_version": 1,
            "body_id": str(data.get("node") or "csi-unknown"),
            "body_type": "wifi_csi",
            "excitation_id": None,
            "field_regions": [],
            "geometry_state": "unknown",
            "timestamp": _now(),
            "modality": {"wifi_csi": {"error": "empty_expand"}},
            "health": "error",
        }
    # keep raw subcarriers in modality for later geometry / replay
    csi = data.get("csi") or []
    packet["modality"] = {
        "wifi_csi": {
            "rssi_dbm": data.get("rssi"),
            "subcarriers": len(csi),
            "csi": csi,
            "node": data.get("node"),
            "device_timestamp": data.get("timestamp"),
        }
    }
    return packet


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CSI / body streams → MetaField FieldObservation JSONL"
    )
    parser.add_argument(
        "--udp", type=int, nargs="?", const=4210, default=None,
        help="Listen UDP (default 4210)",
    )
    parser.add_argument(
        "--file", "-f", type=Path, action="append", default=[],
        help="Input JSONL (wifi_csi or flat FO)",
    )
    parser.add_argument(
        "--from-start", action="store_true",
        help="Read existing file content first",
    )
    parser.add_argument(
        "--out", "-o", type=Path, required=True,
        help="Output JSONL path for MetaField consumer",
    )
    parser.add_argument(
        "--stdin", action="store_true", help="Also read stdin",
    )
    args = parser.parse_args()

    if args.udp is None and not args.file and not args.stdin:
        args.udp = 4210

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out = args.out.open("a", encoding="utf-8")
    count = 0

    def raw_lines():
        if args.udp is not None:
            yield from udp_lines(port=args.udp)
        for p in args.file:
            yield from tail_file(p, from_start=args.from_start)
        if args.stdin or (not args.file and args.udp is None):
            for line in sys.stdin:
                yield line

    print(f"[metafield-bridge] writing → {args.out}", flush=True)
    if args.udp is not None:
        print(f"[metafield-bridge] UDP :{args.udp}", flush=True)

    try:
        for line in raw_lines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue

            if data.get("type") == "wifi_csi" or ("csi" in data and "node" in data):
                packet = wifi_csi_dict_to_metafield(data)
            elif "field_regions" in data and "body_id" in data:
                packet = data
            else:
                rows = parse_line(line)
                packet = flat_obs_to_metafield_packet(rows)
                if packet is None:
                    continue

            out.write(json.dumps(packet, separators=(",", ":")) + "\n")
            out.flush()
            count += 1
            if count % 25 == 0:
                print(
                    f"[metafield-bridge] {count} packets  "
                    f"last={packet.get('body_id')}  "
                    f"regions={len(packet.get('field_regions') or [])}",
                    flush=True,
                )
    except KeyboardInterrupt:
        print(f"\n[metafield-bridge] stopped after {count} packets", flush=True)
    finally:
        out.close()


if __name__ == "__main__":
    main()
