"""Qwuack runtime + smallest closed loop through the existing spine."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.engine import N
from agent.perception import make_synthetic_csi
from agent.schemas import SYS, Channel
from qwuack.identity import QWUACK
from qwuack.runtime import Runtime, Status


class RuntimeTests(unittest.TestCase):
    def test_wake_stamps_self_not_field(self) -> None:
        runtime = Runtime()
        energy = runtime.world.scheduler.field.sum(Channel.Energy)
        status = runtime.wake()
        self.assertEqual(status.state, "awake")
        self.assertEqual(runtime.world.self.peek("identity.name"), "Qwuack")
        self.assertEqual(runtime.world.self.peek("identity.species"), "duck")
        self.assertEqual(runtime.world.self.peek("identity.habitat"), "lake")
        self.assertEqual(runtime.world.scheduler.field.sum(Channel.Energy), energy)

    def test_status_surface(self) -> None:
        status = Status(state="awake", last_action="ATTEND", authorization="granted")
        text = status.render()
        self.assertIn("QWUACK", text)
        self.assertIn("habitat:", text)
        self.assertIn("ATTEND", text)


class ClosedLoopTests(unittest.TestCase):
    def test_fixture_observation_through_tick(self) -> None:
        runtime = Runtime()
        runtime.wake()
        field = runtime.world.scheduler.field
        seq0 = runtime.world.scheduler.sequence

        obs = make_synthetic_csi(8)
        peak, _ = field.peak(Channel.Energy)
        old_here = field.sample(peak, Channel.Energy)

        turn = runtime.cycle(obs)
        self.assertEqual(turn.proposal.originating_observation, turn.perception.id)
        self.assertTrue(turn.proposal.capability)
        self.assertEqual(turn.proposal.agent_id, QWUACK.agent_id)
        self.assertGreater(turn.tick, seq0)
        self.assertEqual(turn.tick, runtime.world.scheduler.sequence)

        self.assertEqual(turn.proposal.action_type, "PROBE")
        self.assertTrue(turn.decision.accepted)
        self.assertTrue(turn.decision.deltas)
        for delta in turn.decision.deltas:
            self.assertEqual(delta.channel, Channel.Energy)
            self.assertGreaterEqual(delta.new_value, delta.old_value)
            self.assertTrue(0 <= delta.cell.x < N)
            self.assertTrue(0 <= delta.cell.z < N)

        olds = {(d.cell.x, d.cell.z): d.old_value for d in turn.decision.deltas}
        self.assertIn((peak.x, peak.z), olds)
        self.assertAlmostEqual(olds[(peak.x, peak.z)], old_here)

        last = runtime.world.scheduler.last
        self.assertIsNotNone(last)
        assert last is not None
        self.assertEqual(last.sequence, turn.tick)
        agent_deltas = [d for d in last.deltas if d.system_id == SYS.AGENT]
        self.assertTrue(agent_deltas)
        for d in agent_deltas:
            self.assertNotEqual(d.old_value, d.new_value)

        self.assertEqual(runtime.status.authorization, "granted")
        self.assertEqual(runtime.status.consequence, "observed")

        obs2 = make_synthetic_csi(9)
        turn2 = runtime.cycle(obs2)
        self.assertNotEqual(turn2.proposal.action_type, turn.proposal.action_type)
        self.assertIn(turn2.proposal.action_type, {"REMEMBER", "ATTEND"})
        remembered = runtime.world.self.peek("working.qwuack") or {}
        self.assertEqual(remembered.get("last_action"), turn2.proposal.action_type)
        self.assertGreater(turn2.tick, turn.tick)

    def test_status_file_for_existing_hud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qwuack_status.json"
            runtime = Runtime(status_path=path)
            runtime.wake()
            runtime.cycle(make_synthetic_csi(4))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "throne.qwuack.status")
            self.assertEqual(payload["identity"]["name"], "Qwuack")
            self.assertEqual(payload["state"], "awake")
            self.assertIn("last_action", payload)


if __name__ == "__main__":
    unittest.main()
