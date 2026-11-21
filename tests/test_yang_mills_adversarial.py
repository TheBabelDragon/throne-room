"""Adversarial GaugeGap / Yang–Mills tests: pond, killer, workbench, provenance.

Companion to tests.test_yang_mills core suite.
"""

from __future__ import annotations

import random
import unittest

from qwuack.workbench.yang_mills.research import run_baseline_experiment


class PondIntegrationTests(unittest.TestCase):
    def test_active_pond_is_su2(self) -> None:
        from qwuack.millennium.ponds import POND_TABLE, yang_mills_experiment
        pond = next(p for p in POND_TABLE if p.pond_id == "yang_mills")
        self.assertIn("SU(2)", pond.hunt)
        self.assertNotEqual(pond.hunt, "finite U(1) Wilson lattices")
        arts = yang_mills_experiment(0, random.Random(1))
        names = {a.name for a in arts}
        self.assertIn("su2_wilson_finite_lattice", names)
        self.assertIn("prize_sentence", names)
        su2 = next(a for a in arts if a.name == "su2_wilson_finite_lattice")
        self.assertEqual(su2.evidence.get("group"), "SU(2)")
        self.assertFalse(su2.evidence.get("is_continuum"))
        self.assertFalse(su2.evidence.get("is_proof"))

    def test_u1_legacy_distinguished(self) -> None:
        from qwuack.millennium.ponds import yang_mills_experiment
        arts = yang_mills_experiment(0, random.Random(1))
        u1 = next(a for a in arts if a.name == "u1_lattice_gap_proxy")
        self.assertEqual(u1.evidence.get("group"), "U(1)")
        self.assertTrue(u1.evidence.get("legacy_baseline"))

    def test_seed_reproducible_artifacts(self) -> None:
        from qwuack.millennium.ponds import yang_mills_experiment
        a = yang_mills_experiment(1, random.Random(99))
        b = yang_mills_experiment(1, random.Random(99))
        sa = next(x for x in a if x.name == "su2_wilson_finite_lattice")
        sb = next(x for x in b if x.name == "su2_wilson_finite_lattice")
        self.assertEqual(sa.evidence.get("mean_plaquette"), sb.evidence.get("mean_plaquette"))
        self.assertEqual(sa.evidence.get("seed"), sb.evidence.get("seed"))


class ProofKillerYMTests(unittest.TestCase):
    def setUp(self) -> None:
        from qwuack.millennium.artifacts import Memory
        from qwuack.millennium.killer import ProofKiller
        self.killer = ProofKiller()
        self.memory = Memory()

    def _art(self, **kwargs):
        from qwuack.millennium.artifacts import Artifact, ArtifactKind
        base = dict(
            pond="yang_mills",
            kind=ArtifactKind.EVIDENCE,
            name="t",
            statement="test",
            status="VERIFIED",
            generation=0,
            evidence={"named": True},
        )
        base.update(kwargs)
        if "kind" in kwargs and isinstance(kwargs["kind"], str):
            from qwuack.millennium.artifacts import ArtifactKind as AK
            base["kind"] = AK(kwargs["kind"]) if isinstance(kwargs["kind"], str) else kwargs["kind"]
        return Artifact(**base)

    def test_valid_su2_survives(self) -> None:
        from qwuack.millennium.artifacts import ArtifactKind
        a = self._art(
            kind=ArtifactKind.EVIDENCE,
            statement="SU(2) Wilson L=4 mean plaquette",
            evidence={
                "named": True, "L": 4, "group": "SU(2)", "family": "su2_wilson_finite",
                "is_continuum": False, "is_proof": False, "seed": 1,
            },
        )
        v = self.killer.attack(a, self.memory)
        self.assertEqual(v.status, "VERIFIED")

    def test_u1_cannot_masquerade(self) -> None:
        from qwuack.millennium.artifacts import ArtifactKind
        a = self._art(
            kind=ArtifactKind.EVIDENCE,
            statement="nonabelian result from U(1)",
            evidence={
                "named": True, "L": 4, "group": "U(1)", "family": "u1_wilson_finite",
                "is_nonabelian": True, "legacy_baseline": True,
            },
        )
        v = self.killer.attack(a, self.memory)
        self.assertEqual(v.status, "REJECTED")
        self.assertEqual(v.reason, "u1_toy_as_nonabelian_ym")

    def test_gap_proxy_not_proof(self) -> None:
        from qwuack.millennium.artifacts import ArtifactKind
        a = self._art(
            kind=ArtifactKind.LEMMA,
            statement="mass gap from numerical effective-mass proxy",
            evidence={
                "named": True, "L": 4, "group": "SU(2)", "gap_proxy": 0.4,
                "family": "su2_wilson_finite", "evidence_level": "numerical_spectral_estimate",
                "is_proof": True,
            },
        )
        v = self.killer.attack(a, self.memory)
        self.assertIn(v.status, {"REJECTED", "KILLED"})
        self.assertEqual(v.reason, "numerical_gap_proxy_as_proof")

    def test_forbidden_shortcut_tag(self) -> None:
        from qwuack.millennium.artifacts import ArtifactKind
        a = self._art(
            kind=ArtifactKind.REJECTION,
            statement="promote finite lattice to continuum",
            status="REJECTED",
            evidence={
                "named": True, "L": 4, "group": "SU(2)",
                "forbidden_shortcut": "finite_lattice_as_continuum",
                "family": "su2_wilson_finite",
            },
        )
        v = self.killer.attack(a, self.memory)
        self.assertEqual(v.status, "REJECTED")
        self.assertEqual(v.reason, "finite_lattice_as_continuum")


class WorkbenchYMPolicyTests(unittest.TestCase):
    def test_numerical_not_promoted_to_lemma(self) -> None:
        import tempfile
        from pathlib import Path
        from qwuack.workbench.desk import DuckDesk
        from qwuack.workbench.objects import ClaimStatus, ObjectKind
        from qwuack.workbench.registry import get_problem
        from qwuack.workbench.store import ObjectStore

        tmp = tempfile.TemporaryDirectory()
        desk = DuckDesk(get_problem("Yang_Mills"), store=ObjectStore(Path(tmp.name)))
        desk.session(cycles=1)
        self.assertEqual([o for o in desk.store if o.is_proof], [])
        bad_lemmas = [
            o for o in desk.store
            if o.kind == ObjectKind.LEMMA
            and o.status == ClaimStatus.LEMMA
            and o.worker == "proof"
            and o.verification.get("formal") != "PASS"
            and o.problem == "MATH-MP-03"
        ]
        self.assertEqual(bad_lemmas, [])
        self.assertTrue([o for o in desk.store if o.status == ClaimStatus.REJECTED and o.problem == "MATH-MP-03"])
        tmp.cleanup()

    def test_rejected_artifacts_remain_visible(self) -> None:
        import tempfile
        from pathlib import Path
        from qwuack.workbench.desk import DuckDesk
        from qwuack.workbench.objects import ClaimStatus
        from qwuack.workbench.registry import get_problem
        from qwuack.workbench.store import ObjectStore

        tmp = tempfile.TemporaryDirectory()
        desk = DuckDesk(get_problem("MATH-MP-03"), store=ObjectStore(Path(tmp.name)))
        desk.session(cycles=1)
        rejected = [o for o in desk.store if o.status in {ClaimStatus.REJECTED, ClaimStatus.KILLED}]
        self.assertTrue(any("NOT A PROOF" in " ".join(o.notes) or "forbidden_shortcut" in " ".join(o.notes) for o in rejected))
        tmp.cleanup()


class ProvenanceTests(unittest.TestCase):
    def test_config_hash_stable(self) -> None:
        from qwuack.workbench.yang_mills.provenance import ExperimentConfig
        a = ExperimentConfig(experiment_id="e1", seed=7, Lx=2, Ly=2, Lz=2, Lt=2)
        b = ExperimentConfig(experiment_id="e1", seed=7, Lx=2, Ly=2, Lz=2, Lt=2)
        self.assertEqual(a.config_hash(), b.config_hash())

    def test_hash_changes_with_params(self) -> None:
        from qwuack.workbench.yang_mills.provenance import ExperimentConfig
        a = ExperimentConfig(experiment_id="e1", seed=7, beta=2.0, Lx=2, Ly=2, Lz=2, Lt=2)
        b = ExperimentConfig(experiment_id="e1", seed=7, beta=2.1, Lx=2, Ly=2, Lz=2, Lt=2)
        self.assertNotEqual(a.config_hash(), b.config_hash())

    def test_invalid_seed(self) -> None:
        from qwuack.workbench.yang_mills.provenance import ExperimentConfig
        with self.assertRaises(ValueError):
            ExperimentConfig(experiment_id="e", seed=-1, Lx=2, Ly=2, Lz=2, Lt=2)

    def test_missing_provenance(self) -> None:
        from qwuack.workbench.yang_mills.provenance import validate_provenance
        gaps = validate_provenance({"group": "SU(2)"})
        self.assertIn("seed", gaps)
        self.assertIn("config_hash", gaps)

    def test_tampered_hash(self) -> None:
        from qwuack.workbench.yang_mills.provenance import ExperimentConfig, config_hash_matches
        cfg = ExperimentConfig(experiment_id="e1", seed=1, Lx=2, Ly=2, Lz=2, Lt=2)
        d = cfg.as_dict()
        self.assertTrue(config_hash_matches(d))
        d["config_hash"] = "0" * 64
        self.assertFalse(config_hash_matches(d))

    def test_baseline_includes_provenance(self) -> None:
        report = run_baseline_experiment(0, L=2, beta=1.5, burn_in=2, measurements=4)
        self.assertIn("provenance", report)
        self.assertIn("config_hash", report)
        self.assertEqual(report["evidence_class"], "FINITE_LATTICE_MC")
        self.assertTrue(report["provenance"].get("not_glueball_correlator"))


class StatsTests(unittest.TestCase):
    def test_insufficient_samples(self) -> None:
        from qwuack.workbench.yang_mills.stats import summarize_series
        s = summarize_series([1.0, 1.1], min_samples=8)
        self.assertEqual(s.classification, "INSUFFICIENT_EVIDENCE")

    def test_ok_series(self) -> None:
        from qwuack.workbench.yang_mills.stats import summarize_series
        xs = [0.5 + 0.01 * (i % 3) for i in range(40)]
        s = summarize_series(xs, min_samples=8)
        self.assertIsNotNone(s.mean)
        self.assertFalse(s.as_dict()["is_proof"])


class EvidenceClassTests(unittest.TestCase):
    def test_plaquette_not_glueball(self) -> None:
        from qwuack.workbench.yang_mills.evidence_types import EvidenceClass, promotion_allowed
        self.assertFalse(
            promotion_allowed(EvidenceClass.PLAQUETTE_AUTOCORRELATION, EvidenceClass.GLUEBALL_CORRELATOR)
        )
        self.assertFalse(promotion_allowed(EvidenceClass.EFFECTIVE_MASS_ESTIMATE, "CONTINUUM_MASS_GAP"))


class AdversarialInferenceTests(unittest.TestCase):
    def test_result_not_lemma_promotion(self) -> None:
        import tempfile
        from pathlib import Path
        from qwuack.workbench.desk import DuckDesk
        from qwuack.workbench.objects import ClaimStatus, ObjectKind
        from qwuack.workbench.registry import get_problem
        from qwuack.workbench.store import ObjectStore
        tmp = tempfile.TemporaryDirectory()
        desk = DuckDesk(get_problem("Yang_Mills"), store=ObjectStore(Path(tmp.name)))
        desk.session(cycles=1)
        for o in desk.store:
            if o.worker == "proof" and o.kind == ObjectKind.RESULT:
                self.assertEqual(o.status, ClaimStatus.COMPUTATIONAL_EVIDENCE)
                self.assertFalse(o.is_proof)
        tmp.cleanup()

    def test_u1_substitution_rejected_by_killer(self) -> None:
        from qwuack.millennium.artifacts import Artifact, ArtifactKind, Memory
        from qwuack.millennium.killer import ProofKiller
        a = Artifact(
            pond="yang_mills", kind=ArtifactKind.EVIDENCE, name="swap",
            statement="SU(2) nonabelian from U(1) data", status="VERIFIED", generation=0,
            evidence={"named": True, "L": 4, "group": "U(1)", "family": "u1_wilson_finite",
                      "is_nonabelian": True, "legacy_baseline": True},
        )
        v = ProofKiller().attack(a, Memory())
        self.assertEqual(v.reason, "u1_toy_as_nonabelian_ym")


if __name__ == "__main__":
    unittest.main()
