"""Millennium Lab — the Duck's long-term objective.

conjecture → experiment → proof attempt → adversarial attack
          → formal verification → survives / dies → MEMORY → better Duck

Reward is progress. Victory is not a legal output.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qwuack.millennium.artifacts import (
    DESK_DIR,
    LATEST_PATH,
    STATE_PATH,
    STATUS_PATH,
    Artifact,
    Memory,
    utcnow,
)
from qwuack.millennium.killer import ProofKiller, apply_verdict
from qwuack.millennium.ponds import POND_TABLE, Pond, connection_artifacts


PONDS: dict[str, Pond] = {p.pond_id: p for p in POND_TABLE}
DEFAULT_ROTATION: tuple[str, ...] = (
    "rh",
    "yang_mills",
    "navier_stokes",
    "bsd",
    "hodge",
    "p_vs_np",
    "poincare",
    "collatz",
)


@dataclass
class LabState:
    generation: int = 0
    seed: int = 1
    progress: int = 0
    verified: int = 0
    refuted: int = 0
    rejected: int = 0
    killed: int = 0
    last_pond: str = ""
    rejected_prize: bool = False
    rejected_ponds: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "seed": self.seed,
            "progress": self.progress,
            "verified": self.verified,
            "refuted": self.refuted,
            "rejected": self.rejected,
            "killed": self.killed,
            "last_pond": self.last_pond,
            "rejected_prize": self.rejected_prize,
            "rejected_ponds": list(self.rejected_ponds),
            "updated": utcnow(),
        }

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "LabState":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                ponds = data.get("rejected_ponds") or []
                return cls(
                    generation=int(data.get("generation", 0)),
                    seed=int(data.get("seed", 1)),
                    progress=int(data.get("progress", 0)),
                    verified=int(data.get("verified", 0)),
                    refuted=int(data.get("refuted", 0)),
                    rejected=int(data.get("rejected", 0)),
                    killed=int(data.get("killed", 0)),
                    last_pond=str(data.get("last_pond") or ""),
                    rejected_prize=bool(data.get("rejected_prize", False)),
                    rejected_ponds=tuple(str(x) for x in ponds),
                )
            except (OSError, ValueError, TypeError):
                pass
        return cls()

    def save(self, path: Path = STATE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")


class MillenniumLab:
    hunt = "seven prize ponds plus Collatz; progress, never victory"

    def __init__(self, state: LabState | None = None, memory: Memory | None = None) -> None:
        self.state = state or LabState.load()
        self.memory = memory or Memory()
        self.memory.load()
        self.killer = ProofKiller()

    @classmethod
    def load(cls) -> "MillenniumLab":
        return cls()

    def _count(self, artifact: Artifact) -> None:
        if artifact.status == "VERIFIED":
            self.state.verified += 1
        elif artifact.status == "REFUTED":
            self.state.refuted += 1
        elif artifact.status == "REJECTED":
            self.state.rejected += 1
        elif artifact.status == "KILLED":
            self.state.killed += 1
        self.state.progress += artifact.progress

    def admit(self, raw: Artifact) -> Artifact:
        verdict = self.killer.attack(raw, self.memory)
        artifact = apply_verdict(raw, verdict)
        self.memory.append(artifact)
        self._count(artifact)
        return artifact

    def session(self, ponds: tuple[str, ...] | None = None) -> list[Artifact]:
        rotation = ponds or DEFAULT_ROTATION
        idx = self.state.generation % len(rotation)
        pond_id = rotation[idx]
        pond = PONDS[pond_id]
        rng = random.Random(self.state.seed + 97 * self.state.generation)
        produced = pond.experiment(self.state.generation, rng)
        produced.extend(connection_artifacts(self.state.generation, produced))
        admitted: list[Artifact] = []
        seen_reject = set()
        for raw in produced:
            if raw.kind.value == "rejected_overclaim":
                key = (raw.pond, raw.statement)
                already = raw.pond in self.state.rejected_ponds or key in seen_reject
                if already:
                    continue
                seen_reject.add(key)
            admitted.append(self.admit(raw))
        self.state.last_pond = pond_id
        self.state.generation += 1
        self.state.seed += 1
        if seen_reject:
            extra = tuple(sorted({a.pond for a in admitted if a.kind.value == "rejected_overclaim"}))
            self.state.rejected_ponds = tuple(sorted(set(self.state.rejected_ponds) | set(extra)))
            self.state.rejected_prize = True
        self.state.save()
        return admitted

    def persist(self, artifacts: list[Artifact]) -> None:
        DESK_DIR.mkdir(parents=True, exist_ok=True)
        ts = utcnow()
        by_status: dict[str, int] = {}
        for a in artifacts:
            by_status[a.status] = by_status.get(a.status, 0) + 1
        snap = {
            "schema": "throne.qwuack.millennium",
            "kind": "adversarial_lab",
            "not_a_millennium_proof": True,
            "victory_legal": False,
            "ts": ts,
            "generation": self.state.generation,
            "last_pond": self.state.last_pond,
            "hunt": self.hunt,
            "progress": self.state.progress,
            "verified": self.state.verified,
            "refuted": self.state.refuted,
            "rejected": self.state.rejected,
            "killed": self.state.killed,
            "this_batch": by_status,
            "ponds": {
                p.pond_id: {"title": p.title, "official": p.official, "hunt": p.hunt}
                for p in POND_TABLE
            },
            "artifacts": [a.as_dict() for a in artifacts],
        }
        STATUS_PATH.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        line = (
            f"{ts} MILLENNIUM gen={self.state.generation} pond={self.state.last_pond} "
            f"progress={self.state.progress} "
            f"verified={self.state.verified} refuted={self.state.refuted} "
            f"rejected={self.state.rejected} killed={self.state.killed} "
            f"batch={by_status}"
        )
        LATEST_PATH.write_text(line + "\n", encoding="utf-8")
        print(line, flush=True)

    def run_forever(self, interval: float = 5.0) -> int:
        import time

        print(
            f"{utcnow()} QWUACK MILLENNIUM start gen={self.state.generation} "
            f"journal={self.memory.path}",
            flush=True,
        )
        print(
            f"{utcnow()} RULE reward=progress victory=illegal "
            "every_claim_hits_proof_killer",
            flush=True,
        )
        try:
            while True:
                batch = self.session()
                self.persist(batch)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.state.save()
            print(f"{utcnow()} QWUACK MILLENNIUM halt gen={self.state.generation}", flush=True)
            return 0
