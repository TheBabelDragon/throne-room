"""Ingest backends for Throne Room (file, stdin, UDP).

Understands both:
  - FieldObservation  {body_id, region, value, ...}
  - wifi_csi          {node, rssi, csi[32], type: "wifi_csi"}  (ESP32 / CYD / gateway)
"""

from __future__ import annotations

import json
import math
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:
    from .models import Observation
except ImportError:
    from models import Observation  # type: ignore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rssi_norm(rssi: float) -> float:
    """Map typical WiFi RSSI (-90..-30) into 0..1."""
    return max(0.0, min(1.0, (float(rssi) + 90.0) / 60.0))


def _from_wifi_csi(data: dict) -> list[Observation]:
    """Expand a wifi_csi packet into FieldObservation rows."""
    node = str(data.get("node") or data.get("body_id") or "csi-unknown")
    ts = data.get("timestamp")
    if isinstance(ts, (int, float)):
        # millis uptime on device — stamp with host time for the view
        timestamp = _now_iso()
    else:
        timestamp = str(ts) if ts else _now_iso()

    rssi = float(data.get("rssi", -80))
    csi = data.get("csi") or []
    try:
        csi_vals = [float(x) for x in csi]
    except (TypeError, ValueError):
        csi_vals = []

    mean = sum(csi_vals) / len(csi_vals) if csi_vals else 0.0
    peak = max(csi_vals) if csi_vals else 0.0
    # simple energy + variance as motion-ish features
    energy = math.sqrt(sum(v * v for v in csi_vals) / len(csi_vals)) if csi_vals else 0.0
    if csi_vals and len(csi_vals) > 1:
        var = sum((v - mean) ** 2 for v in csi_vals) / len(csi_vals)
        spread = math.sqrt(var)
    else:
        spread = 0.0

    meta = {
        "source": "wifi_csi",
        "type": data.get("type", "wifi_csi"),
        "subcarriers": len(csi_vals),
    }

    return [
        Observation(timestamp, node, "rssi", _rssi_norm(rssi), 1.0, {**meta, "rssi_dbm": rssi}),
        Observation(timestamp, node, "csi_mean", max(0.0, min(1.0, mean)), 0.95, meta),
        Observation(timestamp, node, "csi_peak", max(0.0, min(1.0, peak)), 0.95, meta),
        Observation(timestamp, node, "csi_energy", max(0.0, min(1.0, energy)), 0.9, meta),
        Observation(timestamp, node, "csi_spread", max(0.0, min(1.0, spread * 2.0)), 0.85, meta),
    ]


def parse_line(line: str) -> list[Observation]:
    """Parse one JSON line into zero or more Observations."""
    line = line.strip()
    if not line:
        return []
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []

    if not isinstance(data, dict):
        return []

    # Canonical CSI from CYD / standard / ESP-NOW gateway
    if data.get("type") == "wifi_csi" or ("csi" in data and "node" in data):
        return _from_wifi_csi(data)

    # FieldObservation (already canonical)
    try:
        return [
            Observation(
                timestamp=str(data.get("timestamp", _now_iso())),
                body_id=str(data.get("body_id", "unknown")),
                region=str(data.get("region", "unknown")),
                value=float(data.get("value", 0.0)),
                confidence=float(data.get("confidence", 1.0)),
                meta=data.get("meta"),
            )
        ]
    except (TypeError, ValueError):
        return []


def tail_file(path: Path, from_start: bool = False) -> Iterator[str]:
    path = Path(path)
    while True:
        try:
            with path.open("r") as f:
                if not from_start:
                    f.seek(0, 2)
                else:
                    from_start = False
                while True:
                    line = f.readline()
                    if line:
                        yield line
                    else:
                        try:
                            if path.stat().st_size < f.tell():
                                f.seek(0)
                        except OSError:
                            break
                        time.sleep(0.04)
        except FileNotFoundError:
            time.sleep(0.3)
        except OSError:
            time.sleep(0.3)


def stdin_lines() -> Iterator[str]:
    for line in sys.stdin:
        yield line


def udp_lines(host: str = "0.0.0.0", port: int = 4210) -> Iterator[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    except OSError:
        pass
    try:
        sock.bind((host, port))
    except OSError as e:
        print(f"[udp] bind {host}:{port} failed: {e}", file=sys.stderr, flush=True)
        raise
    sock.settimeout(0.2)
    print(f"[udp] bound {host}:{port}", flush=True)
    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
                text = data.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    if line.strip():
                        yield line
            except socket.timeout:
                continue
    finally:
        sock.close()


def multi_source(
    files: list[Path] | None = None,
    use_stdin: bool = False,
    udp_port: int | None = None,
    from_start: bool = False,
) -> Iterator[Observation]:
    only_stdin = use_stdin and not files and udp_port is None
    if only_stdin:
        for line in stdin_lines():
            for obs in parse_line(line):
                yield obs
        return

    sources: list[Iterator[str]] = []

    if use_stdin and not sys.stdin.isatty():
        sources.append(stdin_lines())

    if files:
        for p in files:
            sources.append(tail_file(p, from_start=from_start))

    if udp_port is not None:
        sources.append(udp_lines(port=udp_port))

    if not sources:
        sources.append(stdin_lines())

    while True:
        made_progress = False
        for it in sources:
            try:
                line = next(it)
                for obs in parse_line(line):
                    yield obs
                    made_progress = True
            except StopIteration:
                continue
        if not made_progress:
            time.sleep(0.03)
