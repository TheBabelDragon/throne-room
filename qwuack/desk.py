"""Qwuack's theorem desk.

Finite claims only. --runtime keeps the Duck at the table until killed.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DESK_STATUS = Path("/tmp/metafield/qwuack_desk.json")
MEMORY_PATH = Path("/tmp/metafield/qwuack_memory.jsonl")
STATE_PATH = Path("/tmp/metafield/qwuack_desk_state.json")


def collatz_next(n: int) -> int:
    return n // 2 if n % 2 == 0 else 3 * n + 1


def reaches_one(n: int, cap: int = 2_000_000) -> bool:
    x = n
    for _ in range(cap):
        if x == 1:
            return True
        x = collatz_next(x)
    return False


def stopping_time(n: int) -> int:
    steps = 0
    x = n
    while x != 1 and steps < 2_000_000:
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
    hunt = "global termination of 3n+1"
    max_horizon = 20_000

    def __init__(self, horizon: int = 400, bound_a: float = 40.0, bound_b: float = 12.0, generation: int = 0) -> None:
        self.horizon = horizon
        self.bound_a = bound_a
        self.bound_b = bound_b
        self.generation = generation
        self.admitted_total = 0
        self.killed_total = 0

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "MathDesk":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                desk = cls(
                    horizon=int(data.get("horizon", 400)),
                    bound_a=float(data.get("bound_a", 40.0)),
                    bound_b=float(data.get("bound_b", 12.0)),
                    generation=int(data.get("generation", 0)),
                )
                desk.admitted_total = int(data.get("admitted_total", 0))
                desk.killed_total = int(data.get("killed_total", 0))
                return desk
            except (OSError, ValueError, TypeError):
                pass
        return cls()

    def save(self, path: Path = STATE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "horizon": self.horizon,
            "bound_a": self.bound_a,
            "bound_b": self.bound_b,
            "generation": self.generation,
            "admitted_total": self.admitted_total,
            "killed_total": self.killed_total,
        }, indent=2), encoding="utf-8")

    def conjectures(self) -> list[dict[str, Any]]:
        N = self.horizon
        return [
            {"name": "all_reach_one", "statement": f"every n in 1..{N} reaches 1 under Collatz", "kind": "range", "N": N},
            {"name": "stopping_log_bound", "statement": f"stopping time of n\u2264{N} is < {self.bound_a:g} + {self.bound_b:g} log2(n)", "kind": "bound", "N": N, "a": self.bound_a, "b": self.bound_b},
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
                    notes.append(f"bound failed at n={n} st={st} cap={cap:.1f}")
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
        for n in list(range(1, N + 1, max(1, N // 20))) + [N]:
            if not reaches_one(n):
                attacks_landed += 1
                notes.append(f"attack hit at {n}")
                break
        status = "ADMITTED" if attacks_landed == 0 else "KILLED"
        if status == "ADMITTED":
            notes.append("checker passed; attacks missed")
        return ClaimResult(spec["name"], spec["statement"], True, checker_ok, attacks_landed, status, notes)

    def learn(self, result: ClaimResult) -> None:
        if result.name == "all_reach_one" and result.admitted:
            self.horizon = min(self.max_horizon, max(self.horizon + 200, int(self.horizon * 1.25)))
        if result.name == "stopping_log_bound" and not result.admitted:
            self.bound_a += 20.0
            self.bound_b += 2.0
        if result.name == "stopping_log_bound" and result.admitted:
            self.bound_b = max(8.0, self.bound_b - 0.25)

    def session(self, cycles: int = 3) -> list[ClaimResult]:
        catalog = self.conjectures()
        out: list[ClaimResult] = []
        for i in range(max(1, cycles)):
            result = self.run_one(catalog[i % len(catalog)])
            self.learn(result)
            if result.admitted:
                self.admitted_total += 1
            else:
                self.killed_total += 1
            out.append(result)
        self.generation += 1
        self.save()
        return out

    def run_forever(self, interval: float = 5.0) -> int:
        print(
            f"QWUACK DESK  continuous  horizon={self.horizon}  "
            f"bound={self.bound_a:g}+{self.bound_b:g}log2  interval={interval}s",
            flush=True,
        )
        try:
            while True:
                results = self.session(cycles=3)
                write_desk(results, generation=self.generation, desk=self)
                print(render_desk(results, self), flush=True)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.save()
            print("[qwuack] desk halt", flush=True)
            return 0


def write_desk(results: list[ClaimResult], generation: int = 0, desk: MathDesk | None = None, path: Path = DESK_STATUS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "throne.qwuack.desk",
        "body": "collatz",
        "hunt": MathDesk.hunt,
        "generation": generation,
        "horizon": desk.horizon if desk else None,
        "admitted": sum(1 for r in results if r.admitted),
        "killed": sum(1 for r in results if not r.admitted),
        "admitted_total": desk.admitted_total if desk else None,
        "killed_total": desk.killed_total if desk else None,
        "claims": [asdict(r) for r in results],
        "running": True,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MEMORY_PATH.open("a", encoding="utf-8") as fh:
            for r in results:
                row = asdict(r)
                row["generation"] = generation
                fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def render_desk(results: list[ClaimResult], desk: MathDesk | None = None) -> str:
    gen = desk.generation if desk else 0
    hor = desk.horizon if desk else "?"
    lines = [
        "QWUACK DESK",
        "-----------",
        "body:     collatz",
        f"gen:      {gen}",
        f"horizon:  {hor}",
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
