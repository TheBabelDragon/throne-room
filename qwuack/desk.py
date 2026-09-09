"""Qwuack theorem desk — finite claims, recoverable artifacts.

Human log is one line per claim.
Machine log is append-only JSONL.
State file is enough to resume after sleep or crash.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DESK_DIR = Path("/tmp/metafield")
DESK_STATUS = DESK_DIR / "qwuack_desk.json"
MEMORY_PATH = DESK_DIR / "qwuack_memory.jsonl"
STATE_PATH = DESK_DIR / "qwuack_desk_state.json"
LATEST_PATH = DESK_DIR / "qwuack_desk_latest.txt"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collatz_next(n: int) -> int:
    return n // 2 if n % 2 == 0 else 3 * n + 1


def reaches_one(n: int, cap: int = 2_000_000) -> tuple[bool, int]:
    x = n
    steps = 0
    while x != 1 and steps < cap:
        x = collatz_next(x)
        steps += 1
    return x == 1, steps


def max_stopping(lo: int, hi: int) -> tuple[int, int]:
    worst_n = lo
    worst_st = 0
    for n in range(lo, hi + 1):
        ok, st = reaches_one(n)
        if not ok:
            return n, -1
        if st > worst_st:
            worst_n, worst_st = n, st
    return worst_n, worst_st


@dataclass
class ClaimResult:
    name: str
    statement: str
    status: str
    experiment_ok: bool
    checker_ok: bool
    attacks_landed: int
    horizon: int
    elapsed_s: float
    notes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def admitted(self) -> bool:
        return self.status == "ADMITTED"

    def line(self, ts: str, gen: int) -> str:
        return (
            f"{ts}  gen={gen:<4}  {self.status:<8}  {self.name:<24}  "
            f"{self.statement}  {self.notes[-1] if self.notes else ''}"
        ).rstrip()


class MathDesk:
    hunt = "named-range Collatz termination and least log bound"
    max_horizon = 20_000

    def __init__(
        self,
        horizon: int = 400,
        bound_a: float = 40.0,
        bound_b: float = 12.0,
        generation: int = 0,
        window_start: int = 20_001,
    ) -> None:
        self.horizon = horizon
        self.bound_a = bound_a
        self.bound_b = bound_b
        self.generation = generation
        self.window_start = window_start
        self.admitted_total = 0
        self.killed_total = 0
        self.last_worst_n = 1
        self.last_worst_st = 0

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
                    window_start=int(data.get("window_start", 20_001)),
                )
                desk.admitted_total = int(data.get("admitted_total", 0))
                desk.killed_total = int(data.get("killed_total", 0))
                desk.last_worst_n = int(data.get("last_worst_n", 1))
                desk.last_worst_st = int(data.get("last_worst_st", 0))
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
            "window_start": self.window_start,
            "admitted_total": self.admitted_total,
            "killed_total": self.killed_total,
            "last_worst_n": self.last_worst_n,
            "last_worst_st": self.last_worst_st,
            "updated": utcnow(),
        }, indent=2), encoding="utf-8")

    def _range_claim(self, lo: int, hi: int) -> ClaimResult:
        t0 = time.perf_counter()
        worst_n, worst_st = max_stopping(lo, hi)
        elapsed = time.perf_counter() - t0
        if worst_st < 0:
            return ClaimResult(
                name="all_reach_one",
                statement=f"every n in {lo}..{hi} reaches 1",
                status="KILLED",
                experiment_ok=False,
                checker_ok=False,
                attacks_landed=1,
                horizon=hi,
                elapsed_s=elapsed,
                notes=[f"failed at n={worst_n}"],
                evidence={"lo": lo, "hi": hi, "failed_at": worst_n},
            )
        self.last_worst_n, self.last_worst_st = worst_n, worst_st
        return ClaimResult(
            name="all_reach_one",
            statement=f"every n in {lo}..{hi} reaches 1",
            status="ADMITTED",
            experiment_ok=True,
            checker_ok=True,
            attacks_landed=0,
            horizon=hi,
            elapsed_s=elapsed,
            notes=[f"worst n={worst_n} stopping={worst_st}"],
            evidence={"lo": lo, "hi": hi, "worst_n": worst_n, "worst_stopping": worst_st},
        )

    def _bound_claim(self, lo: int, hi: int) -> ClaimResult:
        t0 = time.perf_counter()
        notes: list[str] = []
        for n in range(lo, hi + 1):
            ok, st = reaches_one(n)
            cap = self.bound_a + self.bound_b * math.log2(max(n, 2))
            if not ok or st >= cap:
                elapsed = time.perf_counter() - t0
                return ClaimResult(
                    name="stopping_log_bound",
                    statement=f"st(n) < {self.bound_a:g} + {self.bound_b:g}*log2(n) for n={lo}..{hi}",
                    status="KILLED",
                    experiment_ok=False,
                    checker_ok=False,
                    attacks_landed=0,
                    horizon=hi,
                    elapsed_s=elapsed,
                    notes=[f"broke at n={n} st={st} cap={cap:.1f}"],
                    evidence={"n": n, "stopping": st, "cap": cap, "a": self.bound_a, "b": self.bound_b},
                )
        elapsed = time.perf_counter() - t0
        return ClaimResult(
            name="stopping_log_bound",
            statement=f"st(n) < {self.bound_a:g} + {self.bound_b:g}*log2(n) for n={lo}..{hi}",
            status="ADMITTED",
            experiment_ok=True,
            checker_ok=True,
            attacks_landed=0,
            horizon=hi,
            elapsed_s=elapsed,
            notes=["bound held on named range"],
            evidence={"lo": lo, "hi": hi, "a": self.bound_a, "b": self.bound_b},
        )

    def _unbounded_claim(self) -> ClaimResult:
        return ClaimResult(
            name="overclaim_all_integers",
            statement="every positive integer reaches 1",
            status="KILLED",
            experiment_ok=False,
            checker_ok=False,
            attacks_landed=1,
            horizon=self.horizon,
            elapsed_s=0.0,
            notes=["unbounded prize sentence is not an experiment"],
            evidence={"reason": "no named bound"},
        )

    def next_work(self) -> list[ClaimResult]:
        if self.horizon < self.max_horizon:
            lo, hi = 1, self.horizon
        else:
            width = 500
            lo = self.window_start
            hi = lo + width - 1
            self.window_start = hi + 1
        return [
            self._range_claim(lo, hi),
            self._bound_claim(lo, hi),
            self._unbounded_claim(),
        ]

    def learn(self, result: ClaimResult) -> None:
        if result.name == "all_reach_one" and result.admitted and self.horizon < self.max_horizon:
            self.horizon = min(self.max_horizon, max(self.horizon + 200, int(self.horizon * 1.25)))
        if result.name == "stopping_log_bound" and not result.admitted:
            self.bound_a += 20.0
            self.bound_b += 2.0
        if result.name == "stopping_log_bound" and result.admitted:
            self.bound_b = max(8.0, self.bound_b - 0.25)

    def session(self, cycles: int = 3) -> list[ClaimResult]:
        results = self.next_work()[: max(1, cycles)]
        for result in results:
            self.learn(result)
            if result.admitted:
                self.admitted_total += 1
            else:
                self.killed_total += 1
        self.generation += 1
        self.save()
        return results

    def persist(self, results: list[ClaimResult]) -> None:
        DESK_DIR.mkdir(parents=True, exist_ok=True)
        ts = utcnow()
        snapshot = {
            "schema": "throne.qwuack.desk",
            "ts": ts,
            "body": "collatz",
            "hunt": self.hunt,
            "generation": self.generation,
            "horizon": self.horizon,
            "window_start": self.window_start,
            "bound": {"a": self.bound_a, "b": self.bound_b},
            "admitted_batch": sum(1 for r in results if r.admitted),
            "killed_batch": sum(1 for r in results if not r.admitted),
            "admitted_total": self.admitted_total,
            "killed_total": self.killed_total,
            "worst": {"n": self.last_worst_n, "stopping": self.last_worst_st},
            "claims": [asdict(r) for r in results],
            "journal": str(MEMORY_PATH),
            "state": str(STATE_PATH),
            "running": True,
        }
        DESK_STATUS.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        with MEMORY_PATH.open("a", encoding="utf-8") as fh:
            for r in results:
                row = asdict(r)
                row["ts"] = ts
                row["generation"] = self.generation
                fh.write(json.dumps(row) + "\n")
        lines = [r.line(ts, self.generation) for r in results]
        footer = (
            f"{ts}  gen={self.generation:<4}  TOTALS    admitted={self.admitted_total}  "
            f"killed={self.killed_total}  horizon={self.horizon}  "
            f"window={self.window_start}  state={STATE_PATH}"
        )
        text = "\n".join(lines + [footer, ""])
        LATEST_PATH.write_text(text, encoding="utf-8")
        print(text, end="", flush=True)

    def run_forever(self, interval: float = 5.0) -> int:
        print(
            f"{utcnow()}  QWUACK DESK start  horizon={self.horizon}  "
            f"bound={self.bound_a:g}+{self.bound_b:g}*log2  interval={interval}s  "
            f"journal={MEMORY_PATH}",
            flush=True,
        )
        try:
            while True:
                results = self.session(cycles=3)
                self.persist(results)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.save()
            print(f"{utcnow()}  QWUACK DESK halt  gen={self.generation}", flush=True)
            return 0
