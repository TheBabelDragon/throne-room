"""End-to-end Field Intelligence live path.

Proves a synthetic observation is traceable through:
  observation → World Mirror → Qwuack perception → memory →
  candidate/decision observatory → Operator ABI → FieldTick →
  consequence → memory update

and that the same episode is replayable in an isolated SIMULATED branch.

Honest about source: uses make_synthetic_csi (FIXTURE path), not physical
hardware. Live CSI journals attach via the same Runtime.cycle hooks.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.field_intelligence.associative_memory import MemoryType
from agent.loop import World
from agent.perception import make_synthetic_csi
from qwuack.runtime import Runtime


class LivePathTests(unittest.TestCase):
    def test_full_trace_observation_to_consequence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            world = World()
            rt = Runtime(world=world, status_path=None, field_intelligence=True, fi_root=root)
            self.assertIsNotNone(rt.fi)

            obs = make_synthetic_csi(1, body="cyd-fixture")
            turn = rt.cycle(obs)

            self.assertIsNotNone(turn)
            assert rt.fi is not None
            report = rt.fi.episode_report()

            # observation landed in World Mirror
            entities = report["mirror"]["entities"]
            self.assertTrue(any(e["body_id"] == "cyd-fixture" for e in entities))

            # memory has OBSERVATION + ACTION + CONSEQUENCE
            types = [m["memory_type"] for m in report["memory"]]
            self.assertIn("OBSERVATION", types)
            self.assertIn("ACTION", types)
            self.assertIn("CONSEQUENCE", types)

            # decision observatory saw admission
            self.assertGreaterEqual(report["decisions"]["total"], 1)

            # prediction evaluated against consequence
            self.assertGreaterEqual(report["predictions"]["n"], 1)

            # trace closed
            self.assertEqual(len(report["trace"]), 1)
            step = report["trace"][0]
            self.assertEqual(step["body_id"], "cyd-fixture")
            self.assertTrue(step["synthetic"])
            self.assertEqual(step["mode"], "FIXTURE")
            self.assertIsNotNone(step["tick_hash"])
            self.assertEqual(step["observation_id"], turn.perception.id)
            self.assertEqual(step["action_type"], turn.proposal.action_type)

            # episode reconstructable
            ep = rt.fi.memory.reconstruct_episode(rt.fi.episode_id)
            self.assertGreaterEqual(len(ep), 3)
            self.assertEqual(ep[0].memory_type, MemoryType.OBSERVATION)

    def test_episode_replayable_and_alternative_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rt = Runtime(world=World(), status_path=None, field_intelligence=True, fi_root=root)
            assert rt.fi is not None

            for i in range(1, 4):
                rt.cycle(make_synthetic_csi(i, body="cyd-fixture"))

            self.assertEqual(len(rt.fi.episode_inputs), 3)
            exp = rt.fi.replay_episode(seed=11)
            self.assertEqual(len(exp.branches), 1)
            base = exp.branches[0]
            self.assertIsNotNone(base.outcome)
            assert base.outcome is not None
            self.assertEqual(base.outcome.kind, "SIMULATED")

            alt = rt.fi.alternative_action(
                exp.experiment_id,
                label="alt-PROBE",
                action_type="PROBE",
                action_params={"magnitude": 0.5},
            )
            self.assertEqual(alt.label, "alt-PROBE")
            self.assertIsNotNone(alt.outcome)
            assert alt.outcome is not None
            self.assertEqual(alt.outcome.kind, "SIMULATED")

            # live FieldTick sequence must be unchanged by counterfactual
            live_seq = rt.world.scheduler.sequence
            cmp = rt.fi.lab.compare(
                exp.experiment_id,
                exp.baseline_branch_id,
                alt.branch_id,
            )
            self.assertEqual(rt.world.scheduler.sequence, live_seq)
            self.assertIn("SIMULATED", cmp.notes)

    def test_disable_bridge(self) -> None:
        rt = Runtime(world=World(), status_path=None, field_intelligence=False)
        self.assertIsNone(rt.fi)
        turn = rt.cycle(force_synthetic=True)
        self.assertIsNotNone(turn)

    def test_multi_step_memory_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rt = Runtime(
                world=World(),
                status_path=None,
                field_intelligence=True,
                fi_root=Path(td),
            )
            assert rt.fi is not None
            rt.cycle(make_synthetic_csi(1, body="alpha"))
            rt.cycle(make_synthetic_csi(2, body="alpha"))
            hits = rt.fi.retrieve_for_body("alpha")
            self.assertGreaterEqual(len(hits), 1)
            self.assertTrue(all(h.body_id == "alpha" for h in hits))


if __name__ == "__main__":
    unittest.main()
