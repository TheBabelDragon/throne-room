"""Fail-closed mathematical victory admission.

The Duck may propose a proof. The Duck may not declare victory.
A VictoryCertificate is a typed object the workbench admits only after:

  schema → problem identity → prize rules → proof predicate
        → dependency closure → checker blob → completion rule

`victory_legal` is true only on an admitted VictoryCertificate.
It is never a global Duck / desk / lab flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from qwuack.workbench.checker import (
    CheckerCertificate,
    issue_certificate,
    statement_hash,
    verify_certificate,
)
from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind
from qwuack.workbench.registry import ProblemSpec, get_problem, shortcut_forbidden
from qwuack.workbench.store import ObjectStore


SUPPORTED_DEP_KINDS = {
    ObjectKind.LEMMA,
    ObjectKind.PROOF,
    ObjectKind.FACT,
    ObjectKind.DEFINITION,
    ObjectKind.RESULT,
    ObjectKind.COUNTEREXAMPLE,
    ObjectKind.EQUATION,
}

DEAD_STATUSES = {
    ClaimStatus.KILLED,
    ClaimStatus.REJECTED,
    ClaimStatus.FAILED,
}


@dataclass(frozen=True)
class VictoryVerdict:
    admitted: bool
    reason: str
    notes: tuple[str, ...] = ()
    closure: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "reason": self.reason,
            "notes": list(self.notes),
            "closure": list(self.closure),
        }


@dataclass
class VictoryCertificate:
    """First-class victory record. Not a mood. Not a speech act."""

    problem_id: str
    proof_id: str
    completion: str
    checker: dict[str, str]
    closure: tuple[str, ...] = ()
    victory_legal: bool = False
    reason: str = "not_admitted"
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "throne.qwuack.victory_certificate",
            "version": 1,
            "problem_id": self.problem_id,
            "proof_id": self.proof_id,
            "completion": self.completion,
            "checker": dict(self.checker),
            "closure": list(self.closure),
            "victory_legal": bool(self.victory_legal),
            "reason": self.reason,
            "notes": list(self.notes),
        }

    @classmethod
    def from_object(cls, obj: MathObject) -> "VictoryCertificate | None":
        if obj.kind != ObjectKind.CERTIFICATE:
            return None
        ev = obj.evidence or {}
        checker = ev.get("checker") if isinstance(ev.get("checker"), dict) else {}
        return cls(
            problem_id=obj.problem,
            proof_id=str(ev.get("proof_id") or ""),
            completion=str(ev.get("completion") or ""),
            checker=dict(checker),
            closure=tuple(ev.get("closure") or ()),
            victory_legal=bool(ev.get("victory_legal")),
            reason=str(ev.get("reason") or obj.status.value),
            notes=tuple(obj.notes),
        )


def dependency_closure(store: ObjectStore, root_id: str) -> tuple[tuple[str, ...], str | None]:
    """Walk dependencies / derived_from. Fail closed on missing nodes."""
    if store.get(root_id) is None:
        return (), "missing_root"
    seen: list[str] = []
    visiting: set[str] = set()

    def walk(oid: str) -> str | None:
        if oid in visiting:
            return None
        obj = store.get(oid)
        if obj is None:
            return f"missing_dependency:{oid}"
        visiting.add(oid)
        if oid not in seen:
            seen.append(oid)
        for kid in list(obj.dependencies) + list(obj.derived_from):
            err = walk(kid)
            if err:
                return err
        visiting.discard(oid)
        return None

    err = walk(root_id)
    return tuple(seen), err


def _completion_allowed(spec: ProblemSpec, completion: str) -> bool:
    return completion in spec.acceptable_completion


def evaluate_victory(
    store: ObjectStore,
    *,
    problem_id: str,
    proof_id: str,
    completion: str,
    checker_blob: dict[str, Any] | CheckerCertificate | None,
    shortcut_tags: Iterable[str] = (),
) -> VictoryVerdict:
    """Pure admission check. Does not mint. Does not speak."""
    notes: list[str] = []

    try:
        spec = get_problem(problem_id)
    except KeyError:
        return VictoryVerdict(False, "unknown_problem", notes=("unknown_problem_id",))

    if spec.id != problem_id and problem_id not in {spec.id, spec.key, spec.pond}:
        return VictoryVerdict(False, "wrong_problem_id", notes=("problem_ref_mismatch",))

    problem_id = spec.id

    if spec.key == "Poincare" and completion != "already_awarded_perelman_2010":
        return VictoryVerdict(
            False,
            "poincare_prize_reclaim",
            notes=("Poincaré prize is archival. Duck cannot re-claim it.",),
        )
    if spec.key == "Poincare":
        return VictoryVerdict(
            False,
            "poincare_not_a_duck_victory",
            notes=("already_awarded_perelman_2010 is not a VictoryCertificate.",),
        )

    if not _completion_allowed(spec, completion):
        return VictoryVerdict(
            False,
            "completion_not_acceptable",
            notes=(f"completion={completion!r} not in {spec.acceptable_completion}",),
        )

    for tag in shortcut_tags:
        if shortcut_forbidden(spec, tag):
            return VictoryVerdict(
                False,
                "forbidden_shortcut",
                notes=(f"forbidden_shortcut:{tag}",),
            )

    proof = store.get(proof_id)
    if proof is None:
        return VictoryVerdict(False, "missing_proof", notes=(f"missing_proof:{proof_id}",))
    if proof.kind != ObjectKind.PROOF:
        return VictoryVerdict(False, "not_a_proof_object", notes=(f"kind={proof.kind.value}",))
    if proof.problem and proof.problem not in {spec.id, spec.key, spec.pond}:
        return VictoryVerdict(
            False,
            "wrong_problem_id",
            notes=(f"proof.problem={proof.problem} spec={spec.id}",),
        )
    if not proof.is_proof:
        return VictoryVerdict(
            False,
            "proof_not_formally_verified",
            notes=("is_proof requires proof-class status and formal=PASS",),
        )
    covers = (
        proof.statement.strip() == spec.statement.strip()
        or bool((proof.evidence or {}).get("covers_problem"))
    )
    if not covers:
        return VictoryVerdict(
            False,
            "proof_does_not_cover_problem",
            notes=("proof statement is not the problem statement",),
        )

    closure, cerr = dependency_closure(store, proof_id)
    if cerr:
        return VictoryVerdict(False, "missing_dependencies", notes=(cerr,), closure=closure)

    for oid in closure:
        node = store.get(oid)
        if node is None:
            return VictoryVerdict(False, "missing_dependencies", notes=(f"missing_dependency:{oid}",), closure=closure)
        if node.status in DEAD_STATUSES:
            return VictoryVerdict(
                False,
                "dead_dependency",
                notes=(f"{oid}:{node.status.value}",),
                closure=closure,
            )
        if node.problem and node.problem not in {spec.id, spec.key, spec.pond, ""}:
            return VictoryVerdict(
                False,
                "wrong_problem_id",
                notes=(f"{oid} belongs to {node.problem}",),
                closure=closure,
            )
        if node.kind == ObjectKind.PROOF and not node.is_proof:
            return VictoryVerdict(
                False,
                "unsupported_dependency",
                notes=(f"{oid} is a proof without formal PASS",),
                closure=closure,
            )
        if node.kind not in SUPPORTED_DEP_KINDS | {ObjectKind.PROOF}:
            if oid != proof_id:
                notes.append(f"ignored_kind:{oid}:{node.kind.value}")

    ok, why = verify_certificate(checker_blob)
    if not ok:
        return VictoryVerdict(False, "failed_verification", notes=(why,), closure=closure)

    cert = (
        checker_blob
        if isinstance(checker_blob, CheckerCertificate)
        else CheckerCertificate.from_dict(checker_blob)
    )
    assert cert is not None
    if cert.claim_id != proof_id:
        return VictoryVerdict(
            False,
            "certificate_claim_mismatch",
            notes=(f"cert.claim_id={cert.claim_id} proof_id={proof_id}",),
            closure=closure,
        )
    if cert.problem_id not in {spec.id, spec.key, spec.pond, problem_id}:
        return VictoryVerdict(
            False,
            "wrong_problem_id",
            notes=(f"cert.problem_id={cert.problem_id} spec={spec.id}",),
            closure=closure,
        )
    if cert.statement_hash != statement_hash(proof.statement):
        return VictoryVerdict(
            False,
            "statement_hash_mismatch",
            notes=("certificate does not cover this proof statement",),
            closure=closure,
        )

    return VictoryVerdict(
        True,
        "admitted",
        notes=tuple(notes) or ("dependency_closure_pass", "checker_pass", "completion_pass"),
        closure=closure,
    )


def admit_victory(
    store: ObjectStore,
    *,
    problem_id: str,
    proof_id: str,
    completion: str,
    checker_blob: dict[str, Any] | CheckerCertificate | None,
    shortcut_tags: Iterable[str] = (),
    session: str = "",
    worker: str = "victory",
) -> MathObject:
    """Mint a certificate object. Legal victory only if the verdict admits."""
    try:
        spec = get_problem(problem_id)
        canonical_problem = spec.id
    except KeyError:
        spec = None
        canonical_problem = problem_id

    verdict = evaluate_victory(
        store,
        problem_id=problem_id,
        proof_id=proof_id,
        completion=completion,
        checker_blob=checker_blob,
        shortcut_tags=shortcut_tags,
    )
    blob = (
        checker_blob.as_dict()
        if isinstance(checker_blob, CheckerCertificate)
        else dict(checker_blob or {})
    )
    record = VictoryCertificate(
        problem_id=canonical_problem,
        proof_id=proof_id,
        completion=completion,
        checker=blob,
        closure=verdict.closure,
        victory_legal=verdict.admitted,
        reason=verdict.reason,
        notes=verdict.notes,
    )
    status = ClaimStatus.FORMALLY_VERIFIED if verdict.admitted else ClaimStatus.REJECTED
    verification = {
        "symbolic": "NOT_RUN",
        "numerical": "NOT_RUN",
        "literature": "NOT_RUN",
        "formal": "PASS" if verdict.admitted else "FAIL",
    }
    statement = (
        f"VictoryCertificate for {canonical_problem} via {proof_id}"
        if verdict.admitted
        else f"rejected VictoryCertificate for {canonical_problem}: {verdict.reason}"
    )
    return store.mint(
        ObjectKind.CERTIFICATE,
        statement,
        problem=canonical_problem,
        status=status,
        derived_from=[proof_id] if proof_id else [],
        dependencies=list(verdict.closure),
        session=session,
        worker=worker,
        notes=list(verdict.notes),
        evidence=record.as_dict(),
        verification=verification,
    )


def desk_has_legal_victory(store: ObjectStore, problem: str | None = None) -> bool:
    rows = store.of_problem(problem) if problem else list(store)
    return any(obj.victory_legal for obj in rows)


def issue_for_proof(store: ObjectStore, proof: MathObject, recipe: dict[str, Any] | None = None) -> CheckerCertificate:
    """Helper for tests / controlled desks. Still has to pass admit_victory."""
    return issue_certificate(
        claim_id=proof.id,
        problem_id=proof.problem,
        statement=proof.statement,
        recipe=recipe,
    )
