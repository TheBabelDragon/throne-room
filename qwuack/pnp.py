"""P vs NP desk — finite SAT experiments, not the prize.

VERIFIED: 2SAT on a named (n, seed, trials) batch.
REFUTED:  greedy 3SAT heuristic vs brute force on a named batch.
REJECTED: P=NP and P!=NP as unbounded sentences.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DESK_DIR = Path("/tmp/metafield")
STATUS = DESK_DIR / "qwuack_pnp.json"
JOURNAL = DESK_DIR / "qwuack_pnp.jsonl"
STATE = DESK_DIR / "qwuack_pnp_state.json"
LATEST = DESK_DIR / "qwuack_pnp_latest.txt"

Clause = tuple[int, ...]
Formula = list[Clause]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sat_assignment(n: int, phi: Formula, assign: list[int]) -> bool:
    for clause in phi:
        if not any((lit > 0 and assign[lit]) or (lit < 0 and not assign[-lit]) for lit in clause):
            return False
    return True


def brute_sat(n: int, phi: Formula) -> bool:
    limit = 1 << n
    for bits in range(limit):
        assign = [0] + [1 if (bits >> (v - 1)) & 1 else 0 for v in range(1, n + 1)]
        if _sat_assignment(n, phi, assign):
            return True
    return False


def greedy_sat(n: int, phi: Formula) -> bool:
    score = [0] * (n + 1)
    for clause in phi:
        for lit in clause:
            score[abs(lit)] += 1 if lit > 0 else -1
    assign = [0] + [1 if score[v] >= 0 else 0 for v in range(1, n + 1)]
    if _sat_assignment(n, phi, assign):
        return True
    for v in range(1, n + 1):
        assign[v] ^= 1
        if _sat_assignment(n, phi, assign):
            return True
        assign[v] ^= 1
    return False


def random_ksat(n: int, m: int, k: int, rng: random.Random) -> Formula:
    phi: Formula = []
    vars_ = list(range(1, n + 1))
    for _ in range(m):
        chosen = rng.sample(vars_, k)
        clause = tuple(sorted(v if rng.random() < 0.5 else -v for v in chosen))
        phi.append(clause)
    return phi


def _tarjan_2sat(n: int, phi: Formula) -> bool:
    N = 2 * n
    graph: list[list[int]] = [[] for _ in range(N)]

    def idx(lit: int) -> int:
        return (lit - 1) * 2 if lit > 0 else ((-lit - 1) * 2 + 1)

    def neg(i: int) -> int:
        return i ^ 1

    for clause in phi:
        if len(clause) == 1:
            a = clause[0]
            graph[idx(-a)].append(idx(a))
        elif len(clause) >= 2:
            a, b = clause[0], clause[1]
            graph[idx(-a)].append(idx(b))
            graph[idx(-b)].append(idx(a))

    index = 0
    stack: list[int] = []
    on = [False] * N
    ids = [-1] * N
    low = [0] * N
    comp = [-1] * N
    cid = 0

    def strong(v: int) -> None:
        nonlocal index, cid
        ids[v] = low[v] = index
        index += 1
        stack.append(v)
        on[v] = True
        for w in graph[v]:
            if ids[w] < 0:
                strong(w)
                low[v] = min(low[v], low[w])
            elif on[w]:
                low[v] = min(low[v], ids[w])
        if low[v] == ids[v]:
            while True:
                w = stack.pop()
                on[w] = False
                comp[w] = cid
                if w == v:
                    break
            cid += 1

    for v in range(N):
        if ids[v] < 0:
            strong(v)
    for i in range(n):
        if comp[2 * i] == comp[2 * i + 1]:
            return False
    return True


@dataclass
class Claim:
    name: str
    statement: str
    status: str
    elapsed_s: float
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "VERIFIED"


class PNPDesk:
    hunt = "named SAT batches; not P vs NP"

    def __init__(self, generation: int = 0, n2: int = 8, n3: int = 10, seed: int = 1) -> None:
        self.generation = generation
        self.n2 = n2
        self.n3 = n3
        self.seed = seed
        self.verified = 0
        self.refuted = 0
        self.rejected_prize = False

    @classmethod
    def load(cls, path: Path = STATE) -> "PNPDesk":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                desk = cls(
                    generation=int(data.get("generation", 0)),
                    n2=int(data.get("n2", 8)),
                    n3=int(data.get("n3", 10)),
                    seed=int(data.get("seed", 1)),
                )
                desk.verified = int(data.get("verified", 0))
                desk.refuted = int(data.get("refuted", 0))
                desk.rejected_prize = bool(data.get("rejected_prize", False))
                return desk
            except (OSError, ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({
            "generation": self.generation,
            "n2": self.n2,
            "n3": self.n3,
            "seed": self.seed,
            "verified": self.verified,
            "refuted": self.refuted,
            "rejected_prize": self.rejected_prize,
            "updated": utcnow(),
        }, indent=2), encoding="utf-8")

    def _two_sat_batch(self) -> Claim:
        trials = 40
        rng = random.Random(self.seed + 1000 * self.generation)
        t0 = time.perf_counter()
        disagree = 0
        sat_count = 0
        for i in range(trials):
            phi = random_ksat(self.n2, self.n2 * 2, 2, random.Random(rng.randint(1, 10**9)))
            fast = _tarjan_2sat(self.n2, phi)
            slow = brute_sat(self.n2, phi)
            if fast != slow:
                disagree += 1
            if slow:
                sat_count += 1
        elapsed = time.perf_counter() - t0
        status = "VERIFIED" if disagree == 0 else "REFUTED"
        return Claim(
            name="two_sat_solver",
            statement=f"implication-SCC 2SAT matches brute on n={self.n2} trials={trials} seed={self.seed+self.generation}",
            status=status,
            elapsed_s=elapsed,
            evidence={"n": self.n2, "trials": trials, "disagree": disagree, "sat": sat_count},
        )

    def _greedy_attack(self) -> Claim:
        trials = 30
        rng = random.Random(self.seed + 9000 * self.generation)
        t0 = time.perf_counter()
        misses = 0
        first = None
        for i in range(trials):
            seed_i = rng.randint(1, 10**9)
            phi = random_ksat(self.n3, self.n3 * 4, 3, random.Random(seed_i))
            brute = brute_sat(self.n3, phi)
            heur = greedy_sat(self.n3, phi)
            if brute and not heur:
                misses += 1
                if first is None:
                    first = seed_i
        elapsed = time.perf_counter() - t0
        status = "REFUTED" if misses else "VERIFIED"
        return Claim(
            name="greedy_3sat_poly_claim",
            statement=f"greedy majority solves 3SAT n={self.n3} trials={trials}",
            status=status,
            elapsed_s=elapsed,
            evidence={"n": self.n3, "trials": trials, "misses": misses, "counterexample_seed": first},
        )

    def session(self) -> list[Claim]:
        claims = [self._two_sat_batch(), self._greedy_attack()]
        for c in claims:
            if c.ok:
                self.verified += 1
            else:
                self.refuted += 1
        self.generation += 1
        if self.generation % 8 == 0 and self.n3 < 12:
            self.n3 += 1
        self.seed += 1
        self.save()
        return claims

    def persist(self, claims: list[Claim]) -> None:
        DESK_DIR.mkdir(parents=True, exist_ok=True)
        ts = utcnow()
        two = next((c for c in claims if c.name == "two_sat_solver"), None)
        grd = next((c for c in claims if c.name == "greedy_3sat_poly_claim"), None)
        snap = {
            "schema": "throne.qwuack.pnp",
            "kind": "verified_computation",
            "not_a_millennium_proof": True,
            "ts": ts,
            "generation": self.generation,
            "hunt": self.hunt,
            "verified": self.verified,
            "refuted": self.refuted,
            "claims": [asdict(c) for c in claims],
        }
        STATUS.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        with JOURNAL.open("a", encoding="utf-8") as fh:
            for c in claims:
                row = asdict(c)
                row["ts"] = ts
                row["generation"] = self.generation
                fh.write(json.dumps(row) + "\n")
        miss = (grd.evidence.get("misses") if grd else None)
        line = (
            f"{ts} PNP gen={self.generation} "
            f"2sat={two.status if two else '?'} "
            f"greedy3sat={grd.status if grd else '?'} misses={miss} "
            f"n2={self.n2} n3={self.n3} verified={self.verified} refuted={self.refuted}"
        )
        LATEST.write_text(line + "\n", encoding="utf-8")
        print(line, flush=True)

    def run_forever(self, interval: float = 5.0) -> int:
        print(f"{utcnow()} QWUACK PNP start gen={self.generation} journal={JOURNAL}", flush=True)
        if not self.rejected_prize:
            print(f"{utcnow()} REJECTED P=NP reason=unbounded_not_an_experiment", flush=True)
            print(f"{utcnow()} REJECTED P!=NP reason=unbounded_not_an_experiment", flush=True)
            self.rejected_prize = True
            self.save()
        try:
            while True:
                claims = self.session()
                self.persist(claims)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.save()
            print(f"{utcnow()} QWUACK PNP halt gen={self.generation}", flush=True)
            return 0
