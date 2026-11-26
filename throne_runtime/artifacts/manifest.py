"""Manifest load/store with strict validation and deterministic hashing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import sha256_json
from .models import MANIFEST_SCHEMA, MANIFEST_VERSION, RunManifest


def canonical_manifest_dict(manifest: RunManifest) -> dict[str, Any]:
    """Produce a dict suitable for deterministic hashing.

    manifest_hash itself is excluded from the hash input.
    """
    d = manifest.as_dict()
    d.pop("manifest_hash", None)
    return d


def compute_manifest_hash(manifest: RunManifest) -> str:
    return sha256_json(canonical_manifest_dict(manifest))


def attach_manifest_hash(manifest: RunManifest) -> RunManifest:
    """Return a copy of the manifest with manifest_hash set."""
    h = compute_manifest_hash(manifest)
    manifest.manifest_hash = h
    return manifest


def write_manifest(path: Path, manifest: RunManifest) -> None:
    """Atomically write a validated, hashed manifest as JSON."""
    attach_manifest_hash(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(manifest.as_dict(), indent=2, sort_keys=True, ensure_ascii=False)
    tmp.write_text(data + "\n", encoding="utf-8")
    tmp.replace(path)


def load_manifest(path: Path) -> RunManifest:
    """Load and strictly validate a manifest file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest root must be an object")
    m = RunManifest.from_dict(raw)
    expected = compute_manifest_hash(m)
    if m.manifest_hash and m.manifest_hash != expected:
        raise ValueError(
            f"manifest_hash mismatch: recorded={m.manifest_hash[:16]}... "
            f"computed={expected[:16]}..."
        )
    return m


def validate_manifest_dict(d: dict[str, Any]) -> RunManifest:
    """Validate an in-memory dict and return a RunManifest."""
    return RunManifest.from_dict(d)
