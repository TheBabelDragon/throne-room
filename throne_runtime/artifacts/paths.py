"""Path containment helpers.

Inspect original path components with lstat() *before* resolution so symlinks
are not hidden by resolve(). Trusted roots are canonicalized separately from
untrusted candidates. Never use string-prefix matching for security.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


class PathContainmentError(ValueError):
    pass


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def is_symlink_path(path: Path) -> bool:
    st = _lstat(path)
    return st is not None and stat.S_ISLNK(st.st_mode)


def reject_symlink_components(path: Path, *, stop_at: Path | None = None) -> None:
    """Reject any symlink in path or its parents up to stop_at (inclusive of path).

    Does not follow symlinks: uses lstat on each component.
    """
    path = Path(path)
    stop = Path(stop_at).resolve() if stop_at is not None else None
    # Walk from path up to root or stop_at
    cur = path
    seen: set[str] = set()
    while True:
        key = str(cur)
        if key in seen:
            break
        seen.add(key)
        if is_symlink_path(cur):
            raise PathContainmentError(f"symlink component rejected: {cur}")
        if stop is not None:
            try:
                # Compare unresolved names carefully: stop when we reach stop_at by resolve
                if cur.exists() or cur.is_symlink():
                    if Path(cur).resolve() == stop:
                        break
            except OSError:
                pass
        parent = cur.parent
        if parent == cur:
            break
        cur = parent


def is_under(root: Path, candidate: Path) -> bool:
    """True if candidate is under root after both are resolved.

    Callers must reject symlink components on *untrusted* candidates first.
    """
    try:
        Path(candidate).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def ensure_under(
    root: Path,
    candidate: Path,
    label: str = "path",
    *,
    reject_symlinks: bool = True,
) -> Path:
    """Containment check for untrusted candidate under trusted root."""
    root_res = Path(root).resolve()
    cand = Path(candidate)
    if reject_symlinks:
        reject_symlink_components(cand, stop_at=root_res)
    # Also reject if any part of the path string is absolute injection when joining
    resolved = cand.resolve()
    try:
        resolved.relative_to(root_res)
    except ValueError as e:
        raise PathContainmentError(f"{label} escapes root: {candidate}") from e
    return resolved


def reject_symlink(path: Path, label: str = "path") -> None:
    if is_symlink_path(Path(path)):
        raise PathContainmentError(f"{label} is a symlink: {path}")


def safe_filename(name: str) -> str:
    """Return basename-only safe filename; reject traversal forms."""
    if not name or name in (".", ".."):
        raise PathContainmentError(f"unsafe filename: {name!r}")
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise PathContainmentError(f"absolute filename rejected: {name!r}")
    parts = Path(normalized).parts
    if ".." in parts or any(p == "" for p in parts):
        raise PathContainmentError(f"path traversal rejected: {name!r}")
    if any("\x00" in p for p in parts):
        raise PathContainmentError(f"NUL in path rejected: {name!r}")
    return Path(*parts).name if len(parts) == 1 else str(Path(*parts))
