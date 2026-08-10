"""
Autonomous decision policies over observation digests + recent CSI.

Outputs *intent* only. Dispatch is gated by RedisControl.snapshot().allowed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _tail_csi_means(jsonl: Path, max_lines: int = 40) -> dict[str, list[float]]:
    """body_id → recent csi_mean (or observed) values."""
    if not jsonl.exists():
        return {}
    lines: list[str] = []
    try:
        with jsonl.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = 8192
            data = b""
            while size > 0 and len(lines) < max_lines + 5:
                read = min(block, size)
                size -= read
                f.seek(size)
                data = f.read(read) + data
                lines = data.splitlines()
            text_lines = [ln.decode("utf-8", errors="replace") for ln in lines[-max_lines:]]
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
        # MetaField canonical
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
        # flat FO fallback
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
    """Produce zero or more intents from current world state."""
    intents: list[Intent] = []
    digest = _read_json(digest_path) or {}
    health = str(digest.get("health") or "unknown")
    obs = digest.get("obs_path") or {}
    csi_lines = int(obs.get("csi_lines") or 0)
    children = digest.get("children") or {}

    # --- structural health ---
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

    # --- CSI dynamics ---
    series = _tail_csi_means(csi_jsonl)
    for body_id, vals in series.items():
        if len(vals) < 4:
            continue
        recent = vals[-8:]
        mean = sum(recent) / len(recent)
        peak = max(recent)
        span = max(recent) - min(recent)

        # quiet room → stay observe-ish
        if mean < 0.15 and span < 0.05:
            continue

        # high energy / motion-ish
        if peak >= 0.75 or (mean >= 0.55 and span >= 0.2):
            intents.append(
                Intent(
                    action="probe",
                    priority=min(1.0, 0.5 + peak * 0.4),
                    reason=f"elevated CSI peak={peak:.2f} mean={mean:.2f}",
                    body_id=body_id,
                    params={"focus": "csi_energy", "peak": peak, "mean": mean},
                )
            )
        elif span >= 0.25:
            intents.append(
                Intent(
                    action="attention",
                    priority=0.45 + min(0.3, span),
                    reason=f"CSI variance span={span:.2f}",
                    body_id=body_id,
                    params={"span": span},
                )
            )

    # mode filters
    if mode == "observe":
        return []
    if mode == "cautious":
        # only high-priority structural / strong peaks
        intents = [i for i in intents if i.priority >= 0.6 or i.action in {"hold", "scale_down"}]

    # de-dupe by action+body, keep highest priority
    best: dict[tuple[str, str | None], Intent] = {}
    for i in intents:
        key = (i.action, i.body_id)
        if key not in best or i.priority > best[key].priority:
            best[key] = i
    return sorted(best.values(), key=lambda x: -x.priority)
