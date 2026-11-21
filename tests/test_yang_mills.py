"""GaugeGap / Yang–Mills domain — mathematical integrity tests."""

from __future__ import annotations

import random
import unittest

from qwuack.workbench.registry import get_problem, shortcut_forbidden
from qwuack.workbench.yang_mills.groups import SU2, SU2Element, group_for
from qwuack.workbench.yang_mills.lattice import Lattice4D, LatticeConfig
from qwuack.workbench.yang_mills.observables import gauge_invariance_test, wilson_loop
from qwuack.workbench.yang_mills.research import run_baseline_experiment
from qwuack.workbench.yang_mills.sampling import MCConfig, run_monte_carlo
from qwuack.workbench.yang_mills.spectrum import estimate_effective_mass
from qwuack.workbench.yang_mills.wilson import WilsonAction, plaquette


class GroupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.g = SU2()
        self.rng = random.Random(0)

    def test_identity(self) -> None:
        e = self.g.identity()
        self.assertTrue(self.g.is_member(e))
        self.assertAlmostEqual(e.w, 1.0)
        self.assertAlmostEqual(e.norm_sq(), 1.0)

    def test_multiply_associative_sample(self) -> None:
        a, b, c = self.g.random(self.rng), self.g.random(self.rng), self.g.random(self.rng)
        left = self.g.multiply(self.g.multiply(a, b), c)
        right = self.g.multiply(a, self.g.multiply(b, c))
        for x, y in zip(left.as_tuple(), right.as_tuple()):
            self.assertAlmostEqual(x, y, places=8)

    def test_inverse(self) -> None:
        a = self.g.random(self.rng)
        inv = self.g.inverse(a)
        prod = self.g.multiply(a, inv)
        self.assertAlmostEqual(prod.w, 1.0, places=8)
        self.assertAlmostEqual(prod.x, 0.0, places=8)

    def test_unitarity_determinant(self) -> None:
        a = self.g.random(self.rng)
        self.assertTrue(self.g.is_member(a))
        self.assertAlmostEqual(a.norm_sq(), 1.0, places=9)

    def test_su3_not_falsely_claimed(self) -> None:
        with self.assertRaises(NotImplementedError):
            group_for("SU(3)")


class LatticeTests(unittest.TestCase):
    def test_indexing_periodic(self) -> None:
        cfg = LatticeConfig(Lx=3, Ly=3, Lz=3, Lt=3, seed=1)
        lat = Lattice4D(cfg)
        self.assertEqual(lat.site_index(0, 0, 0, 0), 0)
        self.assertEqual(lat.site_index(3, 0, 0, 0), 0)  # periodic
        self.assertEqual(lat.shift(0, 0, 1), lat.site_index(1, 0, 0, 0))

    def test_cold_start_plaquette(self) -> None:
        cfg = LatticeConfig(Lx=2, Ly=2, Lz=2, Lt=2, beta=1.0, seed=0)
        lat = Lattice4D(cfg)
        lat.cold_start()
        wa = WilsonAction(lat)
        self.assertAlmostEqual(wa.mean_plaquette(), 1.0, places=8)

    def test_plaquette_orientation(self) -> None:
        cfg = LatticeConfig(Lx=2, Ly=2, Lz=2, Lt=2, seed=0)
        lat = Lattice4D(cfg)
        lat.cold_start()
        p = plaquette(lat, 0, 0, 1)
        self.assertTrue(lat.group.is_member(p))


class ObservableTests(unittest.TestCase):
    def test_gauge_invariance(self) -> None:
        cfg = LatticeConfig(Lx=2, Ly=2, Lz=2, Lt=2, seed=5)
        lat = Lattice4D(cfg)
        rng = random.Random(5)
        lat.hot_start(rng)
        result = gauge_invariance_test(lat, rng, n_trials=3)
        self.assertTrue(result["passed"], msg=result)

    def test_wilson_loop_cold(self) -> None:
        cfg = LatticeConfig(Lx=3, Ly=3, Lz=3, Lt=3, seed=0)
        lat = Lattice4D(cfg)
        lat.cold_start()
        w = wilson_loop(lat, 1, 1)
        self.assertAlmostEqual(w, 1.0, places=8)


class StatisticalTests(unittest.TestCase):
    def test_seed_reproducibility(self) -> None:
        cfg = LatticeConfig(Lx=2, Ly=2, Lz=2, Lt=2, beta=1.5, seed=99)
        mc = MCConfig(burn_in=3, measurements=5, seed=99)
        a = run_monte_carlo(cfg, mc, cold=True)
        b = run_monte_carlo(cfg, mc, cold=True)
        self.assertEqual(a.plaquette_series, b.plaquette_series)

    def test_baseline_experiment_qualified(self) -> None:
        report = run_baseline_experiment(0, L=2, beta=1.5, burn_in=2, measurements=4)
        self.assertEqual(report["group"], "SU(2)")
        self.assertFalse(report["is_proof"])
        self.assertFalse(report["is_continuum"])
        self.assertIn("finite_lattice", report["limitations"])


class ScientificIntegrityTests(unittest.TestCase):
    def test_forbidden_shortcuts_registered(self) -> None:
        spec = get_problem("Yang_Mills")
        self.assertTrue(shortcut_forbidden(spec, "finite_lattice_as_continuum"))
        self.assertTrue(shortcut_forbidden(spec, "u1_toy_as_nonabelian_ym"))
        self.assertTrue(shortcut_forbidden(spec, "numerical_gap_proxy_as_proof"))

    def test_spectral_estimate_not_proof(self) -> None:
        est = estimate_effective_mass(
            [1.0, 0.5, 0.25, 0.12, 0.06],
            gauge_group="SU(2)",
            lattice_dims=(4, 4, 4, 4),
            coupling=2.0,
            boundary="periodic",
            observable="toy",
            sample_count=10,
            seed=1,
        )
        d = est.as_dict()
        self.assertFalse(d["is_proof"])
        self.assertIn("not_a_mathematical_proof", d["limitations"])

    def test_u1_not_nonabelian(self) -> None:
        # Integrity: registry and research protocol forbid this promotion
        spec = get_problem("MATH-MP-03")
        self.assertEqual(spec.key, "Yang_Mills")
        self.assertIn("u1_toy_as_nonabelian_ym", spec.forbidden_shortcuts)


if __name__ == "__main__":
    unittest.main()
