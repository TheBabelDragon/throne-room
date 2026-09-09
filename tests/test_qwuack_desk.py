"""Math desk — finite claims only."""

from __future__ import annotations

import unittest

from qwuack.desk import MathDesk


class DeskTests(unittest.TestCase):
    def test_range_claim_verifies_a_named_window(self) -> None:
        desk = MathDesk(horizon=40)
        result = desk._range_claim(1, 40)
        self.assertTrue(result.experiment_ok)
        self.assertTrue(result.checker_ok)
        self.assertEqual(result.status, "VERIFIED")
        self.assertTrue(result.admitted)

    def test_unbounded_claim_is_rejected_once(self) -> None:
        desk = MathDesk()
        self.assertFalse(desk.rejected_unbounded)
        self.assertIn("named-range", desk.hunt)
        self.assertNotIn("all integers", desk.hunt)

    def test_session_emits_range_and_bound(self) -> None:
        results = MathDesk(horizon=30).session(cycles=2)
        self.assertEqual(len(results), 2)
        names = {r.name for r in results}
        self.assertEqual(names, {"range_terminates", "log_bound"})
        self.assertTrue(any(r.status in {"VERIFIED", "REFUTED"} for r in results))


if __name__ == "__main__":
    unittest.main()
