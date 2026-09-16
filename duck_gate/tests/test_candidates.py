"""Tests for CandidateExcitation purity and immutability."""

from __future__ import annotations

import unittest

from duck_gate.candidates import CandidateExcitation


class TestCandidateExcitation(unittest.TestCase):
    def test_frozen(self) -> None:
        c = CandidateExcitation(
            candidate_id="c1",
            stimulus="probe-A",
            uncertainty=0.4,
            novelty=0.7,
            information_gain=0.5,
            cost=0.1,
        )
        with self.assertRaises(Exception):
            c.novelty = 1.0  # type: ignore[misc]

    def test_as_dict_roundtrip(self) -> None:
        c = CandidateExcitation(
            candidate_id="c2",
            stimulus="attend-B",
            predicted_response="expected-signal",
            uncertainty=0.2,
            novelty=0.9,
            information_gain=0.3,
            cost=0.05,
        )
        d = c.as_dict()
        restored = CandidateExcitation.from_mapping(d)
        self.assertEqual(c, restored)

    def test_defaults(self) -> None:
        c = CandidateExcitation(candidate_id="c3", stimulus="x")
        self.assertEqual(c.predicted_response, "")
        self.assertEqual(c.uncertainty, 0.0)
        self.assertEqual(c.novelty, 0.0)
        self.assertEqual(c.information_gain, 0.0)
        self.assertEqual(c.cost, 0.0)


if __name__ == "__main__":
    unittest.main()
