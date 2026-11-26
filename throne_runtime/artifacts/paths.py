"""Shared path containment helpers (no string-prefix security checks)."""

from __future__ import annotations

from pathlib import Path


class PathContainmentError(ValueError):
    pass


def is_under(root: Path, candidate: Path) -> bool:
    try:
        Path(candidate).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def ensure_under(root: Path, candidate: Path, label: str = "path") -> Path:
    resolved = Path(candidate).resolve()
    if not is_under(root, resolved):
        raise PathContainmentError(f"{label} escapes root: {candidate}")
    return resolved


def reject_symlink(path: Path, label: str = "path") -> None:
    p = Path(path)
    if p.is_symlink():
        raise PathContainmentError(f"{label} is a symlink: {p}")
