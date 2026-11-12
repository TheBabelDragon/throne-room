"""Associative memory — experience-oriented records for Qwuack.

Extends existing SELF / agent MemoryStore concepts. Append-only.
A remembered action is not permission. A hypothesis is not an observation.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from agent.hashutil import uid


class MemoryType(str, Enum):
    OBSERVATION = "OBSERVATION"
    CHANGE = "CHANGE"
    HYPOTHESIS = "HYPOTHESIS"
    PREDICTION = "PREDICTION"
    ACTION = "ACTION"
    CONSEQUENCE = "CONSEQUENCE"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    LESSON = "LESSON"
    VERIFIED_RESULT = "VERIFIED_RESULT"


@dataclass
class MemoryRecord:
    memory_id: str
    episode_id: str
    memory_type: MemoryType
    content: str
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_provenance: str = ""
    creation_sequence: int = 0
    related_memory_ids: list[str] = field(default_factory=list)
    body_id: str | None = None
    observation_id: str | None = None
    originating_tick: int | None = None
    created_at: float = 0.0
    superseded_by: str | None = None
    conflicts_with: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["memory_type"] = self.memory_type.value
        return d

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "MemoryRecord":
        mt = obj.get("memory_type") or "OBSERVATION"
        try:
            memory_type = MemoryType(str(mt))
        except ValueError:
            memory_type = MemoryType.OBSERVATION
        return cls(
            memory_id=str(obj.get("memory_id") or uid("amem")),
            episode_id=str(obj.get("episode_id") or ""),
            memory_type=memory_type,
            content=str(obj.get("content") or ""),
            evidence_refs=list(obj.get("evidence_refs") or []),
            confidence=float(obj.get("confidence") if obj.get("confidence") is not None else 0.5),
            source_provenance=str(obj.get("source_provenance") or ""),
            creation_sequence=int(obj.get("creation_sequence") or 0),
            related_memory_ids=list(obj.get("related_memory_ids") or []),
            body_id=obj.get("body_id"),
            observation_id=obj.get("observation_id"),
            originating_tick=obj.get("originating_tick"),
            created_at=float(obj.get("created_at") or 0),
            superseded_by=obj.get("superseded_by"),
            conflicts_with=list(obj.get("conflicts_with") or []),
        )


class AssociativeMemory:
    """Append-only experience store. Not an authority channel."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path("/tmp/metafield/associative_memory.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[MemoryRecord] = []
        self._seq = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        loaded: list[MemoryRecord] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rec = MemoryRecord.from_dict(obj)
                    loaded.append(rec)
                    self._seq = max(self._seq, rec.creation_sequence)
        except OSError:
            return
        self.records = loaded[-5000:]

    def _persist(self, rec: MemoryRecord) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.as_dict(), sort_keys=True) + "\n")
        except OSError:
            pass

    def append(
        self,
        *,
        episode_id: str,
        memory_type: MemoryType | str,
        content: str,
        evidence_refs: list[str] | None = None,
        confidence: float = 0.5,
        source_provenance: str = "",
        body_id: str | None = None,
        observation_id: str | None = None,
        originating_tick: int | None = None,
        related_memory_ids: list[str] | None = None,
        memory_id: str | None = None,
    ) -> MemoryRecord:
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)
        self._seq += 1
        rec = MemoryRecord(
            memory_id=memory_id or uid("amem"),
            episode_id=episode_id,
            memory_type=memory_type,
            content=content,
            evidence_refs=list(evidence_refs or []),
            confidence=float(confidence),
            source_provenance=source_provenance,
            creation_sequence=self._seq,
            related_memory_ids=list(related_memory_ids or []),
            body_id=body_id,
            observation_id=observation_id,
            originating_tick=originating_tick,
            created_at=time.time(),
        )
        self.records.append(rec)
        if len(self.records) > 5000:
            self.records = self.records[-5000:]
        self._persist(rec)
        return rec

    def by_body(self, body_id: str, limit: int = 20) -> list[MemoryRecord]:
        out = [r for r in self.records if r.body_id == body_id]
        return out[-limit:]

    def by_episode(self, episode_id: str) -> list[MemoryRecord]:
        return [r for r in self.records if r.episode_id == episode_id]

    def by_type(self, memory_type: MemoryType | str, limit: int = 50) -> list[MemoryRecord]:
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)
        out = [r for r in self.records if r.memory_type == memory_type]
        return out[-limit:]

    def by_observation(self, observation_id: str) -> list[MemoryRecord]:
        return [r for r in self.records if r.observation_id == observation_id]

    def mark_conflict(self, memory_id: str, other_id: str) -> None:
        for r in self.records:
            if r.memory_id == memory_id and other_id not in r.conflicts_with:
                r.conflicts_with.append(other_id)
            if r.memory_id == other_id and memory_id not in r.conflicts_with:
                r.conflicts_with.append(memory_id)

    def supersede(self, old_id: str, new_id: str) -> None:
        for r in self.records:
            if r.memory_id == old_id:
                r.superseded_by = new_id
                break

    def reconstruct_episode(self, episode_id: str) -> list[MemoryRecord]:
        rows = self.by_episode(episode_id)
        return sorted(rows, key=lambda r: r.creation_sequence)

    def retrieve_relevant(
        self,
        *,
        body_id: str | None = None,
        query: str = "",
        limit: int = 8,
    ) -> list[MemoryRecord]:
        pool = list(self.records)
        if body_id:
            pool = [r for r in pool if r.body_id == body_id] or pool
        q = query.strip().lower()
        if not q:
            return pool[-limit:]
        tokens = q.split()
        scored: list[tuple[int, MemoryRecord]] = []
        for r in pool:
            text = (r.content + " " + " ".join(r.evidence_refs)).lower()
            score = sum(1 for t in tokens if t in text)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: (-x[0], -x[1].creation_sequence))
        return [r for _, r in scored[:limit]]
