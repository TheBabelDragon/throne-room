"""Math desk — finite claims only."""

from __future__ import annotations

import unittest

from qwuack.desk import MathDesk
from qwuack.runtime import main


class DeskTests(unittest.TestCase):
    def test_range_claim_admits(self) -> None:
        desk = MathDesk()
        result = desk.run_one(desk.conjectures()[0])
        self.assertTrue(result.experiment_ok)
        self.assertTrue(result.checker_ok)
        self.assertEqual(result.status, "ADMITTED")

    def test_unbounded_claim_dies(self) -> None:
        desk = MathDesk()
        result = desk.run_one(desk.conjectures()[-1])
        self.assertEqual(result.status, "KILLED")
        self.assertFalse(result.experiment_ok)

    def test_runtime_desk_math_cli(self) -> None:
        code = main(["--runtime", "--desk", "math", "--cycles", "3"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
