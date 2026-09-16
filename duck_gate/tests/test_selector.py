"""Tests for pure selector: RANDOM vs DUCK, determinism, boundary."""

from __future__ import annotations

import random
import unittest

from duck_gate.candidates import CandidateExcitation
from duck_gate.scoring import score
from duck_gate.selector import Mode, select


def _cands() -> list[CandidateExcitation]:
    return [
        CandidateExcitation(
            candidate_id="low",
            stimulus="a",
            novelty=0.1,
            uncertainty=0.1,
            information_gain=0.1,
            cost=0.5,
        ),
        CandidateExcitation(
            candidate_id="mid",
            stimulus="b",
            novelty=0.5,
            uncertainty=0.5,
            information_gain=0.5,
            cost=0.2,
        ),
        CandidateExcitation(
            candidate_id="high",
            stimulus="c",
            novelty=0.9,
            uncertainty=0.8,
            information_gain=0.7,
            cost=0.1,
        ),
    ]


class TestSelector(unittest.TestCase):
    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            select([], Mode.DUCK)

    def test_duck_selects_highest_score(self) -> None:
        chosen = select(_cands(), Mode.DUCK)
        self.assertEqual(chosen.candidate_id, "high")
        # high score = 0.9+0.8+0.7-0.1 = 2.3
        self.assertAlmostEqual(score(chosen), 2.3)

    def test_duck_deterministic(self) -> None:
        a = select(_cands(), Mode.DUCK)
        b = select(_cands(), Mode.DUCK)
        self.assertEqual(a, b)

    def test_duck_stable_tie_break(self) -> None:
        tied = [
            CandidateExcitation(
                candidate_id="z-last",
                stimulus="x",
                novelty=1.0,
                uncertainty=0.0,
                information_gain=0.0,
                cost=0.0,
            ),
            CandidateExcitation(
                candidate_id="a-first",
                stimulus="y",
                novelty=1.0,
                uncertainty=0.0,
                information_gain=0.0,
                cost=0.0,
            ),
        ]
        # same score; key is (-score, candidate_id) so "a-first" wins
        chosen = select(tied, Mode.DUCK)
        self.assertEqual(chosen.candidate_id, "a-first")

    def test_random_requires_rng(self) -> None:
        with self.assertRaises(ValueError):
            select(_cands(), Mode.RANDOM)

    def test_random_uses_injected_rng(self) -> None:
        rng = random.Random(42)
        chosen = select(_cands(), Mode.RANDOM, rng=rng)
        self.assertIn(chosen.candidate_id, {"low", "mid", "high"})

    def test_random_deterministic_with_seed(self) -> None:
        a = select(_cands(), Mode.RANDOM, rng=random.Random(7))
        b = select(_cands(), Mode.RANDOM, rng=random.Random(7))
        self.assertEqual(a, b)

    def test_random_differs_from_duck_on_same_set(self) -> None:
        # With a fixed seed that does not always pick the max, policies differ.
        # We only require that the two modes can produce different outcomes
        # across the same candidate set (distinguishable policies).
        duck = select(_cands(), Mode.DUCK)
        # Exhaust a few seeds; at least one should differ from the argmax.
        differed = False
        for seed in range(50):
            rnd = select(_cands(), Mode.RANDOM, rng=random.Random(seed))
            if rnd.candidate_id != duck.candidate_id:
                differed = True
                break
        self.assertTrue(differed, "RANDOM and DUCK should be distinguishable")

    def test_returns_candidate_not_action_proposal(self) -> None:
        chosen = select(_cands(), Mode.DUCK)
        self.assertIsInstance(chosen, CandidateExcitation)
        self.assertFalse(hasattr(chosen, "action_type"))
        self.assertFalse(hasattr(chosen, "capability"))

    def test_mode_accepts_string(self) -> None:
        chosen = select(_cands(), "duck")
        self.assertEqual(chosen.candidate_id, "high")


if __name__ == "__main__":
    unittest.main()
