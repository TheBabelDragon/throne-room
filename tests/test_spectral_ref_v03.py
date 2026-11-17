"""Unit tests for spectral_ref (mpmath reference + classification)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from qwuack.spectral_ref.diagnostics import (
    classify_hardy_z,
    compare_hardy_z_production,
    zero_finder_diagnostic,
)
from qwuack.spectral_ref.reference import (
    ODLYZKO_ZEROS,
    hardy_z_reference,
    zero_ordinate_reference,
)


class TestReference(unittest.TestCase):
    def test_hardy_z_near_zero_at_first_odlyzko(self):
        ref = hardy_z_reference(ODLYZKO_ZEROS[0], dps=25)
        self.assertTrue(ref["finite"])
        self.assertLess(ref["abs_Z"], 1e-10)

    def test_zetazero_matches_odlyzko(self):
        z = zero_ordinate_reference(1, dps=30)
        self.assertAlmostEqual(z["t"], ODLYZKO_ZEROS[0], places=8)

    def test_nonzero_point_finite(self):
        ref = hardy_z_reference(20.0, dps=20)
        self.assertTrue(ref["finite"])
        self.assertGreater(abs(ref["Z"]), 0.1)


class TestClassification(unittest.TestCase):
    def test_known_zero_fail_when_large_residual(self):
        self.assertEqual(
            classify_hardy_z(0.3, at_known_zero=True, production_finite=True, ref_finite=True, abs_tol=1e-3),
            "FAIL",
        )

    def test_known_zero_pass_when_tiny(self):
        self.assertEqual(
            classify_hardy_z(1e-12, at_known_zero=True, production_finite=True, ref_finite=True, abs_tol=1e-3),
            "PASS",
        )

    def test_instability(self):
        self.assertEqual(
            classify_hardy_z(0.0, at_known_zero=True, production_finite=False, ref_finite=True),
            "NUMERICAL_INSTABILITY",
        )

    def test_compare_record_schema(self):
        rec = compare_hardy_z_production(14.134725141734693, -0.314, at_known_zero=True, abs_tol=1e-3)
        self.assertEqual(rec.classification, "FAIL")
        self.assertIn("abs_vs_zero", rec.residuals)

    def test_zero_finder_offset_fail(self):
        rec = zero_finder_diagnostic(14.134725, 14.534, 1e-14, abs_offset_tol=0.05)
        self.assertEqual(rec.classification, "FAIL")
        self.assertAlmostEqual(rec.residuals["abs_ordinate_offset"], 0.4, places=2)


class TestFixtures(unittest.TestCase):
    def test_fixture_file(self):
        p = Path(__file__).resolve().parent.parent / "fixtures" / "spectral_fixtures_v0.3.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertEqual(data["fixture_set_version"], "spectral-fixtures.v0.3")
        self.assertGreaterEqual(len(data["points"]), 10)


if __name__ == "__main__":
    unittest.main()
