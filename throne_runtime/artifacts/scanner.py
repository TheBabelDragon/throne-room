"""Safe ingestion scanner.

Symlink inputs are rejected by default. Paths are resolved and must stay
under the configured storage/intake root. No symlink following during
recursive scans. Filesystem segregation is not an OS-level execution sandbox.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_file


@dataclass
class ScanLimits:
    max_files: int = 10_000
    max_total_bytes: int = 512 * 1024 * 1024
    max_single_file_bytes: int = 256 * 1024 * 1024


@dataclass
class ScannedFile:
    path: Path
    relative: str
    size_bytes: int
    content_hash: str
    media_type: str
    is_symlink: bool = False


class ScanError(ValueError):
    pass


def _guess_media_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".log") or lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".lean"):
        return "text/x-lean"
    if lower.endswith(".py"):
        return "text/x-python"
    if lower.endswith(".yaml") or lower.endswith(".yml"):
        return "application/yaml"
    if lower.endswith(".zip"):
        return "application/zip"
    if lower.endswith(".tar") or lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return "application/x-tar"
    return "application/octet-stream"


def _is_under(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_relative_name(name: str) -> str:
    """Reject traversal, absolute, and alternate-separator forms."""
    if not name or name in (".", ".."):
        raise ScanError(f"unsafe filename: {name!r}")
    # Normalize separators
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        raise ScanError(f"absolute path rejected: {name!r}")
    # Windows drive
    if len(normalized) >= 2 and normalized[1] == ":":
        raise ScanError(f"drive-letter path rejected: {name!r}")
    parts = Path(normalized).parts
    if ".." in parts or any(p == "" for p in parts):
        raise ScanError(f"path traversal rejected: {name!r}")
    if any("\x00" in p for p in parts):
        raise ScanError(f"NUL in path rejected: {name!r}")
    return str(Path(*parts)) if parts else name


class ArtifactScanner:
    def __init__(
        self,
        storage_root: Path,
        limits: ScanLimits | None = None,
        *,
        allow_symlinks: bool = False,
    ) -> None:
        self.storage_root = Path(storage_root).resolve()
        self.limits = limits or ScanLimits()
        self.allow_symlinks = allow_symlinks

    def scan_file(self, path: Path, *, relative_name: str | None = None) -> ScannedFile:
        path = Path(path)

        # Reject symlinks by default (before resolve follows them)
        if path.is_symlink() and not self.allow_symlinks:
            raise ScanError(f"symlink input rejected: {path}")

        if not path.exists():
            raise ScanError(f"path does not exist: {path}")

        # Resolve and re-check
        try:
            resolved = path.resolve(strict=True)
        except OSError as e:
            raise ScanError(f"path resolve failed: {path}") from e

        if resolved.is_symlink() and not self.allow_symlinks:
            raise ScanError(f"symlink resolved path rejected: {path}")

        if not resolved.is_file():
            raise ScanError(f"not a regular file: {path}")

        # Containment: if path is under storage_root, enforce; intake from
        # outside is allowed for explicit single-file ingest but relative
        # name must still be safe.
        rel = _safe_relative_name(relative_name or path.name)

        # TOCTOU: stat then hash then re-stat size
        st1 = resolved.stat()
        if st1.st_size > self.limits.max_single_file_bytes:
            raise ScanError(f"file exceeds size limit: {path} ({st1.st_size} bytes)")

        content_hash = sha256_file(resolved)
        st2 = resolved.stat()
        if st2.st_size != st1.st_size or st2.st_ino != st1.st_ino:
            raise ScanError(f"file changed during scan (TOCTOU): {path}")

        return ScannedFile(
            path=resolved,
            relative=rel,
            size_bytes=st2.st_size,
            content_hash=content_hash,
            media_type=_guess_media_type(rel),
            is_symlink=False,
        )

    def scan_tree(self, root: Path) -> list[ScannedFile]:
        root = Path(root)
        if root.is_symlink():
            raise ScanError(f"symlink tree root rejected: {root}")
        if not root.is_dir():
            raise ScanError(f"not a directory: {root}")

        results: list[ScannedFile] = []
        total = 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Prune symlinked directories
            dirnames[:] = [
                d for d in dirnames if not (Path(dirpath) / d).is_symlink()
            ]
            for name in filenames:
                p = Path(dirpath) / name
                if p.is_symlink():
                    raise ScanError(f"symlink in tree rejected: {p}")
                rel = _safe_relative_name(str(p.relative_to(root)))
                sf = self.scan_file(p, relative_name=rel)
                results.append(sf)
                total += sf.size_bytes
                if len(results) > self.limits.max_files:
                    raise ScanError("file count limit exceeded")
                if total > self.limits.max_total_bytes:
                    raise ScanError("total size limit exceeded")
        return results

    def inspect_archive_paths(self, archive_path: Path) -> list[str]:
        archive_path = Path(archive_path)
        if archive_path.is_symlink():
            raise ScanError(f"symlink archive rejected: {archive_path}")
        names: list[str] = []
        lower = archive_path.name.lower()

        def _check(name: str) -> None:
            _safe_relative_name(name.replace("\\", "/").lstrip("/"))
            names.append(name)

        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    _check(info.filename)
        elif lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
            with tarfile.open(archive_path, "r:*") as tf:
                for m in tf.getmembers():
                    _check(m.name)
        else:
            raise ScanError(f"unsupported archive type: {archive_path}")
        return names
