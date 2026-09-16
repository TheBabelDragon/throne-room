"""Tests for deterministic scoring."""

from __future__ import annotations

import unittest

from duck_gate.candidates import CandidateExcitation
from duck_gate.scoring import DEFAULT_WEIGHTS, score


class TestScoring(unittest.TestCase):
    def setUp(self) -> None:
        self.c = CandidateExcitation(
            candidate_id="s1",
            stimulus="probe",
            uncertainty=0.5,
            novelty=0.8,
            information_gain=0.4,
            cost=0.2,
        )

    def test_default_weights_explicit(self) -> None:
        self.assertEqual(DEFAULT_WEIGHTS["novelty"], 1.0)
        self.assertEqual(DEFAULT_WEIGHTS["uncertainty"], 1.0)
        self.assertEqual(DEFAULT_WEIGHTS["information_gain"], 1.0)
        self.assertEqual(DEFAULT_WEIGHTS["cost"], 1.0)

    def test_score_formula(self) -> None:
        # 1*0.8 + 1*0.5 + 1*0.4 - 1*0.2 = 1.5
        self.assertAlmostEqual(score(self.c), 1.5)

    def test_custom_weights(self) -> None:
        w = {"novelty": 2.0, "uncertainty": 0.0, "information_gain": 0.0, "cost": 1.0}
        # 2*0.8 - 1*0.2 = 1.4
        self.assertAlmostEqual(score(self.c, w), 1.4)

    def test_deterministic(self) -> None:
        a = score(self.c)
        b = score(self.c)
        self.assertEqual(a, b)

    def test_identical_candidates_identical_scores(self) -> None:
        c2 = CandidateExcitation(
            candidate_id="other",
            stimulus="probe",
            uncertainty=0.5,
            novelty=0.8,
            information_gain=0.4,
            cost=0.2,
        )
        self.assertEqual(score(self.c), score(c2))


if __name__ == "__main__":
    unittest.main()
