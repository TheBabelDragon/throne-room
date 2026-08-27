"""Self-state kernel — identity, goals, attention, beliefs, integrity.

Adapted from TheBabelDragon/self-state-kernel so throne-room can talk
to SELF without forking that repo. Canonical kernel stays there.
This copy is the adapter used inside the agent loop.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from agent.hashutil import canonical, fnv1a

CommandFn = Callable[..., Any]


class SelfStateKernel:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.commands: dict[str, CommandFn] = {}
        self.trace: list[dict[str, Any]] = []
        self.sequence = 0

        self.SET("kernel.version", "1112")
        self.SET("kernel.status", "READY")
        self.SET("identity.name", "SELF")
        self.SET("identity.role", "field-agent")
        self.SET("identity.continuity", "persistent-across-ticks")
        self.SET("goals", [
            {
                "id": "g0",
                "text": "Maintain a coherent model of the field and answer the human operator.",
                "priority": 1,
            }
        ])
        self.SET("attention.target", "chat")
        self.SET("attention.tick", 0)
        self.SET("beliefs.world", "MetaField")
        self.SET("beliefs.loop", "observe→propose→validate→commit")
        self.SET("working", {})
        self.SET("drives.coherence", 0.7)
        self.SET("drives.curiosity", 0.45)
        self.register("CMD4", self.cmd4)
        self.register("SNAPSHOT", self.snapshot)

    def register(self, name: str, fn: CommandFn) -> None:
        self.commands[name.upper()] = fn

    def peek(self, path: str, fallback: Any = None) -> Any:
        return _get_path(self.values, path, fallback)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.values)

    def integrity(self) -> str:
        return fnv1a(canonical(self.values))

    def GET(self, path: str, fallback: Any = None) -> Any:
        value = copy.deepcopy(_get_path(self.values, path, fallback))
        self._record("GET", path, {"default": fallback}, value)
        return value

    def SET(self, path: str, value: Any) -> Any:
        _set_path(self.values, path, copy.deepcopy(value))
        self._record("SET", path, {"value": value}, value)
        return value

    def QUERY(self, query: str) -> Any:
        upper = query.upper()
        if upper in self.commands:
            result = {"type": "command", "name": upper, "registered": True}
            self._record("QUERY", query, {}, result)
            return result
        return self.GET(query)

    def RUN(self, command: str, *args: Any) -> dict[str, Any]:
        name = command.upper()
        fn = self.commands.get(name)
        if fn is None:
            error = f"Unknown command: {name}"
            self._record("RUN_ERROR", name, {"args": args}, error)
            return {"ok": False, "operation": "RUN", "error": error}
        try:
            value = fn(*args)
            rec = self._record("RUN", name, {"args": args}, value)
            return {"ok": True, "operation": name, "value": value, "trace_sequence": rec["sequence"]}
        except Exception as err:  # noqa: BLE001 — kernel must never raise through RUN
            error = str(err)
            self._record("RUN_ERROR", name, {"args": args}, error)
            return {"ok": False, "operation": name, "error": error}

    def IF(self, condition: Any, then_command: str, else_command: str | None = None) -> dict[str, Any]:
        if not isinstance(condition, bool):
            error = f"IF condition must resolve to bool; received {type(condition).__name__}"
            self._record("IF_ERROR", then_command, {"condition": str(condition)}, error)
            return {"ok": False, "operation": "IF", "error": error}
        if condition:
            return self.RUN(then_command)
        if else_command:
            return self.RUN(else_command)
        self._record("IF_FALSE", then_command, {}, False)
        return {"ok": True, "operation": "IF", "value": False}

    def cmd4(self) -> dict[str, Any]:
        return {
            "command": "CMD4",
            "action": "NORMAL_STATE",
            "special_case": False,
            "attention": self.values.get("attention"),
            "goals": self.values.get("goals"),
            "integrity": self.integrity(),
        }

    def recent_trace(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.trace[-limit:]

    def _record(self, operation: str, target: str, inputs: Any, output: Any) -> dict[str, Any]:
        self.sequence += 1
        rec = {
            "sequence": self.sequence,
            "operation": operation,
            "target": target,
            "inputs": inputs,
            "output": _safe(output),
            "state_hash": self.integrity(),
        }
        self.trace.append(rec)
        if len(self.trace) > 200:
            self.trace.pop(0)
        return rec


def _get_path(obj: dict[str, Any], path: str, fallback: Any = None) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return fallback
        if part not in cur:
            return fallback
        cur = cur[part]
    return cur


def _set_path(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if not parts or any(not p for p in parts):
        raise ValueError(f"Invalid state path: {path}")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _safe(value: Any) -> Any:
    try:
        canonical(value)
        return value
    except TypeError:
        return str(value)


def create_self_state() -> SelfStateKernel:
    return SelfStateKernel()
