"""Isolation manager — storage and process-boundary policy for v0.1.

Path containment uses Path.relative_to() against a trusted resolved root.
String-prefix comparisons are never used for security decisions.
Symlinked parents and destinations are rejected.

Filesystem segregation is not an OS-level execution sandbox.
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


def _is_under(root: Path, candidate: Path) -> bool:
    """True if candidate is contained under root (both resolved, no string prefix)."""
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _reject_symlink_in_chain(path: Path, stop_at: Path) -> None:
    """Walk parents up to stop_at; reject any symlink component."""
    path = Path(path)
    stop = stop_at.resolve()
    cur = path
    # Include path itself
    chain: list[Path] = []
    while True:
        chain.append(cur)
        if cur.resolve() == stop:
            break
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
        try:
            if cur.resolve() == stop:
                chain.append(cur)
                break
        except OSError:
            break
    for p in chain:
        try:
            if p.is_symlink():
                raise IsolationError(f"symlink in path chain rejected: {p}")
        except OSError as e:
            raise IsolationError(f"path inspect failed: {p}: {e}") from e


class IsolationManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        for name in TIER_DIRS.values():
            d = self.root / name
            d.mkdir(parents=True, exist_ok=True)
            if d.is_symlink():
                raise IsolationError(f"tier directory is a symlink: {d}")
        (self.root / "intake").mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)

    def tier_dir(self, isolation: Isolation) -> Path:
        d = (self.root / TIER_DIRS[isolation]).resolve()
        if not _is_under(self.root, d):
            raise IsolationError("tier dir escapes root")
        if d.is_symlink():
            raise IsolationError(f"tier dir is symlink: {d}")
        return d

    def run_dir(self, run_id: str, isolation: Isolation) -> Path:
        if not run_id or any(c in run_id for c in ("/", "\\", "..", "\x00")):
            raise IsolationError(f"unsafe run_id: {run_id!r}")
        if Path(run_id).name != run_id:
            raise IsolationError(f"unsafe run_id: {run_id!r}")
        tier = self.tier_dir(isolation)
        d = tier / run_id
        d.mkdir(parents=True, exist_ok=True)
        resolved = d.resolve()
        if not _is_under(tier, resolved):
            raise IsolationError("run dir escapes tier")
        _reject_symlink_in_chain(resolved, tier)
        return resolved

    def place_link(
        self,
        run_id: str,
        isolation: Isolation,
        filename: str,
        blob_path: Path,
    ) -> Path:
        """Place blob into isolation tier; reject symlink dest/parents."""
        name = Path(filename).name
        if name in ("", ".", "..") or ".." in Path(filename).parts:
            raise IsolationError(f"unsafe filename: {filename!r}")
        if Path(filename).is_absolute() or filename.startswith(("/", "\\")):
            raise IsolationError(f"absolute filename rejected: {filename!r}")

        dest_dir = self.run_dir(run_id, isolation)
        dest = dest_dir / name

        # Inspect pre-resolve components for symlinks
        if dest.exists() or dest.is_symlink():
            if dest.is_symlink():
                raise IsolationError(f"destination is a symlink (rejected): {dest}")

        dest_resolved = dest.resolve()
        if not _is_under(dest_dir, dest_resolved):
            raise IsolationError(f"destination escapes tier: {filename!r}")
        _reject_symlink_in_chain(dest_resolved.parent, dest_dir)

        blob_path = Path(blob_path)
        if blob_path.is_symlink():
            raise IsolationError(f"blob path is symlink: {blob_path}")
        blob_path = blob_path.resolve()
        if not blob_path.is_file():
            raise IsolationError(f"blob is not a regular file: {blob_path}")

        expected_hash = sha256_file(blob_path)
        expected_size = blob_path.stat().st_size

        if dest.exists():
            if dest.is_symlink():
                raise IsolationError(f"destination is a symlink (rejected): {dest}")
            if not dest.is_file():
                raise IsolationError(f"destination not a regular file: {dest}")
            actual = sha256_file(dest)
            if actual == expected_hash and dest.stat().st_size == expected_size:
                return dest_resolved
            raise IsolationError(
                f"destination exists with different content: {dest}"
            )

        tmp = dest.with_suffix(dest.suffix + f".{os.getpid()}.tmp")
        try:
            if tmp.exists() or tmp.is_symlink():
                if tmp.is_symlink():
                    raise IsolationError(f"tmp path is symlink: {tmp}")
                tmp.unlink()
            try:
                os.link(blob_path, tmp)
            except OSError:
                shutil.copy2(blob_path, tmp)
            if tmp.is_symlink():
                tmp.unlink()
                raise IsolationError("staged file became symlink")
            if sha256_file(tmp) != expected_hash:
                tmp.unlink(missing_ok=True)
                raise IsolationError("staged destination hash mismatch")
            if tmp.stat().st_size != expected_size:
                tmp.unlink(missing_ok=True)
                raise IsolationError("staged destination size mismatch")
            os.replace(tmp, dest)
        finally:
            if tmp.exists() or tmp.is_symlink():
                try:
                    tmp.unlink()
                except OSError:
                    pass

        final = dest.resolve()
        if final.is_symlink():
            try:
                final.unlink()
            except OSError:
                pass
            raise IsolationError("destination became symlink after place")
        if not _is_under(dest_dir, final):
            raise IsolationError("final destination escapes tier")
        if sha256_file(final) != expected_hash:
            raise IsolationError("final destination hash mismatch")
        return final
