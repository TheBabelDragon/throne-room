"""Tests for spectral_experiment.v1 import and QUANTUM / RIEMANN POND."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qwuack.workbench.objects import ClaimStatus, ObjectKind
from qwuack.workbench.spectral_import import (
    CONTRACT_VERSION,
    import_spectral_experiment,
    validate_spectral_experiment,
)
from qwuack.workbench.spectral_pond import SpectralPond, demo_roundtrip
from qwuack.workbench.store import ObjectStore


def _quantum_rec(**over):
    rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_q_test",
        "experiment_type": "quantum_wave_packet",
        "engine_version": "spectral-experiment.v1",
        "parameters": {"potential": "free"},
        "units": "dimensionless",
        "random_seed": 0,
        "numerical_method": "split-step-fourier",
        "output_summary": {"energy": 1.0},
        "measurements": {
            "expectedPosition": 0.0,
            "expectedMomentum": 1.0,
            "energy": {"total": 1.0, "kinetic": 1.0, "potential": 0.0},
            "normalizationError": 1e-10,
        },
        "validation": {},
        "limitations": [],
        "timestamp": "2026-11-17T00:00:00Z",
    }
    rec.update(over)
    return rec


def _riemann_rec(**over):
    rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_r_test",
        "experiment_type": "riemann_zeros",
        "engine_version": "spectral-experiment.v1",
        "parameters": {"tMin": 14, "tMax": 40},
        "units": "ordinate-t",
        "random_seed": 0,
        "numerical_method": "riemann-siegel-approx",
        "output_summary": {"candidateCount": 5},
        "measurements": {"candidateCount": 5, "meanSpacing": 4.2},
        "validation": {
            "note": "Finite numerical verification is NOT a proof of the Riemann Hypothesis.",
            "matchedCandidates": 3,
            "limitations": ["approx"],
        },
        "limitations": ["approx"],
        "timestamp": "2026-11-17T00:00:00Z",
    }
    rec.update(over)
    return rec


class TestValidate(unittest.TestCase):
    def test_valid_quantum(self):
        self.assertEqual(validate_spectral_experiment(_quantum_rec()), [])

    def test_rejects_wrong_schema(self):
        errs = validate_spectral_experiment(_quantum_rec(schema="wrong"))
        self.assertTrue(any("schema" in e for e in errs))

    def test_rejects_non_finite(self):
        rec = _quantum_rec()
        rec["measurements"]["expectedPosition"] = float("nan")
        errs = validate_spectral_experiment(rec)
        self.assertTrue(any("non-finite" in e for e in errs))

    def test_rejects_rh_solved_claim(self):
        rec = _riemann_rec()
        rec["validation"] = {"note": "RH solved by this scan"}
        errs = validate_spectral_experiment(rec)
        self.assertTrue(len(errs) >= 1)


class TestImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ObjectStore(root=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_quantum(self):
        result = import_spectral_experiment(_quantum_rec(), self.store)
        self.assertTrue(result.ok, result.errors)
        self.assertGreaterEqual(len(result.objects), 1)
        exp = result.objects[0]
        self.assertEqual(exp.kind, ObjectKind.EXPERIMENT)
        self.assertEqual(exp.verification.get("formal"), "NOT_VERIFIED")
        self.assertFalse(exp.is_proof)

    def test_import_riemann(self):
        result = import_spectral_experiment(_riemann_rec(), self.store)
        self.assertTrue(result.ok, result.errors)
        kinds = {o.kind for o in result.objects}
        self.assertIn(ObjectKind.EXPERIMENT, kinds)
        self.assertIn(ObjectKind.HYPOTHESIS, kinds)
        for o in result.objects:
            self.assertFalse(o.is_proof)

    def test_malformed_rejected(self):
        result = import_spectral_experiment({"schema": "nope"}, self.store)
        self.assertFalse(result.ok)
        self.assertEqual(len(self.store), 0)


class TestSpectralPond(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ObjectStore(root=Path(self.tmp.name))
        self.pond = SpectralPond(store=self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ingest_and_desk(self):
        r1 = self.pond.ingest(_quantum_rec())
        r2 = self.pond.ingest(_riemann_rec())
        self.assertTrue(r1.ok and r2.ok)
        desk = self.pond.render_desk()
        self.assertIn("QUANTUM / RIEMANN POND", desk)
        self.assertIn("open", desk.lower())
        snap = self.pond.snapshot()
        self.assertTrue(len(snap.provenance) >= 1)

    def test_hypothesis_and_adversarial(self):
        self.pond.ingest(_riemann_rec())
        hyp = self.pond.generate_hypothesis("testable spacing hypothesis")
        self.assertEqual(hyp.status, ClaimStatus.CONJECTURE)
        self.assertFalse(hyp.is_proof)
        adv = self.pond.adversarial_check()
        self.assertEqual(adv.status, ClaimStatus.KILLED)
        self.assertFalse(adv.is_proof)

    def test_demo_roundtrip(self):
        out = demo_roundtrip()
        self.assertTrue(out["quantum_ok"] and out["riemann_ok"])
        self.assertFalse(out["any_formal_proof"])
        self.assertTrue(len(out.get("minted_ids") or []) >= 4 or out["object_count"] >= 1)


if __name__ == "__main__":
    unittest.main()
