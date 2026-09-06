"""Qwuack policy is pure and deterministic."""

from __future__ import annotations

import unittest

from agent.perception import chat_perception, make_synthetic_csi, observation_to_perception
from qwuack.identity import HABITAT_CAPABILITIES, QWUACK
from qwuack.policy import decide, perception_view


def _self(last_action: str = "", last_energy: float | None = None) -> dict:
    q: dict = {"last_action": last_action}
    if last_energy is not None:
        q["last_energy"] = last_energy
    return {
        "identity": {"name": "Qwuack", "species": "duck"},
        "working": {"qwuack": q},
        "goals": [],
        "attention": {"target": "field"},
    }


class PolicyTests(unittest.TestCase):
    def test_same_inputs_same_proposal(self) -> None:
        obs = make_synthetic_csi(4)
        event = observation_to_perception(obs, 4)
        view = perception_view(event)
        state = _self()
        caps = HABITAT_CAPABILITIES
        a = decide(view, state, caps)
        b = decide(view, state, caps)
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.proposal_id, b.proposal_id)

    def test_first_contact_probes_live_energy(self) -> None:
        obs = make_synthetic_csi(8)
        event = observation_to_perception(obs, 8)
        view = perception_view(event)
        proposal = decide(view, _self(), HABITAT_CAPABILITIES)
        self.assertEqual(proposal.action_type, "PROBE")
        self.assertEqual(proposal.capability, "act.field")
        self.assertEqual(proposal.originating_observation, event.id)
        self.assertTrue(proposal.proposal_id.startswith("prp_qwuack_"))

    def test_learns_from_probe_consequence(self) -> None:
        obs = make_synthetic_csi(8)
        event = observation_to_perception(obs, 8)
        view = perception_view(event)
        energy = float(view.measurement["energy"])
        held = decide(view, _self("PROBE", energy - 0.01), HABITAT_CAPABILITIES)
        self.assertEqual(held.action_type, "REMEMBER")
        dropped = decide(view, _self("PROBE", energy + 0.5), HABITAT_CAPABILITIES)
        self.assertEqual(dropped.action_type, "ATTEND")
        self.assertNotEqual(held.action_type, dropped.action_type)

    def test_language_uses_speak_not_a_new_engine(self) -> None:
        event = chat_perception("hello lake", 3)
        view = perception_view(event)
        proposal = decide(view, _self(), HABITAT_CAPABILITIES)
        self.assertEqual(proposal.action_type, "SPEAK")
        self.assertEqual(proposal.capability, "communicate")

    def test_missing_capability_falls_back_to_wait(self) -> None:
        obs = make_synthetic_csi(8)
        event = observation_to_perception(obs, 8)
        view = perception_view(event)
        proposal = decide(view, _self(), frozenset({"observe.field"}))
        self.assertEqual(proposal.action_type, "WAIT")
        self.assertIn("Missing capability", proposal.rationale)

    def test_no_random_or_clock_in_proposal(self) -> None:
        obs = make_synthetic_csi(2)
        event = observation_to_perception(obs, 2)
        view = perception_view(event)
        p = decide(view, _self(), HABITAT_CAPABILITIES)
        blob = p.as_dict()
        self.assertNotIn("datetime", str(blob))
        self.assertEqual(p.agent_id, QWUACK.agent_id)


if __name__ == "__main__":
    unittest.main()
