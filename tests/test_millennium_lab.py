"""Millennium Lab — finite ponds, proof-killer, no victory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qwuack.millennium.artifacts import Artifact, ArtifactKind, Memory
from qwuack.millennium.killer import ProofKiller
from qwuack.millennium.lab import LabState, MillenniumLab
from qwuack.millennium.ponds import POND_TABLE, rh_experiment


class KillerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name) / "mem.jsonl")
        self.killer = ProofKiller()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unbounded_prize_sentence_is_rejected(self) -> None:
        raw = Artifact(
            pond="rh",
            kind=ArtifactKind.REJECTION,
            name="prize",
            statement="all non-trivial zeros of zeta have real part 1/2",
            status="REJECTED",
            generation=0,
            evidence={"unbounded": True},
        )
        verdict = self.killer.attack(raw, self.memory)
        self.assertEqual(verdict.status, "REJECTED")
        self.assertEqual(verdict.reason, "unbounded_not_an_experiment")

    def test_victory_declaration_is_killed(self) -> None:
        raw = Artifact(
            pond="p_vs_np",
            kind=ArtifactKind.FORMAL,
            name="victory",
            statement="Millennium prize is solved",
            status="VERIFIED",
            generation=0,
            evidence={"declares_prize_solved": True, "named": True, "n": 3, "certificate": "nope"},
        )
        verdict = self.killer.attack(raw, self.memory)
        self.assertEqual(verdict.status, "KILLED")
        self.assertEqual(verdict.reason, "victory_without_verification")

    def test_formal_without_certificate_dies(self) -> None:
        raw = Artifact(
            pond="hodge",
            kind=ArtifactKind.FORMAL,
            name="fake_proof",
            statement="named tet Betti numbers via a formal proof",
            status="VERIFIED",
            generation=0,
            evidence={"named": True, "complex": "tet"},
        )
        verdict = self.killer.attack(raw, self.memory)
        self.assertEqual(verdict.status, "KILLED")
        self.assertEqual(verdict.reason, "formal_without_certificate")

    def test_named_evidence_survives(self) -> None:
        raw = Artifact(
            pond="collatz",
            kind=ArtifactKind.LEMMA,
            name="window",
            statement="every n in 1..20 reaches 1",
            status="VERIFIED",
            generation=0,
            evidence={"named": True, "lo": 1, "hi": 20},
        )
        verdict = self.killer.attack(raw, self.memory)
        self.assertEqual(verdict.status, "VERIFIED")


class PondTests(unittest.TestCase):
    def test_every_pond_exists(self) -> None:
        ids = [p.pond_id for p in POND_TABLE]
        self.assertEqual(
            ids,
            ["rh", "yang_mills", "navier_stokes", "bsd", "hodge", "p_vs_np", "poincare", "collatz"],
        )

    def test_rh_finds_a_named_zero_window(self) -> None:
        arts = rh_experiment(0, __import__("random").Random(1))
        statuses = {a.name: a.status for a in arts}
        self.assertEqual(statuses["prize_sentence"], "REJECTED")
        self.assertIn(statuses["critical_line_window"], {"VERIFIED", "PROGRESS"})


class LabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        import qwuack.millennium.artifacts as A
        import qwuack.millennium.lab as L

        A.DESK_DIR = root
        A.MEMORY_PATH = root / "millennium_memory.jsonl"
        A.STATE_PATH = root / "millennium_lab.json"
        A.LATEST_PATH = root / "millennium_latest.txt"
        A.STATUS_PATH = root / "millennium_status.json"
        L.DESK_DIR = root
        L.STATE_PATH = A.STATE_PATH
        L.LATEST_PATH = A.LATEST_PATH
        L.STATUS_PATH = A.STATUS_PATH
        self.lab = MillenniumLab(state=LabState(), memory=Memory(A.MEMORY_PATH))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_session_cannot_declare_victory(self) -> None:
        batch = self.lab.session(ponds=("rh",))
        self.assertTrue(batch)
        self.assertFalse(any(a.evidence.get("declares_prize_solved") and a.status == "VERIFIED" for a in batch))
        self.assertTrue(any(a.status == "REJECTED" for a in batch))
        self.assertGreater(self.lab.state.progress, 0)

    def test_victory_artifact_never_admitted(self) -> None:
        raw = Artifact(
            pond="rh",
            kind=ArtifactKind.FORMAL,
            name="i_win",
            statement="the prize is solved",
            status="VERIFIED",
            generation=0,
            evidence={"declares_prize_solved": True, "named": True, "t_lo": 14.0, "certificate": "x"},
        )
        admitted = self.lab.admit(raw)
        self.assertEqual(admitted.status, "KILLED")

    def test_progress_not_correctness(self) -> None:
        self.lab.session(ponds=("p_vs_np",))
        self.lab.session(ponds=("collatz",))
        self.assertGreater(self.lab.state.progress, 0)
        self.assertGreaterEqual(self.lab.state.refuted + self.lab.state.verified, 1)


if __name__ == "__main__":
    unittest.main()
