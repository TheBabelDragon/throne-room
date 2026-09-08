"""Duck Gate v0.1 — admission is deterministic and explicit."""

from __future__ import annotations

import unittest

from agent.engine import seed_field
from agent.operator_abi import OperatorAbi, make_proposal
from qwuack.gate import DEFAULT_GATE, GATE_POLICY, GateConfig


class DuckGateTests(unittest.TestCase):
    def test_same_inputs_same_admission(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="PROBE",
            parameters={"x": 8, "z": 8, "magnitude": 0.4},
            target="8,8",
            rationale="gate replay",
            confidence=0.9,
            originating_observation="obs_1",
            observation_sequence=1,
            agent_id="advisor:qwuack-0",
        )
        a = abi.validate(proposal, field, 1)
        b = abi.validate(proposal, field, 1)
        self.assertEqual(a.status, b.status)
        self.assertEqual(a.reason_code, b.reason_code)
        self.assertEqual(a.accepted, b.accepted)
        self.assertEqual(len(a.deltas), len(b.deltas))

    def test_stale_observation_rejected(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="PROBE",
            parameters={"x": 8, "z": 8, "magnitude": 0.4},
            target="8,8",
            rationale="late",
            confidence=0.9,
            originating_observation="obs_old",
            observation_sequence=1,
            agent_id="advisor:qwuack-0",
        )
        decision = abi.validate(proposal, field, 9)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "STALE")
        self.assertEqual(decision.reason_code, "stale_observation")
        self.assertEqual(decision.deltas, [])

    def test_bounds_reject_not_clamp(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="PROBE",
            parameters={"x": 8, "z": 8, "magnitude": 4.0},
            target="8,8",
            rationale="too much",
            confidence=1.0,
            originating_observation="obs_b",
            observation_sequence=1,
        )
        decision = abi.validate(proposal, field, 1)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "BOUNDS")
        self.assertEqual(decision.deltas, [])

    def test_out_of_field_target_rejected(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="PROBE",
            parameters={"x": 99, "z": 99, "magnitude": 0.4},
            target="99,99",
            rationale="off grid",
            confidence=0.5,
            originating_observation="obs_c",
            observation_sequence=1,
        )
        decision = abi.validate(proposal, field, 1)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "BOUNDS")

    def test_budget_exceeded(self) -> None:
        field = seed_field()
        tight = GateConfig(max_accepts=1, max_delta_per_tick=2.0)
        abi = OperatorAbi(gate=tight)
        first = make_proposal(
            action_type="PROBE",
            parameters={"x": 8, "z": 8, "magnitude": 0.4},
            target="8,8",
            rationale="one",
            confidence=0.5,
            originating_observation="obs_d1",
            observation_sequence=1,
            agent_id="advisor:greedy",
        )
        second = make_proposal(
            action_type="PROBE",
            parameters={"x": 8, "z": 8, "magnitude": 0.4},
            target="8,8",
            rationale="two",
            confidence=0.5,
            originating_observation="obs_d2",
            observation_sequence=2,
            agent_id="advisor:greedy",
        )
        a = abi.validate(first, field, 1)
        self.assertTrue(a.accepted)
        b = abi.validate(second, field, 2)
        self.assertFalse(b.accepted)
        self.assertEqual(b.status, "BUDGET_EXCEEDED")

    def test_missing_sequence_is_legacy_compatible(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="WAIT",
            parameters={},
            target="field",
            rationale="legacy arm",
            confidence=0.4,
            originating_observation="obs_legacy",
        )
        decision = abi.validate(proposal, field, 40)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.status, "ADMITTED")

    def test_admission_has_provenance(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="QUERY_FIELD",
            parameters={},
            target="field",
            rationale="look",
            confidence=0.6,
            originating_observation="obs_p",
            observation_sequence=3,
            agent_id="qwuack-0",
        )
        decision = abi.validate(proposal, field, 3)
        self.assertTrue(decision.accepted)
        self.assertIsNotNone(decision.admission)
        assert decision.admission is not None
        self.assertEqual(decision.admission.provenance.gate_policy, GATE_POLICY)
        self.assertEqual(decision.admission.provenance.observation_id, "obs_p")
        self.assertEqual(DEFAULT_GATE.version, "0.1")


if __name__ == "__main__":
    unittest.main()
