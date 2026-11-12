"""SHARED_BODY export contracts (snapshot, JSONL, Reverie)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_SNAPSHOT_PATH = Path("/tmp/metafield/shared_body/snapshot.json")
DEFAULT_JOURNAL_PATH = Path("/tmp/metafield/shared_body/observations.jsonl")
DEFAULT_REVERIE_PATH = Path("/tmp/metafield/shared_bodies_reverie.json")


def write_snapshot(registry: Any, path: Path | None = None) -> Path:
    path = path or DEFAULT_SNAPSHOT_PATH
    registry._write_snapshot()
    return registry.snapshot_path


def write_observation_jsonl(body: Any, path: Path | None = None) -> Path:
    path = path or DEFAULT_JOURNAL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(body.to_dict(), separators=(",", ":")) + "\n")
    return path


def snapshot_to_reverie(
    registry: Any | None = None,
    path: Path | None = None,
    bodies: list[Any] | None = None,
) -> Path:
    path = path or DEFAULT_REVERIE_PATH
    if bodies is None:
        bodies = [] if registry is None else registry.all()
    items = []
    for b in bodies:
        d = b.to_dict() if hasattr(b, "to_dict") else dict(b)
        intensity = d.get("energy")
        if intensity is None:
            intensity = d.get("heat")
        items.append({
            "id": d.get("body_id"),
            "intensity": intensity,
            "isVerified": not bool((d.get("provenance") or {}).get("synthetic")),
            "status": d.get("status"),
            "observation_id": d.get("observation_id"),
            "body_type": d.get("body_type"),
        })
    payload = {"type": "REVERIE_BODY_SET", "schema_version": "2.0", "bodies": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path
