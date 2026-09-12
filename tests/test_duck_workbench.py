"""Proof-workbench — typed objects, registry, no vibe-proofs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qwuack.workbench.desk import DuckDesk
from qwuack.workbench.equations import EquationEngine, try_simplify
from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind
from qwuack.workbench.registry import MILLENNIUM, get_problem, shortcut_forbidden
from qwuack.workbench.store import ObjectStore


class RegistryTests(unittest.TestCase):
    def test_seven_clay_plus_collatz(self) -> None:
        keys = set(MILLENNIUM)
        self.assertTrue({"P_vs_NP", "Riemann", "Yang_Mills", "Navier_Stokes", "Poincare", "Hodge", "BSD", "Collatz"} <= keys)
        self.assertEqual(MILLENNIUM["Poincare"].status, "solved")
        self.assertEqual(MILLENNIUM["Riemann"].id, "MATH-MP-02")

    def test_rh_forbids_finite_numerical_verification(self) -> None:
        spec = get_problem("MATH-MP-02")
        self.assertTrue(shortcut_forbidden(spec, "finite_numerical_verification"))
        self.assertIn("rigorous_proof", spec.acceptable_completion)

    def test_lookup_by_pond(self) -> None:
        self.assertEqual(get_problem("rh").key, "Riemann")


class ClaimTypingTests(unittest.TestCase):
    def test_unverified_claim_is_not_a_proof(self) -> None:
        obj = MathObject(
            id="C-0001",
            kind=ObjectKind.CLAIM,
            statement="I think I've proven RH",
            status=ClaimStatus.CONJECTURE,
            verification={"symbolic": "PASS", "numerical": "PASS", "formal": "NOT_VERIFIED"},
        )
        self.assertFalse(obj.is_proof)
        self.assertEqual(obj.status, ClaimStatus.CONJECTURE)

    def test_formal_pass_required(self) -> None:
        obj = MathObject(
            id="P-0001",
            kind=ObjectKind.PROOF,
            statement="named lemma with certificate",
            status=ClaimStatus.PROOF,
            verification={"formal": "PASS"},
        )
        self.assertTrue(obj.is_proof)


class EquationTests(unittest.TestCase):
    def test_simplify_folds_arithmetic(self) -> None:
        text, ok = try_simplify("2+3*4")
        self.assertTrue(ok)
        self.assertEqual(text, "14")

    def test_engine_records_parent(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = ObjectStore(Path(tmp.name))
        eng = EquationEngine(store)
        parent = eng.create("2+2", problem="MATH-X-01")
        child = eng.apply(parent, "simplify")
        self.assertEqual(child.derived_from, [parent.id])
        self.assertEqual(child.statement, "4")
        self.assertTrue(child.id.startswith("E-"))
        tmp.cleanup()


class DeskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ObjectStore(Path(self.tmp.name))
        self.desk = DuckDesk(get_problem("Riemann"), store=self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_session_enumerates_objects(self) -> None:
        ids = self.desk.session(cycles=1)
        self.assertTrue(ids)
        self.assertGreater(len(self.store), 5)
        self.assertIsNotNone(self.store.get("MATH-MP-02"))
        census = self.desk.census()
        self.assertGreater(census["objects"], 0)
        text = self.desk.render()
        self.assertIn("DUCK DESK", text)
        self.assertIn("MATH-MP-02", text)
        self.assertIn("Victory is legal only by certificate.", text)

    def test_cannot_promote_window_to_prize_proof(self) -> None:
        self.desk.session(cycles=1)
        rejected = [
            o for o in self.store
            if o.status == ClaimStatus.REJECTED and o.problem == "MATH-MP-02"
        ]
        self.assertTrue(rejected)
        proofs = [o for o in self.store if o.is_proof]
        self.assertEqual(proofs, [])

    def test_every_object_has_an_id(self) -> None:
        self.desk.session(cycles=1)
        for obj in self.store:
            self.assertTrue(obj.id)
            self.assertTrue(obj.kind)


class PvsNPDeskTests(unittest.TestCase):
    def test_pnp_seeds_definitions(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        desk = DuckDesk(get_problem("P_vs_NP"), store=ObjectStore(Path(tmp.name)))
        desk.session(cycles=1)
        defs = [o.statement for o in desk.store.of_kind(ObjectKind.DEFINITION)]
        self.assertTrue(any(s.startswith("P:") for s in defs))
        self.assertTrue(any("polynomial_reduction" in s for s in defs))
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
