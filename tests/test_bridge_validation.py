"""Spectral Bridge v0.2 — Throne Room cross-repo + adversarial + persistence."""

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
from qwuack.workbench.spectral_pond import SpectralPond
from qwuack.workbench.store import ObjectStore

EXPORTS = Path(__file__).resolve().parent.parent / "exports"


def _minimal_quantum(**over):
    rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_q_bridge",
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


def _minimal_riemann(**over):
    rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_r_bridge",
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
            "matchedCandidates": 0,
            "limitations": ["approx"],
        },
        "limitations": ["approx"],
        "timestamp": "2026-11-17T00:00:00Z",
    }
    rec.update(over)
    return rec


def _minimal_comparison(**over):
    rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_c_bridge",
        "experiment_type": "spectral_comparison",
        "engine_version": "spectral-experiment.v1",
        "parameters": {"hypothesis": {"statement": "spacing vs quantum observables (hypothesis only)"}},
        "units": "mixed",
        "random_seed": 0,
        "numerical_method": "coupled-export",
        "output_summary": {"note": "comparison only"},
        "measurements": {},
        "validation": {"note": "not a proof"},
        "limitations": [],
        "timestamp": "2026-11-17T00:00:00Z",
    }
    rec.update(over)
    return rec


def load_fixture(name: str) -> dict:
    p = EXPORTS / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # synthetic fallback when fixtures not checked in
    if "quantum" in name:
        return _minimal_quantum()
    if "riemann" in name:
        return _minimal_riemann()
    return _minimal_comparison()


class TestCrossRepoImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ObjectStore(root=Path(self.tmp.name))
        self.pond = SpectralPond(store=self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_quantum_fixture(self):
        rec = load_fixture("quantum_bridge.json")
        result = self.pond.ingest(rec, session="bridge-v02")
        self.assertTrue(result.ok, result.errors)
        for o in result.objects:
            self.assertFalse(o.is_proof)
            self.assertEqual(o.verification.get("formal"), "NOT_VERIFIED")

    def test_import_riemann_fixture(self):
        result = self.pond.ingest(load_fixture("riemann_bridge.json"))
        self.assertTrue(result.ok, result.errors)
        kinds = {o.kind for o in result.objects}
        self.assertIn(ObjectKind.EXPERIMENT, kinds)
        self.assertIn(ObjectKind.HYPOTHESIS, kinds)

    def test_import_comparison_fixture(self):
        result = self.pond.ingest(load_fixture("comparison_bridge.json"))
        self.assertTrue(result.ok, result.errors)
        self.assertIn(ClaimStatus.KILLED, {o.status for o in result.objects})

    def test_reject_corrupted_dataset(self):
        rec = load_fixture("quantum_bridge.json")
        rec["measurements"]["expectedPosition"] = float("inf")
        self.assertFalse(self.pond.ingest(rec).ok)

    def test_reject_mismatched_identity(self):
        rec = load_fixture("quantum_bridge.json")
        rec["experiment_id"] = ""
        self.assertFalse(self.pond.ingest(rec).ok)

    def test_reject_wrong_schema(self):
        rec = load_fixture("riemann_bridge.json")
        rec["schema"] = "spectral_experiment.v0"
        self.assertFalse(self.pond.ingest(rec).ok)

    def test_duplicate_import_creates_new_objects(self):
        rec = load_fixture("quantum_bridge.json")
        r1 = self.pond.ingest(rec, session="dup-a")
        r2 = self.pond.ingest(rec, session="dup-b")
        self.assertTrue(r1.ok and r2.ok)
        self.assertTrue({o.id for o in r1.objects}.isdisjoint({o.id for o in r2.objects}))


class TestAdversarial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pond = SpectralPond(store=ObjectStore(root=Path(self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_hypothesis_from_imported_experiment(self):
        r = self.pond.ingest(load_fixture("riemann_bridge.json"))
        hyp = self.pond.generate_hypothesis("GUE-like spacing is testable only.", derived_from=[o.id for o in r.objects])
        self.assertEqual(hyp.status, ClaimStatus.CONJECTURE)
        self.assertFalse(hyp.is_proof)

    def test_inject_contradictory_measurements_still_no_proof(self):
        rec = load_fixture("riemann_bridge.json")
        rec = dict(rec)
        rec["validation"] = dict(rec.get("validation") or {})
        rec["validation"]["matchedCandidates"] = 99999
        rec["measurements"] = dict(rec.get("measurements") or {})
        rec["measurements"]["candidateCount"] = 0
        result = self.pond.ingest(rec)
        if result.ok:
            for o in result.objects:
                self.assertFalse(o.is_proof)

    def test_reject_rh_solved_claim(self):
        rec = load_fixture("riemann_bridge.json")
        rec = dict(rec)
        rec["validation"] = {"note": "RH solved by this numerical scan"}
        self.assertTrue(len(validate_spectral_experiment(rec)) >= 1)
        self.assertFalse(self.pond.ingest(rec).ok)

    def test_attempt_promote_to_formal_proof_fails(self):
        r = self.pond.ingest(load_fixture("quantum_bridge.json"))
        exp = r.objects[0]
        exp.status = ClaimStatus.PROOF
        exp.verification["formal"] = "NOT_VERIFIED"
        self.assertFalse(exp.is_proof)
        adv = self.pond.adversarial_check()
        self.assertEqual(adv.status, ClaimStatus.KILLED)
        self.assertFalse(adv.is_proof)

    def test_misleading_precision_rejected_as_proof(self):
        rec = load_fixture("riemann_bridge.json")
        rec = dict(rec)
        rec["validation"] = dict(rec.get("validation") or {})
        rec["validation"]["claimed_precision"] = "1e-50 machine-certified"
        result = self.pond.ingest(rec)
        if result.ok:
            for o in result.objects:
                self.assertEqual(o.verification.get("formal"), "NOT_VERIFIED")
                self.assertFalse(o.is_proof)

    def test_counterexamples_remain_killed(self):
        r = self.pond.ingest(load_fixture("comparison_bridge.json"))
        killed = [o for o in r.objects if o.status == ClaimStatus.KILLED]
        self.assertTrue(len(killed) >= 1)
        for o in killed:
            self.assertFalse(o.is_proof)


class TestPersistence(unittest.TestCase):
    def test_append_only_and_replay_identities(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store1 = ObjectStore(root=root)
            pond1 = SpectralPond(store=store1)
            r1 = pond1.ingest(load_fixture("quantum_bridge.json"), session="persist-1")
            self.assertTrue(r1.ok)
            ids1 = [o.id for o in r1.objects]
            path = root / "duck_objects.jsonl"
            self.assertTrue(path.exists())
            lines1 = [ln for ln in path.read_text().splitlines() if ln.strip()]
            store2 = ObjectStore(root=root)
            for oid in ids1:
                self.assertIsNotNone(store2.get(oid))
            pond2 = SpectralPond(store=store2)
            r2 = pond2.ingest(load_fixture("quantum_bridge.json"), session="persist-2")
            self.assertTrue(r2.ok)
            lines2 = [ln for ln in path.read_text().splitlines() if ln.strip()]
            self.assertGreater(len(lines2), len(lines1))
            self.assertEqual(lines2[0], lines1[0])

    def test_interrupted_write_partial_line_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = ObjectStore(root=root)
            pond = SpectralPond(store=store)
            r = pond.ingest(load_fixture("riemann_bridge.json"))
            self.assertTrue(r.ok)
            path = root / "duck_objects.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write('{"id":"broken"')
            store2 = ObjectStore(root=root)
            self.assertGreaterEqual(len(store2), len(r.objects))

    def test_provenance_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            pond = SpectralPond(store=ObjectStore(root=Path(td)))
            pond.ingest(load_fixture("quantum_bridge.json"))
            pond.ingest(load_fixture("riemann_bridge.json"))
            snap = pond.snapshot()
            self.assertTrue(len(snap.provenance) >= 2)
            for p in snap.provenance:
                self.assertEqual(p.get("formal"), "NOT_VERIFIED")


class TestDesk(unittest.TestCase):
    def test_render_desk_after_imports(self):
        with tempfile.TemporaryDirectory() as td:
            pond = SpectralPond(store=ObjectStore(root=Path(td)))
            pond.ingest(load_fixture("quantum_bridge.json"))
            pond.ingest(load_fixture("riemann_bridge.json"))
            pond.generate_hypothesis("bridge hypothesis")
            pond.adversarial_check()
            desk = pond.render_desk()
            self.assertIn("QUANTUM / RIEMANN POND", desk)
            self.assertIn("open", desk.lower())


if __name__ == "__main__":
    unittest.main()
