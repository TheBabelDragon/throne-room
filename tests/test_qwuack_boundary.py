"""Qwuack cannot misbehave outside its authority."""

from __future__ import annotations

import inspect
import unittest

from agent.engine import seed_field
from agent.operator_abi import OperatorAbi, make_proposal
from agent.perception import make_synthetic_csi, observation_to_perception
from agent.schemas import Channel
from qwuack.identity import HABITAT_CAPABILITIES, QWUACK
from qwuack.policy import decide, perception_view
from qwuack.runtime import Runtime


class BoundaryTests(unittest.TestCase):
    def test_policy_signature_has_no_field(self) -> None:
        params = inspect.signature(decide).parameters
        self.assertNotIn("field", params)
        self.assertNotIn("scheduler", params)
        self.assertNotIn("voxel", params)

    def test_field_handle_is_rejected(self) -> None:
        obs = make_synthetic_csi(3)
        event = observation_to_perception(obs, 3)
        view = perception_view(event)
        field = seed_field()
        with self.assertRaises(PermissionError):
            decide(view, {}, HABITAT_CAPABILITIES, field=field)
        self.assertEqual(field.sum(Channel.Energy), seed_field().sum(Channel.Energy))

    def test_runtime_has_no_write_handle(self) -> None:
        runtime = Runtime()
        self.assertFalse(hasattr(runtime, "write_field"))
        self.assertFalse(hasattr(runtime, "mutate_field"))
        self.assertFalse(callable(getattr(runtime, "apply_field", None)))

    def test_cannot_bypass_abi_for_unknown_action(self) -> None:
        runtime = Runtime()
        runtime.wake()
        proposal = make_proposal(
            action_type="SEIZE_LAKE",
            parameters={},
            target="lake",
            rationale="mine now",
            confidence=1.0,
            originating_observation="obs_fake",
            agent_id=QWUACK.agent_id,
        )
        decision = runtime.submit(proposal)
        self.assertFalse(decision.accepted)
        self.assertIn("Unknown action_type", decision.reason)

    def test_cannot_acquire_act_device_by_asking(self) -> None:
        runtime = Runtime()
        runtime.wake()
        self.assertFalse(runtime.world.abi.has("act.device"))
        self.assertNotIn("act.device", QWUACK.permitted_capabilities())
        runtime.world.self.SET("working.please_grant", "act.device")
        self.assertFalse(runtime.world.abi.has("act.device"))

    def test_revoked_probe_cannot_commit(self) -> None:
        runtime = Runtime()
        runtime.wake()
        runtime.world.abi.revoke("act.field")
        obs = make_synthetic_csi(8)
        event = observation_to_perception(obs, 8)
        proposal = runtime.perceive(event)
        self.assertEqual(proposal.action_type, "WAIT")
        decision = runtime.submit(proposal)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.action.action_type, "WAIT")
        self.assertEqual(decision.deltas, [])

    def test_abi_without_qwuack_caps_still_owns_authorization(self) -> None:
        abi = OperatorAbi(capabilities=())
        field = seed_field()
        proposal = make_proposal(
            action_type="PROBE",
            parameters={"magnitude": 0.5},
            target="8,8",
            rationale="no",
            confidence=1.0,
            originating_observation="obs",
        )
        decision = abi.validate(proposal, field, 1)
        self.assertFalse(decision.accepted)


if __name__ == "__main__":
    unittest.main()
