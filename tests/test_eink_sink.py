"""E-ink is a Duck Gate observer. It does not admit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from duck_gate.bus import GateBus
from duck_gate.eink.display import FileDisplay, MemoryDisplay
from duck_gate.eink.sink import EInkSink
from duck_gate.eink.snapshot import GateDisplaySnapshot
from duck_gate.eink.worker import EInkWorker
from duck_gate.events import DisplayAck, from_committed
from duck_gate.publish import event_after_commit


class EInkObserverTests(unittest.TestCase):
    def test_snapshot_is_a_projection(self) -> None:
        event = from_committed(
            sequence=1842,
            tick_hash="91a7c02e",
            accepted=True,
            action="PROBE",
            delta_count=3,
        )
        snap = GateDisplaySnapshot.from_event(event)
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.sequence, 1842)
        self.assertEqual(snap.status, "ADMITTED")
        self.assertEqual(snap.state_hash, "91a7c02e")
        self.assertEqual(snap.delta_count, 3)
        self.assertTrue(snap.committed)

    def test_invalid_event_is_ignored(self) -> None:
        sink = EInkSink(MemoryDisplay())
        self.assertFalse(sink.accept({"type": "noise"}))
        self.assertIsNone(sink.last_snapshot)
        self.assertEqual(sink.dropped, 1)

    def test_duplicate_sequence_does_not_refresh(self) -> None:
        display = MemoryDisplay()
        sink = EInkSink(display)
        event = from_committed(sequence=10, tick_hash="abcd1234", accepted=True, delta_count=1)
        self.assertTrue(sink.accept(event))
        self.assertTrue(display.refreshes == 1)
        self.assertFalse(sink.accept(event))
        self.assertEqual(display.refreshes, 1)

    def test_halted_keeps_last_committed(self) -> None:
        display = MemoryDisplay()
        sink = EInkSink(display)
        ok = from_committed(sequence=1841, tick_hash="91a7c02e", accepted=True, delta_count=2)
        bad = from_committed(
            sequence=1842,
            tick_hash="91a7c02e",
            accepted=False,
            action="PROBE",
            reason="INVALID DELTA",
            last_ok_sequence=1841,
        )
        sink.accept(ok)
        sink.accept(bad)
        self.assertEqual(sink.last_committed.sequence, 1841)
        self.assertEqual(sink.last_snapshot.status, "HALTED")
        self.assertIn("HALTED", display.frame)
        self.assertIn("INVALID DELTA", display.frame)
        self.assertIn("0001841", display.frame)

    def test_ack_is_observation_not_approval(self) -> None:
        sink = EInkSink(MemoryDisplay(), display_id="EINK-01")
        sink.accept(from_committed(sequence=1842, tick_hash="91a7c02e", accepted=True))
        ack = sink.acknowledge()
        self.assertIsInstance(ack, DisplayAck)
        assert ack is not None
        self.assertEqual(ack.type, "display_ack")
        self.assertEqual(ack.sequence, 1842)
        self.assertEqual(ack.state_hash, "91a7c02e")
        self.assertFalse(hasattr(ack, "accepted"))

    def test_worker_coalesces_ticks(self) -> None:
        display = MemoryDisplay()
        sink = EInkSink(display)
        worker = EInkWorker(sink)
        for seq in (1842, 1843, 1844, 1845):
            worker.submit(from_committed(sequence=seq, tick_hash=f"{seq:08x}", accepted=True))
        self.assertEqual(worker.drain(), 1)
        self.assertEqual(sink.last_sequence, 1845)
        self.assertEqual(worker.coalesced, 3)
        self.assertEqual(display.refreshes, 1)

    def test_bus_does_not_block_on_listener_error(self) -> None:
        bus = GateBus()

        def boom(_event) -> None:
            raise RuntimeError("panel jammed")

        seen: list[int] = []
        bus.subscribe(boom)
        bus.subscribe(lambda e: seen.append(e.sequence))
        bus.publish(from_committed(sequence=7, tick_hash="deadbeef", accepted=True))
        self.assertEqual(seen, [7])

    def test_file_display_writes_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eink_frame.txt"
            sink = EInkSink(FileDisplay(path))
            sink.accept(from_committed(sequence=1842, tick_hash="91a7c02e", accepted=True, delta_count=3))
            text = path.read_text(encoding="utf-8")
            self.assertIn("DUCK GATE", text)
            self.assertIn("ADMITTED", text)
            self.assertIn("0001842", text)

    def test_publish_after_commit_helper(self) -> None:
        class Decision:
            accepted = True
            reason = "committed PROBE"
            deltas = [1, 2, 3]
            proposal = type("P", (), {"action_type": "PROBE"})()

        event = event_after_commit(
            sequence=9,
            tick_hash="fff00011",
            decision=Decision(),
            observation_id="obs_9",
        )
        self.assertEqual(event.status, "ADMITTED")
        self.assertEqual(event.delta_count, 3)
        self.assertEqual(event.delta, "PROBE")


class EInkDoesNotAdmitTests(unittest.TestCase):
    def test_package_has_no_validate(self) -> None:
        import duck_gate.eink as pkg
        self.assertFalse(hasattr(pkg, "validate"))
        self.assertFalse(hasattr(pkg, "admit"))
        src = Path(pkg.__file__).read_text(encoding="utf-8")
        self.assertNotIn("OperatorAbi", src)


if __name__ == "__main__":
    unittest.main()
