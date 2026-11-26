"""Load and validate YAML routing policies — fail closed."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .hashing import sha256_bytes


class PolicyError(ValueError):
    pass


POLICY_VERSION = 1
VALID_DESTINATIONS = frozenset(
    {"quarantine", "sandbox", "validated", "certified", "rejected"}
)
REQUIRED_CONDITIONS = frozenset(
    {
        "unknown_source_or_invalid_manifest",
        "newly_ingested",
        "experimental_run",
        "validated_schema_and_checks",
        "failed_integrity_or_policy",
    }
)


@dataclass
class RoutingPolicy:
    rules: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_path: str = ""
    version: int = POLICY_VERSION
    content_hash: str = ""

    def destination_for(self, condition: str) -> str | None:
        for r in self.rules:
            if r.get("condition") == condition:
                return r.get("destination")
        return None


def load_routing_policy_loose(path: Path) -> RoutingPolicy:
    """Load and validate routing policy; raises PolicyError on any defect."""
    if not path.is_file():
        raise PolicyError(f"routing policy not found: {path}")
    text = path.read_text(encoding="utf-8")
    content_hash = sha256_bytes(text.encode("utf-8"))

    rules: list[dict[str, str]] = []
    current: dict[str, str] = {}
    notes: list[str] = []
    in_notes = False
    version = POLICY_VERSION

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("version:"):
            try:
                version = int(line.split(":", 1)[1].strip())
            except ValueError as e:
                raise PolicyError(f"invalid policy version: {line}") from e
            continue
        if line.startswith("notes:"):
            in_notes = True
            continue
        if in_notes:
            if line.startswith("- "):
                notes.append(line[2:].strip())
            continue
        if line.startswith("- condition:") or (
            line.startswith("condition:") and not current
        ):
            if current:
                rules.append(current)
            cond = line.split(":", 1)[1].strip()
            current = {"condition": cond}
        elif line.startswith("destination:") and current:
            current["destination"] = line.split(":", 1)[1].strip()
        elif line.startswith("- condition:"):
            if current:
                rules.append(current)
            current = {"condition": line.split(":", 1)[1].strip()}

    if current:
        rules.append(current)

    if version != POLICY_VERSION:
        raise PolicyError(
            f"unsupported policy version {version}; expected {POLICY_VERSION}"
        )
    if not rules:
        raise PolicyError(f"no routing rules found in {path}")

    seen_conditions: set[str] = set()
    for r in rules:
        if "condition" not in r or "destination" not in r:
            raise PolicyError(f"malformed rule (need condition+destination): {r}")
        dest = r["destination"].lower()
        if dest not in VALID_DESTINATIONS:
            raise PolicyError(f"invalid isolation destination: {dest}")
        r["destination"] = dest
        seen_conditions.add(r["condition"])

    missing = REQUIRED_CONDITIONS - seen_conditions
    if missing:
        raise PolicyError(f"policy missing required conditions: {sorted(missing)}")

    return RoutingPolicy(
        rules=rules,
        notes=notes,
        source_path=str(path),
        version=version,
        content_hash=content_hash,
    )
