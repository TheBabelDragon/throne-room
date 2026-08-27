"""Follow JSONL the rest of Throne Room already writes.

Does not bind UDP :4210. Bridge remains the sole owner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CSI = Path("/tmp/metafield/csi.jsonl")
DEFAULT_AURORA = Path("/tmp/metafield/aurora_actions.jsonl")
DEFAULT_TICKS = Path("/tmp/metafield/agent_ticks.jsonl")
DEFAULT_MEMORY = Path("/tmp/metafield/agent_memory.jsonl")


class JsonlCursor:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0

    def catch_up_keep(self, n: int) -> list[dict[str, Any]]:
        """Skip history, keep the last n objects, park at EOF."""
        if not self.path.exists() or n <= 0:
            self._seek_end()
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            self.offset = self.path.stat().st_size
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out

    def poll(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return []
        out: list[dict[str, Any]] = []
        try:
            with self.path.open("rb") as fh:
                fh.seek(self.offset)
                data = fh.read()
                self.offset = fh.tell()
        except OSError:
            return []
        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out

    def _seek_end(self) -> None:
        try:
            self.offset = self.path.stat().st_size if self.path.exists() else 0
        except OSError:
            self.offset = 0


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, separators=(",", ":")) + "\n")
    except OSError:
        pass
