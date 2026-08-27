#!/usr/bin/env python3
"""FieldTick replay + ABI + bridge + live-feed invariants. No hardware required.

    python -m agent.test_invariants
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.bridge import aurora_intent_to_proposal, packet_to_observation, proposal_to_aurora_action
from agent.engine import FieldScheduler, seed_field
from agent.feeds import JsonlCursor
from agent.hashutil import canonical, fnv1a
from agent.language.arm import LanguageArm
from agent.language.tokenizer import ArmTokenizer, SPECIALS
from agent.language.transformer import DecoderTransformer
from agent.loop import World
from agent.operator_abi import OperatorAbi, make_proposal
from agent.perception import make_synthetic_csi
from agent.schemas import Channel


class ReplayTests(unittest.TestCase):
    def test_replay_matches_live_field(self) -> None:
        sched = FieldScheduler(seed_field())
        for i in range(12):
            sched.bind_observation(make_synthetic_csi(i + 1))
            sched.step(0.125)
        live = list(sched.field.data)
        replayed = sched.replay_to(sched.sequence)
        self.assertEqual(live, replayed.data)

    def test_identical_inputs_identical_hash(self) -> None:
        hashes = []
        for _ in range(2):
            sched = FieldScheduler(seed_field())
            for i in range(8):
                sched.bind_observation(make_synthetic_csi(i + 1))
                commit = sched.step(0.125)
            hashes.append(commit.hash)
        self.assertEqual(hashes[0], hashes[1])

    def test_tick_hash_is_canonical(self) -> None:
        sched = FieldScheduler(seed_field())
        commit = sched.step(0.125)
        self.assertEqual(commit.hash, fnv1a(canonical(commit.tick.as_dict())))


class AbiTests(unittest.TestCase):
    def test_reject_missing_capability(self) -> None:
        field = seed_field()
        abi = OperatorAbi()
        abi.revoke("act.field")
        proposal = make_proposal(
            action_type="PROBE",
            parameters={"x": 8, "z": 8, "magnitude": 0.5},
            target="8,8",
            rationale="test",
            confidence=0.9,
            originating_observation="obs_test",
        )
        decision = abi.validate(proposal, field, 1)
        self.assertFalse(decision.accepted)
        self.assertIn("Missing capability", decision.reason)

    def test_speak_writes_information_not_energy(self) -> None:
        field = seed_field()
        e0 = field.sum(Channel.Energy)
        abi = OperatorAbi()
        proposal = make_proposal(
            action_type="SPEAK",
            parameters={"text": "hello field"},
            target="chat",
            rationale="test",
            confidence=0.8,
            originating_observation="obs_test",
        )
        decision = abi.validate(proposal, field, 1)
        self.assertTrue(decision.accepted)
        self.assertTrue(decision.deltas)
        self.assertTrue(all(d.channel == Channel.Information for d in decision.deltas))
        field.apply(decision.deltas)
        self.assertEqual(e0, field.sum(Channel.Energy))

    def test_act_device_not_default(self) -> None:
        abi = OperatorAbi()
        self.assertFalse(abi.has("act.device"))


class BridgeTests(unittest.TestCase):
    def test_wifi_csi_packet(self) -> None:
        pkt = {"type": "wifi_csi", "node": "cyd-a", "rssi": -52, "csi": [0.2] * 32}
        obs = packet_to_observation(pkt)
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertEqual(obs.body_id, "cyd-a")
        self.assertTrue(any(r.name == "csi_energy" for r in obs.regions))

    def test_metafield_packet(self) -> None:
        pkt = {
            "schema_version": 1,
            "body_id": "cyd-b",
            "body_type": "wifi_csi",
            "field_regions": [
                {"region": "csi_energy", "observed": 0.44, "confidence": 0.9},
            ],
            "timestamp": "t",
            "health": "ok",
            "modality": {"wifi_csi": {"rssi_dbm": -60, "csi": [0.1, 0.2]}},
        }
        obs = packet_to_observation(pkt)
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertEqual(obs.rssi_dbm, -60.0)

    def test_aurora_probe_maps_to_probe(self) -> None:
        intent = {
            "action": "probe",
            "priority": 0.8,
            "reason": "field pressure",
            "body_id": "cyd-a",
            "params": {"pressure": 0.8},
        }
        proposal = aurora_intent_to_proposal(intent, observation_id="obs_x")
        self.assertEqual(proposal.action_type, "PROBE")
        self.assertEqual(proposal.agent_id, "aurora-0")
        back = proposal_to_aurora_action(proposal)
        self.assertEqual(back["type"], "probe")
        self.assertEqual(back["proposal_id"], proposal.proposal_id)


class LoopTests(unittest.TestCase):
    def test_chat_probe_commits_and_ticks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            world = World(memory_path=Path(td) / "mem.jsonl")
            for _ in range(3):
                world.step()
            seq0 = world.scheduler.sequence
            e0 = world.scheduler.field.sum(Channel.Energy)
            turn = world.handle_human("Probe the energy peak")
            self.assertIsNotNone(turn)
            assert turn is not None
            self.assertEqual(turn.proposal.action_type, "PROBE")
            self.assertTrue(turn.decision.accepted)
            self.assertEqual(world.scheduler.sequence, seq0 + 1)
            self.assertGreater(world.scheduler.field.sum(Channel.Energy), e0)

    def test_remember_persists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "mem.jsonl"
            world = World(memory_path=path)
            world.step()
            world.handle_human("Remember this field state")
            self.assertTrue(any("Tick" in e.text or "energy" in e.text for e in world.memory.entries))
            self.assertTrue(path.exists())


class FeedTests(unittest.TestCase):
    def test_invalid_packet_does_not_tick(self) -> None:
        world = World()
        seq = world.scheduler.sequence
        self.assertFalse(world.ingest_packet({"nope": True}))
        self.assertEqual(world.scheduler.sequence, seq)

    def test_live_csi_then_chat_does_not_inject_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            csi = Path(td) / "csi.jsonl"
            pkt = {
                "type": "wifi_csi",
                "node": "cyd-a",
                "rssi": -40,
                "csi": [0.8] * 32,
            }
            csi.write_text(json.dumps(pkt) + "\n")
            world = World(memory_path=Path(td) / "mem.jsonl")
            counts = world.attach_feeds(csi=csi, warmup=8)
            self.assertEqual(counts["csi"], 1)
            self.assertTrue(world.live)
            self.assertEqual(world.last_obs.body_id, "cyd-a")
            self.assertFalse(world.last_obs.synthetic)
            seq = world.scheduler.sequence
            world.handle_human("What do you perceive?")
            self.assertEqual(world.scheduler.sequence, seq + 1)
            self.assertFalse(world.last_obs.synthetic)
            self.assertEqual(world.last_obs.body_id, "cyd-a")

    def test_cursor_does_not_reingest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            csi = Path(td) / "csi.jsonl"
            csi.write_text(json.dumps({"type": "wifi_csi", "node": "a", "rssi": -50, "csi": [0.3] * 32}) + "\n")
            world = World()
            world.attach_feeds(csi=csi, warmup=8)
            n1 = world.packets_ingested
            self.assertEqual(world.drain_feeds()["csi"], 0)
            self.assertEqual(world.packets_ingested, n1)
            with csi.open("a") as fh:
                fh.write(json.dumps({"type": "wifi_csi", "node": "b", "rssi": -48, "csi": [0.4] * 32}) + "\n")
            got = world.drain_feeds()
            self.assertEqual(got["csi"], 1)
            self.assertEqual(world.last_obs.body_id, "b")

    def test_poll_caps_and_keeps_rest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "csi.jsonl"
            lines = [
                json.dumps({"type": "wifi_csi", "node": f"n{i}", "rssi": -50, "csi": [0.2] * 8})
                for i in range(40)
            ]
            path.write_text("\n".join(lines) + "\n")
            cur = JsonlCursor(path, keep=8)
            cur.catch_up_keep(8)
            # parked at EOF — append more
            extra = [
                json.dumps({"type": "wifi_csi", "node": f"x{i}", "rssi": -40, "csi": [0.4] * 8})
                for i in range(20)
            ]
            with path.open("a") as fh:
                fh.write("\n".join(extra) + "\n")
            first = cur.poll(max_records=5)
            self.assertEqual(len(first), 5)
            self.assertEqual(first[0]["node"], "x0")
            second = cur.poll(max_records=5)
            self.assertEqual(len(second), 5)
            self.assertEqual(second[0]["node"], "x5")

    def test_incomplete_line_waits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "csi.jsonl"
            path.write_text("")
            cur = JsonlCursor(path, keep=4)
            cur.catch_up_keep(4)
            with path.open("ab") as fh:
                fh.write(b'{"type":"wifi_csi","node":"partial"')
            self.assertEqual(cur.poll(), [])
            with path.open("ab") as fh:
                fh.write(b',"rssi":-50,"csi":[0.1,0.2]}\n')
            got = cur.poll()
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["node"], "partial")

    def test_file_appears_does_not_replay_history(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "csi.jsonl"
            cur = JsonlCursor(path, keep=2)
            self.assertEqual(cur.catch_up_keep(2), [])
            hist = [
                json.dumps({"type": "wifi_csi", "node": "old", "rssi": -70, "csi": [0.1] * 8}),
                json.dumps({"type": "wifi_csi", "node": "keep-a", "rssi": -40, "csi": [0.5] * 8}),
                json.dumps({"type": "wifi_csi", "node": "keep-b", "rssi": -41, "csi": [0.5] * 8}),
            ]
            path.write_text("\n".join(hist) + "\n")
            got = cur.poll()
            self.assertEqual(len(got), 2)
            self.assertEqual(got[0]["node"], "keep-a")
            self.assertEqual(cur.poll(), [])

    def test_handle_human_caps_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            csi = Path(td) / "csi.jsonl"
            lines = [
                json.dumps({"type": "wifi_csi", "node": f"b{i}", "rssi": -50, "csi": [0.2] * 8})
                for i in range(200)
            ]
            csi.write_text("\n".join(lines) + "\n")
            world = World(memory_path=Path(td) / "mem.jsonl")
            world.attach_feeds(csi=csi, warmup=4)
            with csi.open("a") as fh:
                for i in range(80):
                    fh.write(json.dumps({
                        "type": "wifi_csi", "node": f"new{i}", "rssi": -45, "csi": [0.3] * 8,
                    }) + "\n")
            t0 = time.monotonic()
            turn = world.handle_human("What do you perceive?")
            elapsed = time.monotonic() - t0
            self.assertIsNotNone(turn)
            self.assertLess(elapsed, 3.0)
            self.assertLessEqual(world.packets_ingested, 4 + 24 + 2)

    def test_aurora_probe_commits_locally_not_device(self) -> None:
        world = World()
        world.live = True
        e0 = world.scheduler.field.sum(Channel.Energy)
        ok = world.observe_aurora({
            "action": "probe",
            "priority": 0.85,
            "reason": "field pressure",
            "body_id": "cyd-a",
            "params": {"pressure": 0.85},
        })
        self.assertTrue(ok)
        self.assertGreater(world.scheduler.field.sum(Channel.Energy), e0)
        self.assertFalse(world.abi.has("act.device"))
        self.assertEqual(world.self.peek("working.last_aurora")["action"], "PROBE")

    def test_tick_journal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ticks = Path(td) / "ticks.jsonl"
            world = World()
            world.ticks_path = ticks
            world.step()
            self.assertTrue(ticks.exists())
            rec = json.loads(ticks.read_text().splitlines()[0])
            self.assertEqual(rec["schema"], "metafield.tick")
            self.assertEqual(rec["sequence"], 1)
            self.assertEqual(rec["hash"], world.last_hash)

    def test_int_ticks_path_does_not_crash(self) -> None:
        world = World()
        world.ticks_path = 4  # type: ignore[assignment]
        world.step()
        self.assertEqual(world.scheduler.sequence, 1)

    def test_attach_feeds_rejects_int_journal(self) -> None:
        world = World()
        with self.assertRaises(TypeError):
            world.attach_feeds(ticks=4)  # type: ignore[arg-type]

    def test_cli_live_follow_ticks_flag_is_not_a_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            csi = Path(td) / "csi.jsonl"
            aurora = Path(td) / "aurora.jsonl"
            journal = Path(td) / "ticks.jsonl"
            pkt = {"type": "wifi_csi", "node": "cyd-a", "rssi": -51, "csi": [0.3] * 32}
            csi.write_text(json.dumps(pkt) + "\n")
            aurora.write_text("")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT)
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "agent.chat",
                    "--live", "--follow", "--interval", "0.05",
                    "--csi", str(csi), "--aurora", str(aurora),
                    "--journal", str(journal), "--ticks", "4", "--warmup", "8",
                ],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                time.sleep(0.35)
                with csi.open("a") as fh:
                    fh.write(json.dumps({
                        "type": "wifi_csi", "node": "cyd-b", "rssi": -47, "csi": [0.5] * 32,
                    }) + "\n")
                    fh.flush()
                time.sleep(0.45)
                proc.send_signal(signal.SIGINT)
                out, _ = proc.communicate(timeout=8)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=3)
                    out = proc.stdout.read() if proc.stdout else ""
            self.assertNotIn("AttributeError", out)
            self.assertIn("follow mode", out)
            self.assertTrue(journal.exists())
            recs = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
            self.assertGreaterEqual(len(recs), 1)
            self.assertEqual(recs[0]["schema"], "metafield.tick")


class ArmTests(unittest.TestCase):
    def test_tokenizer_owns_specials_and_roundtrip(self) -> None:
        tok = ArmTokenizer()
        for name in ("<OBSERVE>", "<ATTEND>", "<QUERY>", "<REMEMBER>", "<PROPOSE>", "<SPEAK>"):
            self.assertIn(name, SPECIALS)
            self.assertGreaterEqual(tok.special_id(name), 256)
        text = "<BOS>hello <SPEAK>field<EOS>"
        ids = tok.encode(text)
        self.assertEqual(tok.decode(ids), text)
        self.assertEqual(tok.version, "arm-tok-v0")

    def test_transformer_is_local_and_deterministic(self) -> None:
        tok = ArmTokenizer()
        a = DecoderTransformer(tok.vocab_size, seed=7)
        b = DecoderTransformer(tok.vocab_size, seed=7)
        ids = tok.encode("<BOS><USER> hi <ARM>")
        ga = a.generate(ids, max_new=8)
        gb = b.generate(ids, max_new=8)
        self.assertEqual(ga, gb)
        self.assertEqual(len(ga), 8)

    def test_arm_emits_proposal_through_abi(self) -> None:
        world = World()
        world.arm.mode = "teacher"
        for _ in range(3):
            world.step()
        turn = world.handle_human("What do you perceive?")
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn.proposal.action_type, "SPEAK")
        self.assertTrue(turn.decision.accepted)
        self.assertEqual(world.arm.last.source, "teacher")
        self.assertGreater(len(world.arm.last.tokens), 0)
        self.assertIsNotNone(world.last_language_context)
        self.assertNotIn("act.device", world.last_language_context.capabilities)

    def test_arm_teacher_probe_still_commits(self) -> None:
        world = World()
        world.step()
        e0 = world.scheduler.field.sum(Channel.Energy)
        turn = world.handle_human("Probe the energy peak")
        assert turn is not None
        self.assertEqual(turn.proposal.action_type, "PROBE")
        self.assertGreater(world.scheduler.field.sum(Channel.Energy), e0)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
