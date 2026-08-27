"""Canonical JSON + FNV-1a. No wall-clock inside hashes."""

from __future__ import annotations

import json
import random
from typing import Any


def sort_keys(value: Any) -> Any:
    if isinstance(value, list):
        return [sort_keys(v) for v in value]
    if isinstance(value, dict):
        return {k: sort_keys(value[k]) for k in sorted(value)}
    return value


def canonical(value: Any) -> str:
    return json.dumps(sort_keys(value), separators=(",", ":"), ensure_ascii=True)


def fnv1a(text: str) -> str:
    h = 2166136261
    for ch in text.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


def uid(prefix: str) -> str:
    n = random.randint(0, 0xFFFFFFFF)
    return f"{prefix}_{n:08x}"


def format_tick(n: int) -> str:
    return f"{n:06d}"
