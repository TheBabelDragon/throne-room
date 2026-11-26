"""Content-addressed blob storage with atomic promotion.

Registry metadata is separate from blob storage. Failed writes must not
leave partially registered artifacts. Identical content resolves to the
same blob.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Protocol

from .hashing import blob_path_for_hash, sha256_bytes, sha256_file


class StorageBackend(Protocol):
    """Interface so a future remote/distributed backend can be swapped in."""

    def put_bytes(self, data: bytes, content_hash: str | None = None) -> str:
        """Store bytes; return content hash."""
        ...

    def put_file(self, path: Path, content_hash: str | None = None) -> str:
        """Store file; return content hash."""
        ...

    def get_path(self, content_hash: str) -> Path:
        """Return local path to blob (may be temporary for remote backends)."""
        ...

    def exists(self, content_hash: str) -> bool:
        ...

    def verify(self, content_hash: str) -> bool:
        """Re-hash stored blob and confirm it matches."""
        ...


class LocalBlobStorage:
    """Filesystem content-addressed store under root/blobs/."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.blobs_root = self.root / "blobs"
        self.blobs_root.mkdir(parents=True, exist_ok=True)

    def _target(self, content_hash: str) -> Path:
        return blob_path_for_hash(self.root, content_hash)

    def put_bytes(self, data: bytes, content_hash: str | None = None) -> str:
        h = content_hash or sha256_bytes(data)
        if content_hash and content_hash != sha256_bytes(data):
            raise ValueError("provided content_hash does not match data")
        target = self._target(h)
        if target.exists():
            if not self.verify(h):
                raise ValueError(f"existing blob corrupted: {h[:16]}...")
            return h
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".staging-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            Path(tmp_name).replace(target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return h

    def put_file(self, path: Path, content_hash: str | None = None) -> str:
        path = Path(path)
        h = content_hash or sha256_file(path)
        if content_hash and content_hash != sha256_file(path):
            raise ValueError("provided content_hash does not match file")
        target = self._target(h)
        if target.exists():
            if not self.verify(h):
                raise ValueError(f"existing blob corrupted: {h[:16]}...")
            return h
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".staging-")
        try:
            with os.fdopen(fd, "wb") as out, path.open("rb") as inp:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
            Path(tmp_name).replace(target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return h

    def get_path(self, content_hash: str) -> Path:
        p = self._target(content_hash)
        if not p.exists():
            raise FileNotFoundError(f"blob not found: {content_hash}")
        return p

    def exists(self, content_hash: str) -> bool:
        return self._target(content_hash).exists()

    def verify(self, content_hash: str) -> bool:
        p = self._target(content_hash)
        if not p.exists():
            return False
        return sha256_file(p) == content_hash
