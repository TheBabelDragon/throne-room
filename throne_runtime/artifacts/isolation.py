"""Isolation manager — storage and process-boundary policy for v0.1.

Sandboxing here is a storage and process-boundary policy, not a claim of a
complete operating-system security sandbox. Filesystem segregation alone is
not secure code isolation.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .hashing import sha256_file
from .models import Isolation

TIER_DIRS = {
    Isolation.QUARANTINED: "quarantine",
    Isolation.SANDBOXED: "sandbox",
    Isolation.VALIDATED: "validated",
    Isolation.CERTIFIED_READ_ONLY: "certified",
    Isolation.REJECTED: "rejected",
}


class IsolationError(ValueError):
    pass


class IsolationManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        for name in TIER_DIRS.values():
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "intake").mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)

    def tier_dir(self, isolation: Isolation) -> Path:
        d = (self.root / TIER_DIRS[isolation]).resolve()
        if not str(d).startswith(str(self.root)):
            raise IsolationError("tier dir escapes root")
        return d

    def run_dir(self, run_id: str, isolation: Isolation) -> Path:
        if ".." in run_id or "/" in run_id or "\\" in run_id:
            raise IsolationError(f"unsafe run_id: {run_id!r}")
        d = self.tier_dir(isolation) / run_id
        d.mkdir(parents=True, exist_ok=True)
        resolved = d.resolve()
        if not str(resolved).startswith(str(self.tier_dir(isolation))):
            raise IsolationError("run dir escapes tier")
        return resolved

    def place_link(
        self,
        run_id: str,
        isolation: Isolation,
        filename: str,
        blob_path: Path,
    ) -> Path:
        """Place blob into isolation tier without unsafe overwrite/symlink subst."""
        # Filename safety
        name = Path(filename).name
        if name in ("", ".", "..") or ".." in Path(filename).parts:
            raise IsolationError(f"unsafe filename: {filename!r}")

        dest_dir = self.run_dir(run_id, isolation)
        dest = (dest_dir / name).resolve()
        if not str(dest).startswith(str(dest_dir)):
            raise IsolationError(f"destination escapes tier: {filename!r}")

        blob_path = Path(blob_path).resolve()
        if not blob_path.is_file() or blob_path.is_symlink():
            # Allow hardlink source; reject if the path itself is a symlink target
            # that points outside — blob store should be regular files.
            if not blob_path.is_file():
                raise IsolationError(f"blob is not a regular file: {blob_path}")

        expected_hash = sha256_file(blob_path)

        if dest.exists() or dest.is_symlink():
            if dest.is_symlink():
                raise IsolationError(f"destination is a symlink (rejected): {dest}")
            # Only reuse if content matches
            if dest.is_file() and sha256_file(dest) == expected_hash:
                return dest
            raise IsolationError(
                f"destination exists with different content: {dest}"
            )

        # Create via temp then link/copy
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            try:
                os.link(blob_path, tmp)
            except OSError:
                shutil.copy2(blob_path, tmp)
            if sha256_file(tmp) != expected_hash:
                tmp.unlink(missing_ok=True)
                raise IsolationError("staged destination hash mismatch")
            os.replace(tmp, dest)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

        if dest.is_symlink():
            dest.unlink()
            raise IsolationError("destination became symlink after place")
        return dest
