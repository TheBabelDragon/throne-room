"""Victory is legal only on an admitted VictoryCertificate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qwuack.workbench.checker import issue_certificate, verify_certificate
from qwuack.workbench.desk import DuckDesk
from qwuack.workbench.objects import ClaimStatus, ObjectKind
from qwuack.workbench.registry import get_problem
from qwuack.workbench.store import ObjectStore
from qwuack.workbench.victory import admit_victory, evaluate_victory


def _store() -> tuple[tempfile.TemporaryDirectory, ObjectStore]:
    tmp = tempfile.TemporaryDirectory()
    return tmp, ObjectStore(Path(tmp.name))


def _seed_proof(store: ObjectStore, *, problem: str = "MATH-MP-02", covers: bool = True):
    spec = get_problem(problem)
    lemma = store.mint(
        ObjectKind.LEMMA,
        "named supporting lemma",
        problem=spec.id,
        status=ClaimStatus.LEMMA,
        verification={"formal": "PASS", "symbolic": "PASS"},
    )
    statement = spec.statement if covers else "a side identity on a named window"
    proof = store.mint(
        ObjectKind.PROOF,
        statement,
        problem=spec.id,
        status=ClaimStatus.PROOF,
        dependencies=[lemma.id],
        derived_from=[lemma.id],
        verification={"formal": "PASS"},
        evidence={"covers_problem": covers},
    )
    return spec, lemma, proof


class CheckerTests(unittest.TestCase):
    def test_issued_blob_verifies(self) -> None:
        cert = issue_certificate(
            claim_id="P-0001",
            problem_id="MATH-MP-02",
            statement="hello",
        )
        ok, reason = verify_certificate(cert)
        self.assertTrue(ok)
        self.assertEqual(reason, "checker_pass")

    def test_tampered_token_fails(self) -> None:
        cert = issue_certificate(
            claim_id="P-0001",
            problem_id="MATH-MP-02",
            statement="hello",
        )
        blob = cert.as_dict()
        blob["token"] = "0" * 64
        ok, reason = verify_certificate(blob)
        self.assertFalse(ok)
        self.assertEqual(reason, "token_mismatch")

    def test_empty_blob_fails(self) -> None:
        ok, reason = verify_certificate({})
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_certificate")


class VictoryAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.store = _store()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_valid_certificate_is_legal_only_on_the_object(self) -> None:
        spec, lemma, proof = _seed_proof(self.store)
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id=spec.id,
            statement=proof.statement,
        )
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob=blob,
        )
        self.assertTrue(minted.victory_legal)
        self.assertTrue(minted.id.startswith("VC-"))
        self.assertEqual(minted.status, ClaimStatus.FORMALLY_VERIFIED)
        self.assertTrue((minted.evidence or {}).get("victory_legal"))
        self.assertIn(lemma.id, minted.dependencies)
        desk = DuckDesk(spec, store=self.store)
        snap = desk.snapshot()
        self.assertFalse(snap["victory_legal"])
        self.assertEqual(snap["victory_rule"], "legal_only_by_certificate")
        self.assertTrue(any(row["victory_legal"] for row in snap["certificates"]))
        self.assertIn("Victory is legal only by certificate.", desk.render())
        self.assertFalse(proof.victory_legal)
        self.assertFalse(lemma.victory_legal)

    def test_invalid_certificate_rejected(self) -> None:
        spec, _lemma, proof = _seed_proof(self.store)
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob={"checker_id": "nope"},
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual(minted.status, ClaimStatus.REJECTED)
        self.assertEqual((minted.evidence or {}).get("reason"), "failed_verification")

    def test_missing_dependencies_rejected(self) -> None:
        spec = get_problem("MATH-MP-02")
        proof = self.store.mint(
            ObjectKind.PROOF,
            spec.statement,
            problem=spec.id,
            status=ClaimStatus.PROOF,
            dependencies=["L-9999"],
            verification={"formal": "PASS"},
            evidence={"covers_problem": True},
        )
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id=spec.id,
            statement=proof.statement,
        )
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob=blob,
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual((minted.evidence or {}).get("reason"), "missing_dependencies")

    def test_wrong_problem_id_rejected(self) -> None:
        spec, _lemma, proof = _seed_proof(self.store, problem="MATH-MP-02")
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id="MATH-MP-01",
            statement=proof.statement,
        )
        minted = admit_victory(
            self.store,
            problem_id="MATH-MP-01",
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob=blob,
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual((minted.evidence or {}).get("reason"), "wrong_problem_id")

    def test_unknown_problem_rejected(self) -> None:
        verdict = evaluate_victory(
            self.store,
            problem_id="MATH-MP-99",
            proof_id="P-0001",
            completion="rigorous_proof",
            checker_blob=None,
        )
        self.assertFalse(verdict.admitted)
        self.assertEqual(verdict.reason, "unknown_problem")

    def test_failed_verification_rejected(self) -> None:
        spec, _lemma, proof = _seed_proof(self.store)
        proof.verification["formal"] = "NOT_VERIFIED"
        self.store.update(proof)
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id=spec.id,
            statement=proof.statement,
        )
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob=blob,
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual((minted.evidence or {}).get("reason"), "proof_not_formally_verified")

    def test_bad_checker_token_is_failed_verification(self) -> None:
        spec, _lemma, proof = _seed_proof(self.store)
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id=spec.id,
            statement=proof.statement,
        ).as_dict()
        blob["token"] = "ab" * 32
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob=blob,
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual((minted.evidence or {}).get("reason"), "failed_verification")

    def test_poincare_cannot_be_a_duck_victory(self) -> None:
        spec, _lemma, proof = _seed_proof(self.store, problem="MATH-MP-05")
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id=spec.id,
            statement=proof.statement,
        )
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="already_awarded_perelman_2010",
            checker_blob=blob,
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual((minted.evidence or {}).get("reason"), "poincare_not_a_duck_victory")

    def test_forbidden_shortcut_rejected(self) -> None:
        spec, _lemma, proof = _seed_proof(self.store, problem="MATH-MP-02")
        blob = issue_certificate(
            claim_id=proof.id,
            problem_id=spec.id,
            statement=proof.statement,
        )
        minted = admit_victory(
            self.store,
            problem_id=spec.id,
            proof_id=proof.id,
            completion="rigorous_proof",
            checker_blob=blob,
            shortcut_tags=("finite_numerical_verification",),
        )
        self.assertFalse(minted.victory_legal)
        self.assertEqual((minted.evidence or {}).get("reason"), "forbidden_shortcut")

    def test_desk_rule_text(self) -> None:
        desk = DuckDesk(get_problem("Riemann"), store=self.store)
        text = desk.render()
        self.assertIn("Victory is legal only by certificate.", text)
        self.assertNotIn("Victory is illegal.", text)


if __name__ == "__main__":
    unittest.main()
