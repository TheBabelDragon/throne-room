"""Field Intelligence v1 — world mirror, memory, counterfactual, observatory, prediction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.field_intelligence.associative_memory import AssociativeMemory, MemoryType
from agent.field_intelligence.counterfactual import CounterfactualLab, ExperimentInput
from agent.field_intelligence.decision_observatory import DecisionObservatory, SelectionMode
from agent.field_intelligence.prediction import PredictionEvalStatus, PredictionStore
from agent.field_intelligence.world_mirror import EntityStatus, WorldMirror
from agent.shared_body_perception import BodyView
from duck_gate.candidates import CandidateExcitation


class WorldMirrorTests(unittest.TestCase):
    def test_stable_identity_and_new_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mirror = WorldMirror(root=Path(td))
            v1 = BodyView(
                body_id="cyd-a", observation_id="obs-1", source_system="csi",
                source_node_id="cyd-a", observed_at="t0", ingested_at="t0i",
                status="ALIVE", synthetic=False, measurements={"csi_energy": 0.4}, energy=0.4,
            )
            ch = mirror.ingest_body_view(v1)
            self.assertTrue(any(c.kind == "NEW" for c in ch))
            ent = mirror.get_entity("cyd-a")
            self.assertIsNotNone(ent)
            assert ent is not None
            self.assertEqual(ent.status, EntityStatus.ALIVE)
            self.assertEqual(ent.measurements.get("csi_energy"), 0.4)

    def test_missing_measurement_not_zeroed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mirror = WorldMirror(root=Path(td))
            v = BodyView(
                body_id="b1", observation_id="o1", source_system="csi", source_node_id="n1",
                observed_at="t", ingested_at="t", status="ALIVE", synthetic=False,
                measurements={"csi_energy": None},
            )
            mirror.ingest_body_view(v)
            ent = mirror.get_entity("b1")
            assert ent is not None
            self.assertIsNone(ent.measurements.get("csi_energy"))

    def test_measurement_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mirror = WorldMirror(root=Path(td))
            for i, val in enumerate([0.2, 0.9]):
                mirror.ingest_body_view(BodyView(
                    body_id="b", observation_id=f"o{i}", source_system="csi", source_node_id="n",
                    observed_at="t", ingested_at="t", status="ALIVE", synthetic=False,
                    measurements={"csi_energy": val},
                ))
            snap = mirror.snapshot()
            self.assertIn("MEASUREMENT", [c.kind for c in snap.changes])

    def test_synthetic_fixture_kind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mirror = WorldMirror(root=Path(td))
            mirror.ingest_body_view(BodyView(
                body_id="syn", observation_id="s1", source_system="fixture", source_node_id="f",
                observed_at="t", ingested_at="t", status="ALIVE", synthetic=True,
                measurements={"csi_energy": 0.1},
            ))
            ent = mirror.get_entity("syn")
            assert ent is not None and ent.evidence is not None
            self.assertTrue(ent.evidence.synthetic)
            self.assertEqual(ent.evidence.kind.value, "FIXTURE")

    def test_disappear(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mirror = WorldMirror(root=Path(td))
            mirror.ingest_body_view(BodyView(
                body_id="gone", observation_id="g1", source_system="csi", source_node_id="n",
                observed_at="t", ingested_at="t", status="ALIVE", synthetic=False,
            ))
            ch = mirror.mark_missing("gone")
            self.assertIsNotNone(ch)
            self.assertEqual(mirror.get_entity("gone").status, EntityStatus.MISSING)  # type: ignore[union-attr]


class MemoryTests(unittest.TestCase):
    def test_append_and_episode_reconstruct(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mem = AssociativeMemory(path=Path(td) / "m.jsonl")
            a = mem.append(episode_id="ep1", memory_type=MemoryType.OBSERVATION, content="saw cyd-a",
                           body_id="cyd-a", observation_id="o1", evidence_refs=["o1"])
            mem.append(episode_id="ep1", memory_type=MemoryType.ACTION, content="PROBE",
                       observation_id="o1", related_memory_ids=[a.memory_id])
            mem.append(episode_id="ep1", memory_type=MemoryType.CONSEQUENCE, content="energy rose",
                       related_memory_ids=[a.memory_id])
            ep = mem.reconstruct_episode("ep1")
            self.assertEqual(len(ep), 3)
            self.assertEqual(ep[0].memory_type, MemoryType.OBSERVATION)

    def test_hypothesis_not_observation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mem = AssociativeMemory(path=Path(td) / "m.jsonl")
            h = mem.append(episode_id="ep", memory_type=MemoryType.HYPOTHESIS,
                           content="maybe optical interference", confidence=0.3)
            self.assertEqual(h.memory_type, MemoryType.HYPOTHESIS)

    def test_conflict_and_supersede(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mem = AssociativeMemory(path=Path(td) / "m.jsonl")
            a = mem.append(episode_id="e", memory_type=MemoryType.OBSERVATION, content="v1")
            b = mem.append(episode_id="e", memory_type=MemoryType.OBSERVATION, content="v2")
            mem.mark_conflict(a.memory_id, b.memory_id)
            mem.supersede(a.memory_id, b.memory_id)
            self.assertIn(b.memory_id, a.conflicts_with)
            self.assertEqual(a.superseded_by, b.memory_id)

    def test_retrieve_by_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mem = AssociativeMemory(path=Path(td) / "m.jsonl")
            mem.append(episode_id="e", memory_type=MemoryType.OBSERVATION, content="x", body_id="a")
            mem.append(episode_id="e", memory_type=MemoryType.OBSERVATION, content="y", body_id="b")
            self.assertEqual(len(mem.by_body("a")), 1)


class CounterfactualTests(unittest.TestCase):
    def test_same_inputs_same_result(self) -> None:
        lab = CounterfactualLab(root=Path(tempfile.mkdtemp()))
        inputs = [
            ExperimentInput(sequence=0, observation_payload={"seed": 1}),
            ExperimentInput(sequence=1, observation_payload={"seed": 2}, action_type="PROBE",
                            action_params={"magnitude": 0.4}),
        ]
        e1 = lab.start_experiment(episode_id="ep", baseline_inputs=inputs, seed=7)
        e2 = lab.start_experiment(episode_id="ep", baseline_inputs=inputs, seed=7)
        o1, o2 = e1.branches[0].outcome, e2.branches[0].outcome
        assert o1 and o2
        self.assertEqual(o1.final_sequence, o2.final_sequence)
        self.assertAlmostEqual(o1.energy_sum, o2.energy_sum, places=6)
        self.assertEqual(o1.kind, "SIMULATED")

    def test_alternative_branch_isolated(self) -> None:
        lab = CounterfactualLab(root=Path(tempfile.mkdtemp()))
        base = [ExperimentInput(sequence=0, observation_payload={"seed": 3})]
        exp = lab.start_experiment(episode_id="ep", baseline_inputs=base, seed=1)
        alt_inputs = [
            ExperimentInput(sequence=0, observation_payload={"seed": 3}),
            ExperimentInput(sequence=1, observation_payload={"seed": 9}, action_type="PROBE",
                            action_params={"magnitude": 0.9}),
        ]
        alt = lab.branch_alternative(exp.experiment_id, label="alt-probe", inputs=alt_inputs)
        self.assertEqual(len(exp.branches), 2)
        assert alt.outcome is not None
        self.assertEqual(alt.outcome.kind, "SIMULATED")
        lab.compare(exp.experiment_id, exp.baseline_branch_id, alt.branch_id)


class ObservatoryTests(unittest.TestCase):
    def test_duck_selection_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            obs = DecisionObservatory(path=Path(td) / "d.jsonl")
            cands = [
                CandidateExcitation("c1", "probe-a", novelty=0.2, uncertainty=0.1,
                                    information_gain=0.3, cost=0.1),
                CandidateExcitation("c2", "probe-b", novelty=0.9, uncertainty=0.5,
                                    information_gain=0.8, cost=0.2),
            ]
            r1 = obs.observe_selection(episode_id="e", observation_id="o", candidates=cands,
                                       mode=SelectionMode.DUCK)
            r2 = obs.observe_selection(episode_id="e", observation_id="o", candidates=cands,
                                       mode=SelectionMode.DUCK)
            self.assertEqual(r1.selected_candidate_id, r2.selected_candidate_id)
            self.assertEqual(r1.selected_candidate_id, "c2")

    def test_random_seeded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            obs = DecisionObservatory(path=Path(td) / "d.jsonl")
            cands = [
                CandidateExcitation("a", "x", novelty=0.1),
                CandidateExcitation("b", "y", novelty=0.1),
                CandidateExcitation("c", "z", novelty=0.1),
            ]
            r1 = obs.observe_selection(episode_id="e", observation_id="o", candidates=cands,
                                       mode=SelectionMode.RANDOM, seed=42)
            r2 = obs.observe_selection(episode_id="e", observation_id="o", candidates=cands,
                                       mode=SelectionMode.RANDOM, seed=42)
            self.assertEqual(r1.selected_candidate_id, r2.selected_candidate_id)

    def test_admission_trace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            obs = DecisionObservatory(path=Path(td) / "d.jsonl")
            cands = [CandidateExcitation("c1", "s", novelty=1.0)]
            rec = obs.observe_selection(episode_id="e", observation_id="o", candidates=cands)
            obs.record_admission(rec.decision_id, proposal_id="p1", accepted=True, tick_sequence=3)
            self.assertEqual(obs.stats()["accepted"], 1)


class PredictionTests(unittest.TestCase):
    def test_match_mismatch_partial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = PredictionStore(path=Path(td) / "p.jsonl")
            p = store.predict(episode_id="e", source_observation_ids=["o1"],
                              target_event="next_energy", expected_outcome="rise", confidence=0.6)
            self.assertEqual(p.evaluation_status, PredictionEvalStatus.PENDING)
            store.evaluate(p.prediction_id, "rise")
            self.assertEqual(p.evaluation_status, PredictionEvalStatus.MATCHED)
            p2 = store.predict(episode_id="e", source_observation_ids=["o2"],
                               target_event="next_energy", expected_outcome="fall")
            store.evaluate(p2.prediction_id, "rise sharply")
            self.assertEqual(p2.evaluation_status, PredictionEvalStatus.MISMATCHED)
            p3 = store.predict(episode_id="e", source_observation_ids=["o3"],
                               target_event="body", expected_outcome="cyd")
            store.evaluate(p3.prediction_id, "cyd-a returned")
            self.assertEqual(p3.evaluation_status, PredictionEvalStatus.PARTIAL)
            acc = store.accuracy()
            self.assertEqual(acc["n"], 3)
            self.assertEqual(acc["matched"], 1)


if __name__ == "__main__":
    unittest.main()
