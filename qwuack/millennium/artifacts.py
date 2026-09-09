"""Progress the Duck may keep. Victory is not one of the kinds."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


DESK_DIR = Path("/tmp/metafield")
MEMORY_PATH = DESK_DIR / "millennium_memory.jsonl"
STATE_PATH = DESK_DIR / "millennium_lab.json"
LATEST_PATH = DESK_DIR / "millennium_latest.txt"
STATUS_PATH = DESK_DIR / "millennium_status.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ArtifactKind(str, Enum):
    LEMMA = "verified_lemma"
    COUNTEREXAMPLE = "counterexample"
    TRANSFORM = "useful_transformation"
    CONJECTURE = "conjecture"
    FAILED_STRATEGY = "failed_proof_strategy"
    EVIDENCE = "computational_evidence"
    FORMAL = "formal_proof"
    CONNECTION = "connection"
    REJECTION = "rejected_overclaim"


PROGRESS_WEIGHT: dict[ArtifactKind, int] = {
    ArtifactKind.LEMMA: 3,
    ArtifactKind.COUNTEREXAMPLE: 4,
    ArtifactKind.TRANSFORM: 2,
    ArtifactKind.CONJECTURE: 1,
    ArtifactKind.FAILED_STRATEGY: 1,
    ArtifactKind.EVIDENCE: 2,
    ArtifactKind.FORMAL: 5,
    ArtifactKind.CONNECTION: 2,
    ArtifactKind.REJECTION: 1,
}


@dataclass
class Artifact:
    pond: str
    kind: ArtifactKind
    name: str
    statement: str
    status: str
    generation: int
    evidence: dict[str, Any] = field(default_factory=dict)
    recipe: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    ts: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            self.kind = ArtifactKind(self.kind)
        if not self.ts:
            self.ts = utcnow()

    @property
    def progress(self) -> int:
        if self.status in {"REJECTED", "KILLED"}:
            return PROGRESS_WEIGHT.get(self.kind, 0)
        if self.status in {"VERIFIED", "REFUTED", "PROGRESS"}:
            return PROGRESS_WEIGHT.get(self.kind, 0)
        return 0

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["kind"] = self.kind.value
        return row


class Memory:
    """Append-only lab memory. Better Duck reads this. Victory does not."""

    def __init__(self, path: Path = MEMORY_PATH) -> None:
        self.path = path
        self._rows: list[Artifact] = []

    def load(self) -> list[Artifact]:
        self._rows = []
        if not self.path.exists():
            return self._rows
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                kind = data.get("kind")
                if kind not in {k.value for k in ArtifactKind}:
                    continue
                self._rows.append(Artifact(**data))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return self._rows

    def append(self, artifact: Artifact) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(artifact.as_dict()) + "\n")
        self._rows.append(artifact)

    def for_pond(self, pond: str) -> list[Artifact]:
        return [a for a in self._rows if a.pond == pond]

    def counterexamples(self, pond: str | None = None) -> list[Artifact]:
        rows = self._rows if pond is None else self.for_pond(pond)
        return [a for a in rows if a.kind == ArtifactKind.COUNTEREXAMPLE]

    def score(self) -> int:
        return sum(a.progress for a in self._rows)
