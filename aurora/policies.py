"""
Autonomous decision policies over observation digests + recent CSI.

Outputs *intent* only. Dispatch is gated by RedisControl.snapshot().allowed.
Tails a full fine-measurement window — not a placeholder line count.

Multi-head aware: uses head_fused_* / head_entropy regions when the bridge
has enriched CSI packets.
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


def _tail_csi_series(
    jsonl: Path, max_lines: int = POLICY_TAIL_LINES
) -> dict[str, dict[str, list[float]]]:
    """body_id → {metric: recent values} over the fine window."""
    if not jsonl.exists():
        return {}
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
            text_lines = [
                ln.decode("utf-8", errors="replace") for ln in data.splitlines()[-max_lines:]
            ]
    except OSError:
        return {}

    series: dict[str, dict[str, list[float]]] = {}
    interesting = {
        "csi_mean", "csi_energy", "csi_spread", "csi_peak",
        "head_fused_mean", "head_fused_energy", "head_fused_spread",
        "head_entropy", "head_dominant",
    }
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
        bucket = series.setdefault(body, {})
        for r in pkt.get("field_regions") or []:
            if not isinstance(r, dict):
                continue
            name = str(r.get("region") or "")
            if name not in interesting:
                continue
            try:
                val = float(r.get("observed"))
            except (TypeError, ValueError):
                continue
            bucket.setdefault(name, []).append(val)
        if pkt.get("region") in interesting:
            try:
                bucket.setdefault(str(pkt["region"]), []).append(float(pkt.get("value")))
            except (TypeError, ValueError):
                pass
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

    series = _tail_csi_series(csi_jsonl)
    for body_id, metrics in series.items():
        means = metrics.get("csi_mean") or metrics.get("head_fused_mean") or []
        energies = metrics.get("csi_energy") or metrics.get("head_fused_energy") or []
        spreads = metrics.get("csi_spread") or metrics.get("head_fused_spread") or []
        ents = metrics.get("head_entropy") or []
        if len(means) < 8 and len(energies) < 8:
            continue
        vals = energies if len(energies) >= len(means) else means
        recent_n = max(8, len(vals) // 4)
        recent = vals[-recent_n:]
        mean = sum(recent) / len(recent)
        peak = max(recent)
        span = max(recent) - min(recent)
        ent = (sum(ents[-recent_n:]) / len(ents[-recent_n:])) if ents else 0.5

        if mean < 0.15 and span < 0.05:
            continue

        # multi-head: low entropy + high peak → concentrated band anomaly
        if peak >= 0.75 or (mean >= 0.55 and span >= 0.2):
            pri = min(1.0, 0.5 + peak * 0.4)
            if ent < 0.3 and peak >= 0.6:
                pri = min(1.0, pri + 0.12)  # focused head → more confident probe
            intents.append(
                Intent(
                    action="probe",
                    priority=pri,
                    reason=(
                        f"elevated CSI peak={peak:.2f} mean={mean:.2f} "
                        f"ent={ent:.2f} n={len(recent)}"
                    ),
                    body_id=body_id,
                    params={
                        "focus": "multi_head" if ents else "csi_energy",
                        "peak": peak,
                        "mean": mean,
                        "entropy": ent,
                        "samples": len(recent),
                    },
                )
            )
        elif span >= 0.25 or (ent > 0.7 and span >= 0.15):
            # high routing entropy + variance → attention
            intents.append(
                Intent(
                    action="attention",
                    priority=0.45 + min(0.3, span),
                    reason=f"CSI variance span={span:.2f} ent={ent:.2f} n={len(recent)}",
                    body_id=body_id,
                    params={"span": span, "entropy": ent, "samples": len(recent)},
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
