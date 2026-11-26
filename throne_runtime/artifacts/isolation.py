"""Isolation manager — storage and process-boundary policy for v0.1.

Sandboxing here is a storage and process-boundary policy, not a claim of a
complete operating-system security sandbox. Filesystem segregation alone is
not secure code isolation.
"""

from __future__ import annotations

from pathlib import Path

from .models import Isolation

TIER_DIRS = {
    Isolation.QUARANTINED: "quarantine",
    Isolation.SANDBOXED: "sandbox",
    Isolation.VALIDATED: "validated",
    Isolation.CERTIFIED_READ_ONLY: "certified",
    Isolation.REJECTED: "rejected",
}


class IsolationManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        for name in TIER_DIRS.values():
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "intake").mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)

    def tier_dir(self, isolation: Isolation) -> Path:
        return self.root / TIER_DIRS[isolation]

    def run_dir(self, run_id: str, isolation: Isolation) -> Path:
        d = self.tier_dir(isolation) / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def place_link(
        self,
        run_id: str,
        isolation: Isolation,
        filename: str,
        blob_path: Path,
    ) -> Path:
        """Create a hardlink or copy of the blob into the isolation tier."""
        dest_dir = self.run_dir(run_id, isolation)
        dest = dest_dir / filename
        if dest.exists():
            return dest
        try:
            os_link = getattr(__import__("os"), "link")
            os_link(blob_path, dest)
        except OSError:
            import shutil

            shutil.copy2(blob_path, dest)
        return dest
