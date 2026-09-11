"""The Duck's desk — visible interface onto the object store."""

from __future__ import annotations

import json
from typing import Any

from qwuack.workbench.objects import ClaimStatus, ObjectKind
from qwuack.workbench.registry import ProblemSpec
from qwuack.workbench.store import ObjectStore
from qwuack.workbench.workers import Workbench


MARK = {
    ClaimStatus.LEMMA: "\u2713",
    ClaimStatus.VERIFIED_DERIVATION: "\u2713",
    ClaimStatus.COMPUTATIONAL_EVIDENCE: "\u2713",
    ClaimStatus.FORMALLY_VERIFIED: "\u2713",
    ClaimStatus.PROOF: "\u2713",
    ClaimStatus.DISPROOF: "\u2717",
    ClaimStatus.KILLED: "\u2717",
    ClaimStatus.REJECTED: "\u2717",
    ClaimStatus.FAILED: "\u2717",
    ClaimStatus.OPEN: "?",
    ClaimStatus.EXPLORING: "?",
    ClaimStatus.CONJECTURE: "?",
    ClaimStatus.OBSERVATION: "\u00b7",
    ClaimStatus.CONDITIONAL_RESULT: "?",
}


class DuckDesk:
    def __init__(self, spec: ProblemSpec, store: ObjectStore | None = None) -> None:
        self.wb = Workbench(spec, store=None if store is None else store)
        self.spec = spec

    @property
    def store(self) -> ObjectStore:
        return self.wb.store

    def session(self, cycles: int = 1) -> list[str]:
        ids: list[str] = []
        for _ in range(max(1, cycles)):
            produced = self.wb.turn()
            ids.extend(o.id for o in produced)
        self.persist()
        return ids

    def census(self) -> dict[str, int]:
        c = self.store.counts(self.spec.id)
        return {
            "objects": c.get("objects", 0),
            "failed_branches": len(self.store.failed_attempts(self.spec.id)),
            "active_conjectures": len(self.store.active_conjectures(self.spec.id)),
            "lemmas": len(self.store.lemmas(self.spec.id)),
            "equations": c.get("equation", 0),
            "experiments": c.get("experiment", 0),
        }

    def render(self) -> str:
        spec, store = self.spec, self.store
        defs = [o for o in store.of_problem(spec.id) if o.kind == ObjectKind.DEFINITION][-6:]
        facts = [o for o in store.of_problem(spec.id) if o.kind == ObjectKind.FACT][-6:]
        conjectures = store.active_conjectures(spec.id)[-6:]
        targets = [o for o in store.of_problem(spec.id) if o.kind in {ObjectKind.TARGET, ObjectKind.GOAL}][-3:]
        scratch = [o for o in store.of_problem(spec.id) if o.kind == ObjectKind.EQUATION][-6:]
        lemmas = store.lemmas(spec.id)[-5:]
        attempts = store.failed_attempts(spec.id)[-4:]
        evidence_n = [o for o in store.of_problem(spec.id) if o.kind == ObjectKind.EXPERIMENT]
        counters = [o for o in store.of_problem(spec.id) if o.kind == ObjectKind.COUNTEREXAMPLE]
        status = "EXPLORING" if spec.status == "open" else spec.status.upper()
        target = targets[-1] if targets else None
        lines = [
            "DUCK DESK",
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
            f"Problem: {spec.title}  [{spec.id}]",
            "Definitions",
        ]
        lines.extend([f"  {d.id}: {d.statement}" for d in defs] or ["  (empty)"])
        lines.append("Known facts")
        lines.extend([f"  {f.id}: {f.statement}" for f in facts] or ["  (empty)"])
        lines.append("Conjectures")
        lines.extend([f"  {c.id}: {c.statement}" for c in conjectures] or ["  (none active)"])
        lines.append("Current target")
        lines.append(f"  {target.id}: {target.statement}" if target else "  (none)")
        lines.append("Scratchpad")
        lines.extend([f"  {e.id}: {e.statement}" for e in scratch] or ["  (empty)"])
        lines.append("Proof tree")
        if target:
            lines.append(f"  \u2514\u2500 {target.id}")
            kids = lemmas[-3:]
            if not kids:
                lines.append("      \u2514\u2500 (no lemmas yet)")
            for i, lem in enumerate(kids):
                branch = "\u2514\u2500" if i == len(kids) - 1 else "\u251c\u2500"
                lines.append(f"      {branch} {lem.id} {MARK.get(lem.status, '?')}")
        else:
            lines.append("  (idle)")
        if attempts:
            lines.append("Failed branches")
            lines.extend(f"  {a.id} \u2717 {a.statement[:72]}" for a in attempts)
        lines.append("Evidence")
        lines.append(f"  symbolic: {sum(1 for o in store.of_problem(spec.id) if o.worker=='symbolic')}")
        lines.append(f"  numerical: {len(evidence_n)}")
        lines.append(f"  literature: {sum(1 for o in store.of_problem(spec.id) if o.worker=='literature')}")
        lines.append(f"  counterexamples: {len(counters)}")
        census = self.census()
        lines.append(
            f"Census: {census['objects']} objects, {census['failed_branches']} failed branches, "
            f"{census['active_conjectures']} active conjectures, {census['lemmas']} lemmas"
        )
        lines.append(f"Status: {status}")
        lines.append("RULE: proof is a typed state. Victory is illegal.")
        return "\n".join(lines) + "\n"

    def snapshot(self) -> dict[str, Any]:
        census = self.census()
        return {
            "schema": "throne.qwuack.workbench",
            "kind": "proof_workbench",
            "not_a_millennium_proof": True,
            "victory_legal": False,
            "problem": self.spec.as_dict(),
            "session": self.wb.session_id,
            "generation": self.wb.generation,
            "census": census,
            "desk": self.render(),
        }

    def persist(self) -> None:
        snap = self.snapshot()
        self.store.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.store.status_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        self.store.text_path.write_text(snap["desk"], encoding="utf-8")
        with self.store.session_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "session": self.wb.session_id,
                "problem": self.spec.id,
                "generation": self.wb.generation,
                "census": snap["census"],
            }) + "\n")
        c = snap["census"]
        print(
            f"DUCK DESK {self.spec.id} session={self.wb.session_id} "
            f"objects={c['objects']} failed={c['failed_branches']} "
            f"conjectures={c['active_conjectures']} lemmas={c['lemmas']}",
            flush=True,
        )

    def run_forever(self, interval: float = 5.0) -> int:
        import time
        print(self.render(), flush=True)
        try:
            while True:
                self.session(cycles=1)
                time.sleep(max(0.25, interval))
        except KeyboardInterrupt:
            self.persist()
            return 0
