"""Qwuack theorem desk — verified finite computations, not theorems.

A named window that reaches 1 is VERIFIED.
A bound that breaks is REFUTED.
An unbounded prize sentence is REJECTED once, then dropped.
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
ENVELOPE_PATH = DESK_DIR / "qwuack_envelope.jsonl"
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
        return self.status in {"ADMITTED", "VERIFIED"}


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
        rejected_unbounded: bool = False,
    ) -> None:
        self.horizon = horizon
        self.bound_a = bound_a
        self.bound_b = bound_b
        self.generation = generation
        self.window_start = window_start
        self.rejected_unbounded = rejected_unbounded
        self.admitted_total = 0
        self.killed_total = 0
        self.last_worst_n = 1
        self.last_worst_st = 0
        self.last_lo = 1
        self.last_hi = 1

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
                    rejected_unbounded=bool(data.get("rejected_unbounded", False)),
                )
                desk.admitted_total = int(data.get("admitted_total", 0))
                desk.killed_total = int(data.get("killed_total", 0))
                desk.last_worst_n = int(data.get("last_worst_n", 1))
                desk.last_worst_st = int(data.get("last_worst_st", 0))
                desk.last_lo = int(data.get("last_lo", 1))
                desk.last_hi = int(data.get("last_hi", 1))
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
            "rejected_unbounded": self.rejected_unbounded,
            "admitted_total": self.admitted_total,
            "killed_total": self.killed_total,
            "last_worst_n": self.last_worst_n,
            "last_worst_st": self.last_worst_st,
            "last_lo": self.last_lo,
            "last_hi": self.last_hi,
            "updated": utcnow(),
        }, indent=2), encoding="utf-8")

    def _range_claim(self, lo: int, hi: int) -> ClaimResult:
        t0 = time.perf_counter()
        worst_n, worst_st = max_stopping(lo, hi)
        elapsed = time.perf_counter() - t0
        self.last_lo, self.last_hi = lo, hi
        if worst_st < 0:
            return ClaimResult(
                name="range_terminates",
                statement=f"every n in {lo}..{hi} reaches 1",
                status="REFUTED",
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
            name="range_terminates",
            statement=f"every n in {lo}..{hi} reaches 1",
            status="VERIFIED",
            experiment_ok=True,
            checker_ok=True,
            attacks_landed=0,
            horizon=hi,
            elapsed_s=elapsed,
            notes=[f"worst n={worst_n} st={worst_st}"],
            evidence={"lo": lo, "hi": hi, "worst_n": worst_n, "worst_stopping": worst_st},
        )

    def _bound_claim(self, lo: int, hi: int) -> ClaimResult:
        t0 = time.perf_counter()
        for n in range(lo, hi + 1):
            ok, st = reaches_one(n)
            cap = self.bound_a + self.bound_b * math.log2(max(n, 2))
            if not ok or st >= cap:
                elapsed = time.perf_counter() - t0
                return ClaimResult(
                    name="log_bound",
                    statement=f"st(n) < {self.bound_a:g}+{self.bound_b:g}*log2(n) on {lo}..{hi}",
                    status="REFUTED",
                    experiment_ok=False,
                    checker_ok=False,
                    attacks_landed=0,
                    horizon=hi,
                    elapsed_s=elapsed,
                    notes=[f"n={n} st={st} cap={cap:.1f}"],
                    evidence={"n": n, "stopping": st, "cap": cap, "a": self.bound_a, "b": self.bound_b, "lo": lo, "hi": hi},
                )
        elapsed = time.perf_counter() - t0
        return ClaimResult(
            name="log_bound",
            statement=f"st(n) < {self.bound_a:g}+{self.bound_b:g}*log2(n) on {lo}..{hi}",
            status="VERIFIED",
            experiment_ok=True,
            checker_ok=True,
            attacks_landed=0,
            horizon=hi,
            elapsed_s=elapsed,
            notes=["held"],
            evidence={"lo": lo, "hi": hi, "a": self.bound_a, "b": self.bound_b},
        )

    def next_work(self) -> list[ClaimResult]:
        if self.horizon < self.max_horizon:
            lo, hi = 1, self.horizon
        else:
            width = 500
            lo = self.window_start
            hi = lo + width - 1
            self.window_start = hi + 1
        return [self._range_claim(lo, hi), self._bound_claim(lo, hi)]

    def learn(self, result: ClaimResult) -> None:
        if result.name == "range_terminates" and result.admitted and self.horizon < self.max_horizon:
            self.horizon = min(self.max_horizon, max(self.horizon + 200, int(self.horizon * 1.25)))
        if result.name == "log_bound" and not result.admitted:
            self.bound_a += 20.0
            self.bound_b += 2.0
        if result.name == "log_bound" and result.admitted:
            self.bound_b = max(8.0, self.bound_b - 0.25)

    def session(self, cycles: int = 2) -> list[ClaimResult]:
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
            "kind": "verified_computation",
            "not_a_theorem": True,
            "ts": ts,
            "body": "collatz",
            "hunt": self.hunt,
            "generation": self.generation,
            "window": {"lo": self.last_lo, "hi": self.last_hi},
            "worst": {"n": self.last_worst_n, "stopping": self.last_worst_st},
            "bound": {"a": self.bound_a, "b": self.bound_b},
            "verified_total": self.admitted_total,
            "refuted_total": self.killed_total,
            "claims": [asdict(r) for r in results],
            "envelope": str(ENVELOPE_PATH),
            "journal": str(MEMORY_PATH),
            "state": str(STATE_PATH),
        }
        DESK_STATUS.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        with MEMORY_PATH.open("a", encoding="utf-8") as fh:
            for r in results:
                row = asdict(r)
                row["ts"] = ts
                row["generation"] = self.generation
                fh.write(json.dumps(row) + "\n")
        with ENVELOPE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": ts,
                "generation": self.generation,
                "lo": self.last_lo,
                "hi": self.last_hi,
                "worst_n": self.last_worst_n,
                "worst_stopping": self.last_worst_st,
                "bound_a": self.bound_a,
                "bound_b": self.bound_b,
            }) + "\n")
        rng = next((r for r in results if r.name == "range_terminates"), None)
        bnd = next((r for r in results if r.name == "log_bound"), None)
        line = (
            f"{ts} gen={self.generation} window={self.last_lo}..{self.last_hi} "
            f"range={rng.status if rng else '?'} bound={bnd.status if bnd else '?'} "
            f"worst_n={self.last_worst_n} st={self.last_worst_st} "
            f"cap={self.bound_a:g}+{self.bound_b:g}*log2 "
            f"verified={self.admitted_total} refuted={self.killed_total}"
        )
        LATEST_PATH.write_text(line + "\n", encoding="utf-8")
        print(line, flush=True)

    def run_forever(self, interval: float = 5.0) -> int:
        print(
            f"{utcnow()} QWUACK DESK start gen={self.generation} "
            f"window={self.window_start} envelope={ENVELOPE_PATH}",
            flush=True,
        )
        if not self.rejected_unbounded:
            print(
                f"{utcnow()} REJECTED overclaim_all_integers "
                f"reason=unbounded_not_an_experiment",
                flush=True,
            )
            self.rejected_unbounded = True
            self.save()
        try:
            while True:
                results = self.session(cycles=2)
                self.persist(results)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.save()
            print(f"{utcnow()} QWUACK DESK halt gen={self.generation}", flush=True)
            return 0
