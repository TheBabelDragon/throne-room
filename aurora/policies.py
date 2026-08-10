"""
Autonomous decision policies over observation digests + recent CSI.

Outputs *intent* only. Dispatch is gated by RedisControl.snapshot().allowed.
Tails a full fine-measurement window — not a placeholder line count.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from observer.measurement import POLICY_TAIL_LINES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Intent:
    action: str
    priority: float  # 0..1
    reason: str
    body_id: str | None = None
    params: dict[str, Any] | None = None

    def to_action(self, source: str = "aurora.action_layer") -> dict[str, Any]:
        return {
            "type": self.action,
            "action": self.action,
            "priority": round(self.priority, 3),
            "reason": self.reason,
            "body_id": self.body_id,
            "params": self.params or {},
            "timestamp": _now(),
            "source": source,
            "schema_version": 1,
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _tail_csi_means(
    jsonl: Path, max_lines: int = POLICY_TAIL_LINES
) -> dict[str, list[float]]:
    """body_id → recent csi_mean values over the fine window."""
    if not jsonl.exists():
        return {}
    lines: list[str] = []
    try:
        with jsonl.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = 65536
            data = b""
            target = max_lines * 256
            while size > 0 and len(data) < target:
                read = min(block, size)
                size -= read
                f.seek(size)
                data = f.read(read) + data
            lines = data.splitlines()
            text_lines = [
                ln.decode("utf-8", errors="replace") for ln in lines[-max_lines:]
            ]
    except OSError:
        return {}

    series: dict[str, list[float]] = {}
    for line in text_lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            pkt = json.loads(line)
        except json.JSONDecodeError:
            continue
        body = str(pkt.get("body_id") or "")
        if not body:
            continue
        regions = pkt.get("field_regions") or []
        val = None
        for r in regions:
            if isinstance(r, dict) and r.get("region") in {
                "csi_mean",
                "csi_energy",
                "csi_spread",
            }:
                try:
                    val = float(r.get("observed"))
                    if r.get("region") == "csi_mean":
                        break
                except (TypeError, ValueError):
                    pass
        if val is None and pkt.get("region") in {"csi_mean", "csi_energy"}:
            try:
                val = float(pkt.get("value"))
            except (TypeError, ValueError):
                val = None
        if val is None:
            continue
        series.setdefault(body, []).append(val)
    return series


def decide(
    *,
    digest_path: Path,
    csi_jsonl: Path,
    mode: str,
) -> list[Intent]:
    intents: list[Intent] = []
    digest = _read_json(digest_path) or {}
    health = str(digest.get("health") or "unknown")
    obs = digest.get("obs_path") or {}
    csi_lines = int(obs.get("csi_lines") or 0)
    children = digest.get("children") or {}

    bridge = children.get("metafield_bridge") or {}
    if not bridge.get("alive", True) and csi_lines == 0:
        intents.append(
            Intent(
                action="hold",
                priority=0.9,
                reason="bridge down and no CSI backlog",
            )
        )
        return intents

    if health == "degraded":
        intents.append(
            Intent(
                action="scale_down",
                priority=0.55,
                reason="obs path degraded",
                params={"factor": 0.7},
            )
        )

    host = digest.get("host") or {}
    if host.get("stressed"):
        advice = str(host.get("advice") or "scale_down")
        intents.append(
            Intent(
                action="hold" if advice == "hold" else "scale_down",
                priority=0.7 if advice == "hold" else 0.6,
                reason=f"host stress cpu={host.get('cpu_pct')} mem={host.get('mem_pct')}",
                params={"cpu_pct": host.get("cpu_pct"), "mem_pct": host.get("mem_pct")},
            )
        )

    field = digest.get("field") or {}
    pressure = float(field.get("pressure") or 0.0)
    if pressure >= 0.75:
        intents.append(
            Intent(
                action="probe",
                priority=min(1.0, 0.55 + pressure * 0.4),
                reason=f"field pressure={pressure:.3f}",
                params={"pressure": pressure, "n_bodies": field.get("n_bodies")},
            )
        )

    series = _tail_csi_means(csi_jsonl)
    for body_id, vals in series.items():
        if len(vals) < 8:
            continue
        recent_n = max(8, len(vals) // 4)
        recent = vals[-recent_n:]
        mean = sum(recent) / len(recent)
        peak = max(recent)
        span = max(recent) - min(recent)

        if mean < 0.15 and span < 0.05:
            continue

        if peak >= 0.75 or (mean >= 0.55 and span >= 0.2):
            intents.append(
                Intent(
                    action="probe",
                    priority=min(1.0, 0.5 + peak * 0.4),
                    reason=f"elevated CSI peak={peak:.2f} mean={mean:.2f} n={len(recent)}",
                    body_id=body_id,
                    params={
                        "focus": "csi_energy",
                        "peak": peak,
                        "mean": mean,
                        "samples": len(recent),
                    },
                )
            )
        elif span >= 0.25:
            intents.append(
                Intent(
                    action="attention",
                    priority=0.45 + min(0.3, span),
                    reason=f"CSI variance span={span:.2f} n={len(recent)}",
                    body_id=body_id,
                    params={"span": span, "samples": len(recent)},
                )
            )

    if mode == "observe":
        return []
    if mode == "cautious":
        intents = [
            i
            for i in intents
            if i.priority >= 0.6 or i.action in {"hold", "scale_down"}
        ]

    best: dict[tuple[str, str | None], Intent] = {}
    for i in intents:
        key = (i.action, i.body_id)
        if key not in best or i.priority > best[key].priority:
            best[key] = i
    return sorted(best.values(), key=lambda x: -x.priority)
