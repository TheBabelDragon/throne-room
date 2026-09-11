"""Multiple mathematical workers. One Duck, five jobs, one skeptic."""

from __future__ import annotations

import random
from typing import Callable

from qwuack.millennium.artifacts import Artifact
from qwuack.millennium.killer import ProofKiller
from qwuack.millennium.ponds import POND_TABLE
from qwuack.workbench.equations import EquationEngine
from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind
from qwuack.workbench.registry import ProblemSpec, shortcut_forbidden
from qwuack.workbench.store import ObjectStore


WorkerFn = Callable[["Workbench"], list[MathObject]]


def _status_from_artifact(status: str) -> ClaimStatus:
    return {
        "VERIFIED": ClaimStatus.COMPUTATIONAL_EVIDENCE,
        "REFUTED": ClaimStatus.DISPROOF,
        "PROGRESS": ClaimStatus.OBSERVATION,
        "REJECTED": ClaimStatus.REJECTED,
        "KILLED": ClaimStatus.KILLED,
    }.get(status, ClaimStatus.OBSERVATION)


def _kind_from_artifact(kind_value: str) -> ObjectKind:
    return {
        "verified_lemma": ObjectKind.LEMMA,
        "counterexample": ObjectKind.COUNTEREXAMPLE,
        "useful_transformation": ObjectKind.RESULT,
        "conjecture": ObjectKind.CONJECTURE,
        "failed_proof_strategy": ObjectKind.ATTEMPT,
        "computational_evidence": ObjectKind.EXPERIMENT,
        "formal_proof": ObjectKind.PROOF,
        "connection": ObjectKind.RESULT,
        "rejected_overclaim": ObjectKind.CLAIM,
    }.get(kind_value, ObjectKind.RESULT)


class Workbench:
    def __init__(self, spec: ProblemSpec, store: ObjectStore | None = None, generation: int = 0) -> None:
        self.spec = spec
        self.store = ObjectStore() if store is None else store
        self.generation = generation
        self.engine = EquationEngine(self.store)
        self.killer = ProofKiller()
        self.session_id = self.store.alloc.next("session")

    def seed_problem(self) -> list[MathObject]:
        existing = [o for o in self.store.of_problem(self.spec.id) if o.kind == ObjectKind.PROBLEM]
        if existing:
            return existing
        minted: list[MathObject] = []
        minted.append(self.store.mint(
            ObjectKind.PROBLEM,
            self.spec.statement,
            id=self.spec.id,
            problem=self.spec.id,
            status=ClaimStatus.OPEN if self.spec.status == "open" else ClaimStatus.PROOF,
            session=self.session_id,
            evidence={"official": self.spec.status, "forbidden": list(self.spec.forbidden_shortcuts)},
            notes=["registry_seed"],
        ))
        for name, text in self.spec.definitions:
            minted.append(self.store.mint(
                ObjectKind.DEFINITION,
                f"{name}: {text}",
                problem=self.spec.id,
                status=ClaimStatus.OBSERVATION,
                session=self.session_id,
                worker="literature",
            ))
        for fact in self.spec.known_facts:
            minted.append(self.store.mint(
                ObjectKind.FACT,
                fact,
                problem=self.spec.id,
                status=ClaimStatus.OBSERVATION,
                session=self.session_id,
                worker="literature",
                verification={"literature": "PASS"},
            ))
        minted.append(self.store.mint(
            ObjectKind.GOAL,
            "; ".join(self.spec.objective),
            problem=self.spec.id,
            status=ClaimStatus.OPEN,
            session=self.session_id,
        ))
        return minted

    def literature(self) -> list[MathObject]:
        self.seed_problem()
        return self.store.of_problem(self.spec.id)

    def numerical(self) -> list[MathObject]:
        self.seed_problem()
        pond = next((p for p in POND_TABLE if p.pond_id == self.spec.pond), None)
        if pond is None:
            return []
        rng = random.Random(1000 + self.generation)
        produced = pond.experiment(self.generation, rng)
        out: list[MathObject] = []
        for art in produced:
            obj = self._ingest_artifact(art, worker="numerical")
            if obj is not None:
                out.append(obj)
        return out

    def symbolic(self) -> list[MathObject]:
        self.seed_problem()
        out: list[MathObject] = []
        if self.spec.key == "Riemann":
            eq = self.engine.create("zeta(1/2 + i*t)", problem=self.spec.id, session=self.session_id)
            out.append(eq)
            out.append(self.engine.apply(eq, "substitute", mapping={"t": "14.134725"}))
        elif self.spec.key == "Collatz":
            eq = self.engine.create("T(n)", problem=self.spec.id, session=self.session_id)
            out.append(eq)
            out.append(self.engine.apply(eq, "substitute", mapping={"n": "27"}))
        elif self.spec.key == "P_vs_NP":
            out.append(self.engine.create("TIME(n^k) vs NTIME(n^k)", problem=self.spec.id, session=self.session_id))
        else:
            eq = self.engine.create(f"obj({self.spec.key})", problem=self.spec.id, session=self.session_id)
            out.append(self.engine.apply(eq, "simplify"))
        return out

    def proof(self) -> list[MathObject]:
        self.seed_problem()
        out: list[MathObject] = []
        evidence = [
            o for o in self.store.of_problem(self.spec.id)
            if o.kind in {ObjectKind.EXPERIMENT, ObjectKind.LEMMA}
            and o.status == ClaimStatus.COMPUTATIONAL_EVIDENCE
        ]
        for ev in evidence[-3:]:
            if shortcut_forbidden(self.spec, "finite_numerical_verification") and ev.kind == ObjectKind.EXPERIMENT:
                out.append(self.store.mint(
                    ObjectKind.CLAIM,
                    f"promote {ev.id} to a prize proof",
                    problem=self.spec.id,
                    status=ClaimStatus.REJECTED,
                    derived_from=[ev.id],
                    session=self.session_id,
                    worker="proof",
                    notes=["forbidden_shortcut:finite_numerical_verification", "NOT A PROOF"],
                    verification={"numerical": "PASS", "formal": "NOT_VERIFIED"},
                ))
                continue
            out.append(self.store.mint(
                ObjectKind.LEMMA,
                f"finite consequence of {ev.id}: {ev.statement}",
                problem=self.spec.id,
                status=ClaimStatus.LEMMA,
                derived_from=[ev.id],
                dependencies=[ev.id],
                session=self.session_id,
                worker="proof",
                verification=dict(ev.verification),
            ))
        if not out:
            out.append(self.store.mint(
                ObjectKind.TARGET,
                f"Prove / disprove a named lemma inside {self.spec.id}",
                problem=self.spec.id,
                status=ClaimStatus.EXPLORING,
                session=self.session_id,
                worker="proof",
            ))
        return out

    def skeptic(self) -> list[MathObject]:
        self.seed_problem()
        out: list[MathObject] = []
        candidates = [
            o for o in self.store.of_problem(self.spec.id)
            if o.kind in {ObjectKind.CLAIM, ObjectKind.LEMMA, ObjectKind.PROOF, ObjectKind.CONJECTURE}
            and o.status not in {ClaimStatus.KILLED, ClaimStatus.REJECTED}
        ]
        for obj in candidates[-5:]:
            if obj.status in {ClaimStatus.PROOF, ClaimStatus.FORMALLY_VERIFIED} and obj.verification.get("formal") != "PASS":
                killed = self.store.mint(
                    ObjectKind.ATTEMPT,
                    f"skeptic: {obj.id} claims proof without formal PASS",
                    problem=self.spec.id,
                    status=ClaimStatus.KILLED,
                    derived_from=[obj.id],
                    session=self.session_id,
                    worker="skeptic",
                    notes=["NOT A PROOF", "formal:NOT_VERIFIED"],
                    verification=dict(obj.verification),
                )
                obj.status = ClaimStatus.KILLED
                obj.notes = list(obj.notes) + ["demoted_by_skeptic"]
                self.store.update(obj)
                out.append(killed)
                continue
            if obj.kind == ObjectKind.PROOF:
                out.append(self.store.mint(
                    ObjectKind.ATTEMPT,
                    f"skeptic: prize-shaped proof {obj.id} is illegal without certificate",
                    problem=self.spec.id,
                    status=ClaimStatus.KILLED,
                    derived_from=[obj.id],
                    session=self.session_id,
                    worker="skeptic",
                    notes=["victory_without_verification"],
                ))
        if not out:
            out.append(self.store.mint(
                ObjectKind.ATTEMPT,
                "skeptic patrol: no prize-shaped claim found this turn",
                problem=self.spec.id,
                status=ClaimStatus.OBSERVATION,
                session=self.session_id,
                worker="skeptic",
            ))
        return out

    def _ingest_artifact(self, art: Artifact, worker: str) -> MathObject | None:
        if art.kind.value == "rejected_overclaim":
            return self.store.mint(
                ObjectKind.CLAIM,
                art.statement,
                problem=self.spec.id,
                status=ClaimStatus.REJECTED,
                session=self.session_id,
                worker=worker,
                notes=list(art.notes) + ["unbounded_not_an_experiment"],
                evidence=dict(art.evidence),
            )
        status = _status_from_artifact(art.status)
        kind = _kind_from_artifact(art.kind.value)
        if kind == ObjectKind.LEMMA and shortcut_forbidden(self.spec, "named_height_window_as_proof"):
            status = ClaimStatus.COMPUTATIONAL_EVIDENCE
            kind = ObjectKind.EXPERIMENT
        ver = {
            "numerical": "PASS" if art.status == "VERIFIED" else "NOT_RUN",
            "symbolic": "NOT_RUN",
            "literature": "NOT_RUN",
            "formal": "NOT_VERIFIED",
        }
        return self.store.mint(
            kind,
            art.statement,
            problem=self.spec.id,
            status=status,
            session=self.session_id,
            worker=worker,
            notes=list(art.notes),
            evidence={"artifact": art.name, "pond": art.pond, **dict(art.evidence)},
            verification=ver,
        )

    def turn(self) -> list[MathObject]:
        produced: list[MathObject] = []
        produced.extend(self.literature())
        produced.extend(self.symbolic())
        produced.extend(self.numerical())
        produced.extend(self.proof())
        produced.extend(self.skeptic())
        self.generation += 1
        return produced
