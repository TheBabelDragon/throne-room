#!/usr/bin/env python3
"""Arm / Torch language-arm invariants (split from agent.test_invariants for CI payload limits)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.language.arm import LanguageArm
from agent.language.tokenizer import ArmTokenizer, SPECIALS
from agent.language.transformer import DecoderTransformer
from agent.loop import World
from agent.operator_abi import make_proposal
from agent.schemas import Channel


class ArmTests(unittest.TestCase):
    def test_tokenizer_owns_specials_and_roundtrip(self) -> None:
        tok = ArmTokenizer()
        for name in ("<OBSERVE>", "<ATTEND>", "<QUERY>", "<REMEMBER>", "<PROPOSE>", "<SPEAK>"):
            self.assertIn(name, SPECIALS)
            self.assertGreaterEqual(tok.special_id(name), 256)
        text = "<BOS>hello <SPEAK>field<EOS>"
        ids = tok.encode(text)
        self.assertEqual(tok.decode(ids), text)
        self.assertEqual(tok.version, "arm-tok-v1")

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

    def test_encode_target_is_structured(self) -> None:
        tok = ArmTokenizer()
        p = make_proposal(
            action_type="PROBE",
            parameters={"x": 7, "z": 7, "magnitude": 0.5},
            target="7,7",
            rationale="t",
            confidence=0.9,
            originating_observation="o",
        )
        ids = tok.encode_target(p)
        self.assertEqual(tok.action_from_ids(ids), "PROBE")
        self.assertEqual(ids[0], tok.special_id("<PROPOSE>"))

    def test_user_span_ignores_field_prefix(self) -> None:
        tok = ArmTokenizer()
        a = tok.encode("<BOS><FIELD> t=1 E=9.90 <USER> Probe the energy peak <ARM>")
        b = tok.encode("<BOS><FIELD> t=99 E=0.01 <USER> Probe the energy peak <ARM>")
        self.assertEqual(tok.decode(tok.user_span(a)), tok.decode(tok.user_span(b)))
        self.assertIn("Probe the energy peak", tok.decode(tok.user_span(a)))
        self.assertNotIn("E=9.90", tok.decode(tok.user_span(a)))

    def test_dataset_covers_all_actions(self) -> None:
        from agent.language.dataset import SCRIPTS, synthesize
        from agent.language.transformer import ACTION_ORDER
        labeled = {ex.action for ex in synthesize(len(SCRIPTS), tokenizer=ArmTokenizer())}
        self.assertTrue(set(ACTION_ORDER).issubset(labeled), labeled)

    def test_train_runtime_improves_action_head(self) -> None:
        from agent.language.train import run
        with tempfile.TemporaryDirectory() as td:
            ckpt = Path(td) / "arm.npz"
            summary = run(examples=48, steps=40, lr=1.5, ckpt=ckpt, seed=7)
            self.assertTrue(ckpt.exists())
            self.assertGreaterEqual(summary["hold_acc"], 0.5)
            self.assertGreaterEqual(summary["reload_acc"], 0.5)
            from agent.language.transformer import MODEL_VERSION
            self.assertEqual(summary["model"], MODEL_VERSION)

    def test_compose_is_the_operator_voice(self) -> None:
        world = World()
        world.step()
        turn = world.handle_human("What do you perceive?")
        assert turn is not None
        self.assertEqual(turn.proposal.action_type, "SPEAK")
        text = turn.utterance or ""
        self.assertTrue(len(text) > 0)

    def test_learn_one_updates_weights(self) -> None:
        import numpy as np
        from agent.language.transformer import DecoderTransformer, learn_one
        tok = ArmTokenizer()
        model = DecoderTransformer(tok.vocab_size, seed=1)
        ids = tok.encode("<USER> Probe the energy peak <ARM>")
        w0 = model.w_act.copy()
        rec = learn_one(model, ids, 1, lr=1.5)
        self.assertEqual(rec["gold"], "PROBE")
        self.assertFalse(np.allclose(w0, model.w_act))


def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_has_torch(), "torch not installed")
class TorchArmTests(unittest.TestCase):
    def test_forward_shapes_and_determinism(self) -> None:
        from agent.language.torch_model import ArmGPT
        tok = ArmTokenizer()
        a = ArmGPT(tok.vocab_size)
        ids = tok.encode("<BOS><USER> Probe the energy peak <ARM>")
        import torch
        t = torch.tensor([ids], dtype=torch.long)
        logits, hidden = a.forward(t)
        self.assertEqual(tuple(logits.shape), (1, len(ids), tok.vocab_size))
        self.assertEqual(tuple(hidden.shape), (1, len(ids), a.d_model))
        pred, p = a.predict_action_p(ids)
        self.assertIn(pred, ("SPEAK", "PROBE", "REMEMBER", "ATTEND", "SET_GOAL", "QUERY_FIELD", "WAIT"))
        self.assertGreater(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_torch_train_improves_action_head(self) -> None:
        from agent.language.torch_train import run
        with tempfile.TemporaryDirectory() as td:
            ckpt = Path(td) / "arm_gpt.pt"
            summary = run(examples=48, steps=8, lr=3e-3, ckpt=ckpt, seed=7, batch=8)
            self.assertTrue(ckpt.exists())
            self.assertGreaterEqual(summary["hold_acc"], 0.5)
            self.assertGreaterEqual(summary["reload_acc"], 0.5)
            from agent.language.torch_model import TORCH_VERSION
            self.assertEqual(summary["model"], TORCH_VERSION)

    def test_arm_loads_torch_checkpoint(self) -> None:
        from agent.language.arm import LanguageArm
        from agent.language.torch_model import ArmGPT
        tok = ArmTokenizer()
        gpt = ArmGPT(tok.vocab_size)
        world = World()
        world.arm = LanguageArm(mode="model", tokenizer=tok, model=gpt, min_p=0.0)
        self.assertEqual(world.arm.backend, "torch")
        world.step()
        turn = world.handle_human("What do you perceive?")
        self.assertIsNotNone(turn)
        self.assertEqual(world.arm.last.source, "model")  # type: ignore[union-attr]


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
