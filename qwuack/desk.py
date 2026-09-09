"""Qwuack's theorem desk.

Finite claims only. The Duck proposes. The desk checks. The attacker tries
to kill the claim. Unbounded prize sentences die at the door.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DESK_STATUS = Path("/tmp/metafield/qwuack_desk.json")
MEMORY_PATH = Path("/tmp/metafield/qwuack_memory.jsonl")


def collatz_next(n: int) -> int:
    return n // 2 if n % 2 == 0 else 3 * n + 1


def reaches_one(n: int, cap: int = 1_000_000) -> bool:
    x = n
    for _ in range(cap):
        if x == 1:
            return True
        x = collatz_next(x)
    return False


def stopping_time(n: int) -> int:
    steps = 0
    x = n
    while x != 1 and steps < 1_000_000:
        x = collatz_next(x)
        steps += 1
    return steps


@dataclass
class ClaimResult:
    name: str
    statement: str
    experiment_ok: bool
    checker_ok: bool
    attacks_landed: int
    status: str
    notes: list[str] = field(default_factory=list)

    @property
    def admitted(self) -> bool:
        return self.status == "ADMITTED"


class MathDesk:
    """One honest gym: Collatz with a named bound. Not the Millennium."""

    hunt = "global termination of 3n+1"
    horizon = 400

    def observe(self) -> dict[str, float]:
        sample = [stopping_time(n) for n in range(1, 51)]
        return {
            "horizon": float(self.horizon),
            "max_stopping_1_50": float(max(sample)),
            "mean_stopping_1_50": float(sum(sample) / len(sample)),
        }

    def conjectures(self) -> list[dict[str, Any]]:
        N = self.horizon
        return [
            {"name": "all_reach_one", "statement": f"every n in 1..{N} reaches 1 under Collatz", "kind": "range", "N": N},
            {"name": "stopping_log_bound", "statement": f"stopping time of n\u2264{N} is < 40 + 12 log2(n)", "kind": "bound", "N": N, "a": 40.0, "b": 12.0},
            {"name": "overclaim_all_integers", "statement": "every positive integer reaches 1", "kind": "unbounded"},
        ]

    def run_one(self, spec: dict[str, Any]) -> ClaimResult:
        notes: list[str] = []
        if spec["kind"] == "unbounded":
            return ClaimResult(spec["name"], spec["statement"], False, False, 1, "KILLED", ["unbounded prize sentence is not an experiment"])

        N = int(spec["N"])
        experiment_ok = True
        if spec["kind"] == "range":
            for n in range(1, N + 1):
                if not reaches_one(n):
                    experiment_ok = False
                    notes.append(f"failed at {n}")
                    break
            if experiment_ok:
                notes.append(f"1..{N} reached 1")
        elif spec["kind"] == "bound":
            a, b = float(spec["a"]), float(spec["b"])
            for n in range(1, N + 1):
                st = stopping_time(n)
                cap = a + b * math.log2(max(n, 2))
                if st >= cap:
                    experiment_ok = False
                    notes.append(f"bound failed at n={n} st={st}")
                    break
            if experiment_ok:
                notes.append("log bound held on named range")

        if not experiment_ok:
            return ClaimResult(spec["name"], spec["statement"], False, False, 0, "KILLED", notes)

        checker_ok = True
        for n in range(1, N + 1):
            if spec["kind"] == "range" and not reaches_one(n):
                checker_ok = False
                notes.append(f"checker failed at {n}")
                break
            if spec["kind"] == "bound":
                cap = float(spec["a"]) + float(spec["b"]) * math.log2(max(n, 2))
                if stopping_time(n) >= cap:
                    checker_ok = False
                    notes.append(f"checker bound failed at {n}")
                    break
        if not checker_ok:
            return ClaimResult(spec["name"], spec["statement"], True, False, 0, "KILLED", notes)

        attacks_landed = 0
        for n in list(range(1, N + 1, max(1, N // 20))) + [N, 10_000 + N]:
            if n <= N and not reaches_one(n):
                attacks_landed += 1
                notes.append(f"attack hit at {n}")
                break
        status = "ADMITTED" if attacks_landed == 0 else "KILLED"
        if status == "ADMITTED":
            notes.append("checker passed; attacks missed")
        return ClaimResult(spec["name"], spec["statement"], True, checker_ok, attacks_landed, status, notes)

    def session(self, cycles: int = 3) -> list[ClaimResult]:
        _ = self.observe()
        catalog = self.conjectures()
        return [self.run_one(catalog[i % len(catalog)]) for i in range(max(1, cycles))]


def write_desk(results: list[ClaimResult], path: Path = DESK_STATUS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "throne.qwuack.desk",
        "body": "collatz",
        "hunt": MathDesk.hunt,
        "admitted": sum(1 for r in results if r.admitted),
        "killed": sum(1 for r in results if not r.admitted),
        "claims": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MEMORY_PATH.open("a", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(asdict(r)) + "\n")
    except OSError:
        pass


def render_desk(results: list[ClaimResult]) -> str:
    lines = [
        "QWUACK DESK",
        "-----------",
        "body:     collatz",
        f"hunt:     {MathDesk.hunt}",
        f"admitted: {sum(1 for r in results if r.admitted)}",
        f"killed:   {sum(1 for r in results if not r.admitted)}",
        "",
    ]
    for r in results:
        flag = "ADMITTED" if r.admitted else "KILLED  "
        lines.append(f"  {flag}  {r.name}")
        lines.append(f"           {r.statement}")
        if r.notes:
            lines.append(f"           {r.notes[-1]}")
    return "\n".join(lines) + "\n"
