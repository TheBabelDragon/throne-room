"""Append-only episodic memory. JSONL on disk, not a placeholder cap."""

from __future__ import annotations

import json
import time
from pathlib import Path

from agent.hashutil import uid
from agent.schemas import MemoryEntry

DEFAULT_PATH = Path("/tmp/metafield/agent_memory.jsonl")
MAX_LIVE = 2000


class MemoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.entries: list[MemoryEntry] = []

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        loaded: list[MemoryEntry] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                loaded.append(
                    MemoryEntry(
                        id=str(obj.get("id") or uid("mem")),
                        tick=int(obj.get("tick") or 0),
                        kind=str(obj.get("kind") or "episodic"),
                        text=str(obj.get("text") or ""),
                        tags=list(obj.get("tags") or []),
                        created_at=float(obj.get("created_at") or 0),
                        observation_id=obj.get("observation_id"),
                    )
                )
        except OSError:
            return
        self.entries = loaded[-MAX_LIVE:]

    def append(
        self,
        *,
        tick: int,
        text: str,
        kind: str = "episodic",
        tags: list[str] | None = None,
        observation_id: str | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=uid("mem"),
            tick=tick,
            kind=kind,
            text=text,
            tags=tags or [],
            created_at=time.time(),
            observation_id=observation_id,
        )
        self.entries.append(entry)
        if len(self.entries) > MAX_LIVE:
            self.entries = self.entries[-MAX_LIVE:]
        self._persist(entry)
        return entry

    def retrieve(self, query: str, limit: int = 6) -> list[MemoryEntry]:
        q = query.strip().lower()
        if not q:
            return self.entries[-limit:]
        scored: list[tuple[int, MemoryEntry]] = []
        tokens = q.split()
        for e in self.entries:
            hay = f"{e.text} {' '.join(e.tags)}".lower()
            score = sum(1 for t in tokens if t in hay)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda p: (-p[0], -p[1].tick))
        picked = [e for _, e in scored] if scored else self.entries[-limit:]
        return picked[:limit]

    def recent(self, limit: int = 8) -> list[MemoryEntry]:
        return list(reversed(self.entries[-limit:]))

    def _persist(self, entry: MemoryEntry) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "id": entry.id,
                    "tick": entry.tick,
                    "kind": entry.kind,
                    "text": entry.text,
                    "tags": entry.tags,
                    "created_at": entry.created_at,
                    "observation_id": entry.observation_id,
                    "schema": entry.schema,
                    "version": entry.version,
                }, separators=(",", ":")) + "\n")
        except OSError:
            pass
