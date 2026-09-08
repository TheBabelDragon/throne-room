"""QwuackState is a tenant snapshot, not a write handle."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.perception import make_synthetic_csi
from qwuack.runtime import Runtime
from qwuack.state import STATE_SCHEMA, QwuackState


class QwuackStateTests(unittest.TestCase):
    def test_cycle_writes_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = Path(tmp) / "qwuack_status.json"
            state = Path(tmp) / "qwuack_state.json"
            runtime = Runtime(status_path=status, state_path=state)
            runtime.wake()
            turn = runtime.cycle(make_synthetic_csi(4))
            self.assertTrue(state.exists())
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], STATE_SCHEMA)
            self.assertTrue(payload["awake"])
            self.assertEqual(payload["last_action"], turn.proposal.action_type)
            self.assertIn(payload["admission_status"], {"ADMITTED", "REJECTED", "UNAUTHORIZED", "WAIT"})
            self.assertEqual(payload["identity"]["name"], "Qwuack")
            self.assertIn("budget", payload)
            status_payload = json.loads(status.read_text(encoding="utf-8"))
            self.assertIn("qwuack_state", status_payload)
            self.assertEqual(status_payload["qwuack_state"]["proposal_id"], turn.proposal.proposal_id)

    def test_state_is_not_authority(self) -> None:
        snap = QwuackState(awake=True, last_action="PROBE", admission_status="ADMITTED")
        self.assertFalse(hasattr(snap, "write"))
        self.assertFalse(hasattr(snap, "admit"))
        self.assertIn("QWUACKSTATE", snap.render())


if __name__ == "__main__":
    unittest.main()
