"""Persistent indexed store of mathematical objects.

The desk is the visible slice. This is the body MetaField can remember.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from qwuack.workbench.ids import IdAllocator
from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind, utcnow


DESK_DIR = Path("/tmp/metafield")
OBJECT_LOG = DESK_DIR / "duck_objects.jsonl"
ALLOC_PATH = DESK_DIR / "duck_ids.json"
DESK_STATUS = DESK_DIR / "duck_desk.json"
DESK_TEXT = DESK_DIR / "duck_desk.txt"
SESSION_LOG = DESK_DIR / "duck_sessions.jsonl"


class ObjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DESK_DIR
        self.objects_path = self.root / "duck_objects.jsonl"
        self.alloc_path = self.root / "duck_ids.json"
        self.status_path = self.root / "duck_desk.json"
        self.text_path = self.root / "duck_desk.txt"
        self.session_path = self.root / "duck_sessions.jsonl"
        self.alloc = IdAllocator()
        self.by_id: dict[str, MathObject] = {}
        self.order: list[str] = []
        self.load()

    def load(self) -> None:
        if self.alloc_path.exists():
            try:
                self.alloc.seed(json.loads(self.alloc_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                pass
        self.by_id.clear()
        self.order.clear()
        if not self.objects_path.exists():
            return
        for line in self.objects_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = MathObject.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            self._index(obj, persist=False)

    def _index(self, obj: MathObject, persist: bool) -> None:
        if obj.id not in self.by_id:
            self.order.append(obj.id)
        self.by_id[obj.id] = obj
        if persist:
            self.objects_path.parent.mkdir(parents=True, exist_ok=True)
            with self.objects_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(obj.as_dict()) + "\n")
            self.alloc_path.write_text(json.dumps(self.alloc.as_dict()), encoding="utf-8")

    def mint(self, kind: ObjectKind | str, statement: str, **kwargs) -> MathObject:
        kind_s = kind.value if isinstance(kind, ObjectKind) else str(kind)
        obj_id = kwargs.pop("id", None) or self.alloc.next(kind_s)
        obj = MathObject(id=obj_id, kind=ObjectKind(kind_s), statement=statement, **kwargs)
        self._index(obj, persist=True)
        return obj

    def get(self, obj_id: str) -> MathObject | None:
        return self.by_id.get(obj_id)

    def update(self, obj: MathObject) -> MathObject:
        obj.ts = utcnow()
        self._index(obj, persist=True)
        return obj

    def of_kind(self, kind: ObjectKind) -> list[MathObject]:
        return [self.by_id[i] for i in self.order if self.by_id[i].kind == kind]

    def of_problem(self, problem: str) -> list[MathObject]:
        return [self.by_id[i] for i in self.order if self.by_id[i].problem == problem]

    def of_status(self, status: ClaimStatus) -> list[MathObject]:
        return [self.by_id[i] for i in self.order if self.by_id[i].status == status]

    def counts(self, problem: str | None = None) -> dict[str, int]:
        rows = self.of_problem(problem) if problem else [self.by_id[i] for i in self.order]
        out: dict[str, int] = {"objects": len(rows)}
        for obj in rows:
            out[obj.kind.value] = out.get(obj.kind.value, 0) + 1
            out[f"status:{obj.status.value}"] = out.get(f"status:{obj.status.value}", 0) + 1
        return out

    def failed_attempts(self, problem: str | None = None) -> list[MathObject]:
        rows = self.of_problem(problem) if problem else [self.by_id[i] for i in self.order]
        return [o for o in rows if o.kind == ObjectKind.ATTEMPT and o.status in {ClaimStatus.FAILED, ClaimStatus.KILLED, ClaimStatus.REJECTED}]

    def active_conjectures(self, problem: str | None = None) -> list[MathObject]:
        rows = self.of_problem(problem) if problem else [self.by_id[i] for i in self.order]
        return [o for o in rows if o.kind in {ObjectKind.CONJECTURE, ObjectKind.CLAIM} and o.status in {ClaimStatus.CONJECTURE, ClaimStatus.OPEN, ClaimStatus.EXPLORING}]

    def lemmas(self, problem: str | None = None) -> list[MathObject]:
        rows = self.of_problem(problem) if problem else [self.by_id[i] for i in self.order]
        return [o for o in rows if o.kind == ObjectKind.LEMMA and o.status not in {ClaimStatus.KILLED, ClaimStatus.REJECTED}]

    def __iter__(self) -> Iterable[MathObject]:
        for i in self.order:
            yield self.by_id[i]

    def __len__(self) -> int:
        return len(self.order)
