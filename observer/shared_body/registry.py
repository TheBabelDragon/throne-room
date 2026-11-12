"""Persistent SHARED_BODY registry — outside FieldTick."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .schema import SharedBody, SharedBodyValidationError, validate_shared_body

DEFAULT_DIR = Path("/tmp/metafield/shared_body")
SNAPSHOT_NAME = "snapshot.json"
JOURNAL_NAME = "observations.jsonl"
ALIVE_S = 8.0
STALE_S = 30.0


def _status_for(last_seen: float | None, now: float | None = None) -> str:
    if last_seen is None:
        return "MISSING"
    t = now if now is not None else time.time()
    age = t - float(last_seen)
    if age <= ALIVE_S:
        return "ALIVE"
    if age <= STALE_S:
        return "STALE"
    return "TIMEOUT"


class SharedBodyRegistry:
    def __init__(self, root: Path | str | None = None, *, auto_persist: bool = True):
        self.root = Path(root) if root else DEFAULT_DIR
        self.auto_persist = auto_persist
        self._bodies: dict[str, SharedBody] = {}
        self._seen_obs: set[str] = set()
        self.root.mkdir(parents=True, exist_ok=True)
        self._load()

    @property
    def snapshot_path(self) -> Path:
        return self.root / SNAPSHOT_NAME

    @property
    def journal_path(self) -> Path:
        return self.root / JOURNAL_NAME

    def _load(self) -> None:
        if self.snapshot_path.exists():
            try:
                data = json.loads(self.snapshot_path.read_text())
                bodies = data.get("bodies") or data.get("records") or []
                if isinstance(bodies, dict):
                    bodies = list(bodies.values())
                for raw in bodies:
                    try:
                        b = validate_shared_body(raw)
                        self._bodies[b.body_id] = b
                        self._seen_obs.add(b.observation_id)
                    except SharedBodyValidationError:
                        continue
            except Exception:
                pass
        if self.journal_path.exists():
            try:
                with self.journal_path.open() as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            raw = json.loads(line)
                            b = validate_shared_body(raw)
                            self._bodies[b.body_id] = b
                            self._seen_obs.add(b.observation_id)
                        except Exception:
                            continue
            except Exception:
                pass

    def register(self, body: SharedBody) -> tuple[bool, str]:
        if body.observation_id in self._seen_obs:
            return False, "duplicate_observation_id"
        if body.last_seen is None:
            body.last_seen = time.time()
        body.status = _status_for(body.last_seen)
        self._bodies[body.body_id] = body
        self._seen_obs.add(body.observation_id)
        if self.auto_persist:
            try:
                self._append_journal(body)
                self._write_snapshot()
            except Exception as e:
                return True, f"registered_persist_failed:{e}"
        return True, "ok"

    def get(self, body_id: str) -> Optional[SharedBody]:
        return self._bodies.get(body_id)

    def all(self) -> list[SharedBody]:
        now = time.time()
        out = []
        for b in self._bodies.values():
            b.status = _status_for(b.last_seen, now)
            out.append(b)
        return out

    def counts(self) -> dict[str, int]:
        now = time.time()
        total = alive = stale = timeout = missing = 0
        for b in self._bodies.values():
            total += 1
            st = _status_for(b.last_seen, now)
            b.status = st
            if st == "ALIVE":
                alive += 1
            elif st == "STALE":
                stale += 1
            elif st == "TIMEOUT":
                timeout += 1
            else:
                missing += 1
        return {"total": total, "alive": alive, "stale": stale, "timeout": timeout, "missing": missing}

    def _append_journal(self, body: SharedBody) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a") as f:
            f.write(json.dumps(body.to_dict(), separators=(",", ":")) + "\n")

    def _write_snapshot(self) -> None:
        now = time.time()
        bodies = []
        for b in self._bodies.values():
            b.status = _status_for(b.last_seen, now)
            bodies.append(b.to_dict())
        payload = {
            "type": "SHARED_BODY_SNAPSHOT",
            "schema_version": "2.0",
            "written_at": now,
            "n_bodies": len(bodies),
            "bodies": bodies,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.snapshot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.snapshot_path)
