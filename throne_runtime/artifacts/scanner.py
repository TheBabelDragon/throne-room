"""Safe ingestion scanner.

Rejects path traversal, symlink escapes, unsafe archive members.
Never executes discovered files. Default new inputs are QUARANTINED.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .hashing import sha256_file


@dataclass
class ScanLimits:
    max_files: int = 10_000
    max_total_bytes: int = 512 * 1024 * 1024  # 512 MiB
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


class ArtifactScanner:
    """Scan paths for safe ingestion into the artifact store."""

    def __init__(self, storage_root: Path, limits: ScanLimits | None = None) -> None:
        self.storage_root = Path(storage_root).resolve()
        self.limits = limits or ScanLimits()

    def scan_file(self, path: Path, *, relative_name: str | None = None) -> ScannedFile:
        path = Path(path)
        if not path.exists():
            raise ScanError(f"path does not exist: {path}")
        if path.is_symlink():
            # Do not follow; record and reject for storage placement outside root.
            target = path.resolve()
            if not _is_under(self.storage_root, target) and not _is_under(path.parent, target):
                # Allow only if the ultimate target stays within a controlled area;
                # for v0.1 we reject external symlink targets on ingest.
                if not target.exists() or not _is_under(self.storage_root, target):
                    raise ScanError(f"symlink escape rejected: {path} -> {target}")
        if not path.is_file():
            raise ScanError(f"not a regular file: {path}")

        size = path.stat().st_size
        if size > self.limits.max_single_file_bytes:
            raise ScanError(f"file exceeds size limit: {path} ({size} bytes)")

        rel = relative_name or path.name
        if ".." in Path(rel).parts or rel.startswith("/") or rel.startswith("\\"):
            raise ScanError(f"path traversal rejected: {rel}")

        return ScannedFile(
            path=path,
            relative=rel,
            size_bytes=size,
            content_hash=sha256_file(path),
            media_type=_guess_media_type(rel),
            is_symlink=path.is_symlink(),
        )

    def scan_tree(self, root: Path) -> list[ScannedFile]:
        root = Path(root)
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
                    # Reject symlink files that escape
                    try:
                        resolved = p.resolve()
                    except OSError as e:
                        raise ScanError(f"symlink resolve failed: {p}") from e
                    if not _is_under(root, resolved):
                        raise ScanError(f"symlink escape rejected: {p}")
                    continue  # skip storing symlink itself for v0.1 tree ingest
                rel = str(p.relative_to(root))
                sf = self.scan_file(p, relative_name=rel)
                results.append(sf)
                total += sf.size_bytes
                if len(results) > self.limits.max_files:
                    raise ScanError("file count limit exceeded")
                if total > self.limits.max_total_bytes:
                    raise ScanError("total size limit exceeded")
        return results

    def inspect_archive_paths(self, archive_path: Path) -> list[str]:
        """Inspect archive member paths without extraction; reject escapes."""
        archive_path = Path(archive_path)
        names: list[str] = []
        lower = archive_path.name.lower()

        def _check(name: str) -> None:
            # Normalize and reject absolute / traversal
            parts = Path(name).parts
            if name.startswith("/") or name.startswith("\\") or ".." in parts:
                raise ScanError(f"unsafe archive member path: {name}")
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
