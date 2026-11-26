"""Load and validate YAML routing / grading / isolation policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    pass


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser (maps + lists of scalars/maps).

    Avoids a PyYAML dependency for v0.1. Supports the policy files we ship.
    """
    # Prefer stdlib-only: try json first, else a tiny line parser for our files.
    text = text.strip()
    if not text:
        return {}
    try:
        import json

        return json.loads(text)
    except Exception:
        pass

    # Extremely small subset: top-level keys, nested maps, list of maps with key: value
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(0, root)]
    pending_list_key: str | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        # Pop stack to current indent
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
            pending_list_key = None

        parent_indent, parent = stack[-1]

        if line.startswith("- "):
            item_raw = line[2:].strip()
            if isinstance(parent, list):
                if ":" in item_raw and not item_raw.startswith("{"):
                    k, _, v = item_raw.partition(":")
                    parent.append({k.strip(): _scalar(v.strip())})
                else:
                    parent.append(_scalar(item_raw))
            elif isinstance(parent, dict) and pending_list_key:
                lst = parent.setdefault(pending_list_key, [])
                if ":" in item_raw:
                    k, _, v = item_raw.partition(":")
                    lst.append({k.strip(): _scalar(v.strip())})
                else:
                    lst.append(_scalar(item_raw))
            continue

        if ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest == "":
                # Nested structure follows
                # Lookahead not available; create dict, may become list if '-' comes
                node: Any = {}
                if isinstance(parent, dict):
                    parent[key] = node
                    stack.append((indent + 2, node))
                    pending_list_key = key
                continue
            val = _scalar(rest)
            if isinstance(parent, dict):
                parent[key] = val
                pending_list_key = None
            continue

    return root


def _scalar(s: str) -> Any:
    if s.startswith("\"") and s.endswith("\""):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return int(s)
    return s


@dataclass
class RoutingPolicy:
    rules: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_path: str = ""

    def destination_for(self, condition: str) -> str | None:
        for r in self.rules:
            if r.get("condition") == condition:
                return r.get("destination")
        return None


def load_routing_policy(path: Path) -> RoutingPolicy:
    if not path.is_file():
        raise PolicyError(f"routing policy not found: {path}")
    data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PolicyError("routing policy root must be a mapping")
    rules_raw = data.get("rules") or []
    if not isinstance(rules_raw, list):
        raise PolicyError("routing policy 'rules' must be a list")
    rules: list[dict[str, str]] = []
    for item in rules_raw:
        if not isinstance(item, dict):
            # our parser may produce list of single-key dicts accumulated poorly;
            # also accept already-merged maps from richer parsers
            raise PolicyError(f"malformed rule entry: {item!r}")
        # Merge successive single-key dicts if needed is not required for our files
        # when using a real YAML loader; for the subset parser we store full maps
        # by rewriting the policy files to JSON-compatible form in tests if needed.
        rules.append({str(k): str(v) for k, v in item.items()})
    notes = data.get("notes") or []
    if notes and not isinstance(notes, list):
        raise PolicyError("'notes' must be a list")
    return RoutingPolicy(
        rules=rules,
        notes=[str(n) for n in notes],
        source_path=str(path),
    )


def load_routing_policy_loose(path: Path) -> RoutingPolicy:
    """Load policy using a tolerant line scan for condition/destination pairs."""
    if not path.is_file():
        raise PolicyError(f"routing policy not found: {path}")
    rules: list[dict[str, str]] = []
    current: dict[str, str] = {}
    notes: list[str] = []
    in_notes = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("notes:"):
            in_notes = True
            continue
        if in_notes:
            if line.startswith("- "):
                notes.append(line[2:].strip())
            continue
        if line.startswith("- condition:"):
            if current:
                rules.append(current)
            current = {"condition": line.split(":", 1)[1].strip()}
        elif line.startswith("destination:") and current is not None:
            current["destination"] = line.split(":", 1)[1].strip()
        elif line.startswith("condition:"):
            if current:
                rules.append(current)
            current = {"condition": line.split(":", 1)[1].strip()}
    if current:
        rules.append(current)
    if not rules:
        raise PolicyError(f"no routing rules found in {path}")
    return RoutingPolicy(rules=rules, notes=notes, source_path=str(path))
