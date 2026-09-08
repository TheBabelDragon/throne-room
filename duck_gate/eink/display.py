"""Display ports. Hardware drivers implement the same render/refresh pair."""

from __future__ import annotations

from pathlib import Path

from duck_gate.eink.layout import render_frame
from duck_gate.eink.snapshot import GateDisplaySnapshot

DEFAULT_FRAME = Path("/tmp/metafield/eink_frame.txt")


class MemoryDisplay:
    """In-process framebuffer. Tests and consoles use this. No SPI."""

    def __init__(self) -> None:
        self.frame = ""
        self.refreshes = 0
        self.last: GateDisplaySnapshot | None = None

    def render(self, snapshot: GateDisplaySnapshot) -> None:
        self.last = snapshot
        self.frame = render_frame(snapshot)

    def refresh(self) -> None:
        self.refreshes += 1


class FileDisplay(MemoryDisplay):
    """Writes the last frame to disk so a real panel or SSH session can tail it."""

    def __init__(self, path: Path = DEFAULT_FRAME) -> None:
        super().__init__()
        self.path = path

    def refresh(self) -> None:
        super().refresh()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.frame, encoding="utf-8")
        except OSError:
            return
