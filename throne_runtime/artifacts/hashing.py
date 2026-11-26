"""SHA-256 content-addressed hashing utilities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of bytes. Deterministic."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return hex SHA-256 of file contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    """Deterministic SHA-256 of a JSON-serializable object.

    Uses sorted keys and compact separators so equal semantic content
    yields the same hash regardless of insertion order.
    """
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(payload.encode("utf-8"))


def blob_path_for_hash(root: Path, content_hash: str) -> Path:
    """Content-addressed blob layout: blobs/ab/cd/<fullhash>."""
    if len(content_hash) < 4:
        raise ValueError("content_hash too short")
    return root / "blobs" / content_hash[:2] / content_hash[2:4] / content_hash
