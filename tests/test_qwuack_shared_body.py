"""Qwuack SHARED_BODY perception + continuity tests."""

from __future__ import annotations

import tempfile
import time
import unittest

from observer.shared_body.schema import (
    SCHEMA_VERSION, Measurement, Provenance, SharedBody, make_observation_id,
)
from observer.shared_body.registry import SharedBodyRegistry
from observer.shared_body.adapter import from_field_observation_packet
from agent.shared_body_perception import (
    perceive_shared_bodies, perception_status, reset_perception_memory,
)
from qwuack.policy import decide, perception_view
from agent.schemas import PerceptionEvent


def _body(body_id, obs_suffix, *, energy=0.5, synthetic=False, last_seen=None):
    observed_at = f"t-{obs_suffix}"
    oid = make_observation_id(body_id, observed_at, "test", "csi_energy")
    measurements, regions = [], []
    if energy is not None:
        measurements.append(Measurement(region="csi_energy", value=energy, confidence=0.9))
        regions.append("csi_energy")
    return SharedBody(
        body_id=body_id, schema_version=SCHEMA_VERSION, source_system="test",
        source_node_id=body_id, observation_id=oid, observed_at=observed_at,
        ingested_at=observed_at, regions=regions, measurements=measurements,
        provenance=Provenance(packet_type="FieldObservation", raw_node=body_id, synthetic=synthetic),
        body_type="wifi_csi", energy=energy,
        last_seen=last_seen if last_seen is not None else time.time(), status="ALIVE",
    )


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = SharedBodyRegistry(root=self.tmp.name, auto_persist=True)
        reset_perception_memory()
    def tearDown(self):
        self.tmp.cleanup()
    def test_first_observation(self):
        ok, reason = self.reg.register(_body("cyd_01", "1"))
        self.assertTrue(ok); self.assertEqual(reason, "ok")
    def test_same_body_new_observation(self):
        self.reg.register(_body("cyd_01", "1"))
        ok, _ = self.reg.register(_body("cyd_01", "2"))
        self.assertTrue(ok); self.assertEqual(self.reg.counts()["total"], 1)
    def test_duplicate_observation_id_rejected(self):
        b = _body("cyd_01", "1"); self.reg.register(b)
        ok, reason = self.reg.register(b)
        self.assertFalse(ok); self.assertEqual(reason, "duplicate_observation_id")
    def test_restart_identity(self):
        self.reg.register(_body("cyd_01", "1", energy=0.42))
        reg2 = SharedBodyRegistry(root=self.tmp.name, auto_persist=False)
        self.assertEqual(reg2.get("cyd_01").energy, 0.42)
    def test_missing_energy_stays_none(self):
        self.reg.register(_body("cyd_01", "1", energy=None))
        self.assertIsNone(self.reg.get("cyd_01").energy)
    def test_stale_status(self):
        self.reg.register(_body("cyd_01", "1", last_seen=time.time() - 20))
        self.assertEqual(self.reg.counts()["stale"], 1)


class AdapterTests(unittest.TestCase):
    def test_packet_to_body(self):
        pkt = {"type": "FieldObservation", "body_id": "esp32_cyd_01", "timestamp": "100",
               "synthetic": False,
               "regions": [{"name": "csi_energy", "observed": 0.55, "confidence": 0.9}]}
        body, reason = from_field_observation_packet(pkt)
        self.assertEqual(reason, "ok"); self.assertEqual(body.energy, 0.55)
    def test_no_fabricated_energy(self):
        pkt = {"body_id": "x", "timestamp": "1", "regions": [{"name": "rssi", "observed": 0.2}]}
        body, reason = from_field_observation_packet(pkt)
        self.assertIsNone(body.energy)


class PerceptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = SharedBodyRegistry(root=self.tmp.name, auto_persist=True)
        reset_perception_memory()
    def tearDown(self):
        self.tmp.cleanup()
    def test_perceive_events(self):
        self.reg.register(_body("cyd_01", "1"))
        events = perceive_shared_bodies(tick=1, registry=self.reg)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].modality, "shared_body")
        self.assertTrue(events[0].features["is_new"])
    def test_returning_body(self):
        self.reg.register(_body("cyd_01", "1"))
        perceive_shared_bodies(tick=1, registry=self.reg)
        self.reg.register(_body("cyd_01", "2", energy=0.7))
        events = perceive_shared_bodies(tick=2, registry=self.reg)
        self.assertTrue(events[0].features.get("measurement_changed"))
    def test_status_live(self):
        self.reg.register(_body("cyd_01", "1", synthetic=False))
        self.assertEqual(perception_status(self.reg).mode, "LIVE")
    def test_status_fixture(self):
        self.reg.register(_body("syn", "1", synthetic=True))
        self.assertEqual(perception_status(self.reg).mode, "FIXTURE")


class PolicyTests(unittest.TestCase):
    def _event(self, **features):
        base = {"body_id": "cyd_01", "observation_id": "obs_1", "status": "ALIVE",
                "synthetic": False, "is_new": True, "is_returning": False,
                "measurement_changed": True}
        base.update(features)
        return PerceptionEvent(id="pe1", source="cyd_01", timestamp="t", tick=1,
                               modality="shared_body", features=base, confidence=0.9)
    def test_stale_waits(self):
        prop = decide(perception_view(self._event(status="STALE", energy=0.9)),
                      {}, {"observe.field", "act.field"}, None)
        self.assertEqual(prop.action_type, "WAIT")
    def test_synthetic_no_probe(self):
        prop = decide(perception_view(self._event(synthetic=True, energy=0.9)),
                      {}, {"observe.field", "act.field"}, None)
        self.assertNotEqual(prop.action_type, "PROBE")
    def test_unchanged_returning_waits(self):
        prop = decide(perception_view(self._event(
            is_new=False, is_returning=True, measurement_changed=False, energy=0.5)),
            {}, {"observe.field", "act.field"}, None)
        self.assertEqual(prop.action_type, "WAIT")


if __name__ == "__main__":
    unittest.main()
