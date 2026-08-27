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
    def __init__(self, path: Path, *, keep: int = 32) -> None:
        self.path = Path(path)
        self.offset = 0
        self.keep = max(1, keep)
        self._existed = self.path.exists()

    def catch_up_keep(self, n: int) -> list[dict[str, Any]]:
        """Skip history, keep the last n objects, park at EOF."""
        if n <= 0:
            self._seek_end()
            return []
        if not self.path.exists():
            self._existed = False
            self.offset = 0
            return []
        self._existed = True
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        try:
            if size > 524_288:
                with self.path.open("rb") as fh:
                    fh.seek(max(0, size - 524_288))
                    chunk = fh.read().decode("utf-8", errors="replace")
                lines = chunk.splitlines()
                if size > 524_288 and lines:
                    lines = lines[1:]
            else:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            self.offset = size
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

    def poll(self, max_records: int = 64, max_bytes: int = 262_144) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if not self._existed:
            # File appeared after attach — do not replay hours of history.
            return self.catch_up_keep(self.keep)
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return []
        budget = max(64, max_bytes)
        start = self.offset
        try:
            with self.path.open("rb") as fh:
                fh.seek(start)
                data = fh.read(budget)
        except OSError:
            return []
        if not data:
            return []
        if not data.endswith(b"\n"):
            last_nl = data.rfind(b"\n")
            if last_nl < 0:
                return []
            data = data[: last_nl + 1]
        out: list[dict[str, Any]] = []
        consumed = 0
        parts = data.split(b"\n")
        for i, raw in enumerate(parts):
            if i == len(parts) - 1 and raw == b"":
                break
            consumed += len(raw) + 1
            s = raw.strip()
            if not s:
                continue
            try:
                obj = json.loads(s.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
            if len(out) >= max_records:
                break
        self.offset = start + consumed
        return out

    def backlog_bytes(self) -> int:
        try:
            if not self.path.exists():
                return 0
            size = self.path.stat().st_size
        except OSError:
            return 0
        return max(0, size - self.offset)

    def _seek_end(self) -> None:
        try:
            if self.path.exists():
                self.offset = self.path.stat().st_size
                self._existed = True
            else:
                self.offset = 0
                self._existed = False
        except OSError:
            self.offset = 0


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    if not isinstance(path, Path):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, separators=(",", ":")) + "\n")
            fh.flush()
    except OSError:
        pass
