"""Action pathway: contextual vs pre_attention ablation.

Does not touch Qwuack, FieldTick, or Operator ABI.
"""

from __future__ import annotations

import numpy as np
import pytest

from agent.language.transformer import ACTION_ORDER, DecoderTransformer, USER_ID, ARM_ID, BYTE_SIZE
from agent.language.tokenizer import SPECIALS


def _toy_ids(n: int = 12) -> list[int]:
    ids = [1, 2, 3, USER_ID, 10, 11, 12, 13, ARM_ID, 20, 21]
    return ids[:n] if n < len(ids) else ids


def test_numpy_contextual_logits_shape():
    model = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=3, action_path="contextual"
    )
    logits = model.action_logits(_toy_ids())
    assert logits.shape == (len(ACTION_ORDER),)
    assert np.isfinite(logits).all()


def test_numpy_pre_attention_logits_shape():
    model = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=3, action_path="pre_attention"
    )
    logits = model.action_logits(_toy_ids())
    assert logits.shape == (len(ACTION_ORDER),)


def test_numpy_paths_differ_for_same_weights_family():
    ids = _toy_ids()
    m_ctx = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=11, action_path="contextual"
    )
    m_pre = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=11, action_path="pre_attention"
    )
    a = m_ctx.action_logits(ids)
    b = m_pre.action_logits(ids)
    assert a.shape == b.shape
    assert not np.allclose(a, b, atol=1e-5)


def test_numpy_explicit_path_override():
    model = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=5, action_path="contextual"
    )
    ids = _toy_ids()
    a = model.action_logits(ids, path="contextual")
    b = model.action_logits(ids, path="pre_attention")
    assert not np.allclose(a, b, atol=1e-5)


def test_numpy_action_heads_confidence_bounds():
    model = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=2, action_path="contextual"
    )
    logits, conf, val = model.action_heads(_toy_ids())
    assert logits.shape == (len(ACTION_ORDER),)
    assert 0.0 <= conf <= 1.0
    assert np.isfinite(val)


def test_numpy_serialize_roundtrip_contextual():
    model = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=9, action_path="contextual"
    )
    ids = _toy_ids()
    before = model.action_logits(ids)
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "m.npz"
        model.save(path)
        loaded = DecoderTransformer.load(path)
    assert loaded.action_path == "contextual"
    after = loaded.action_logits(ids)
    assert np.allclose(before, after, atol=1e-5)


def test_numpy_predict_uses_argmax():
    model = DecoderTransformer(
        BYTE_SIZE + len(SPECIALS), d_model=32, n_head=4, n_layer=1, seed=1, action_path="contextual"
    )
    act, p = model.predict_action_p(_toy_ids())
    assert act in ACTION_ORDER
    assert 0.0 <= p <= 1.0


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_torch_contextual_uses_hidden_not_embed():
    import torch
    from agent.language.torch_model import ArmGPT
    from agent.language.tokenizer import ArmTokenizer

    tok = ArmTokenizer()
    model = ArmGPT(tok.vocab_size, d_model=32, n_layer=1, n_head=4, action_path="contextual")
    t = torch.tensor([_toy_ids()], dtype=torch.long)
    pooled_ctx = model.action_representation(t, path="contextual")
    pooled_pre = model.action_representation(t, path="pre_attention")
    assert pooled_ctx.shape == (1, model.d_model)
    assert pooled_pre.shape == (1, model.d_model)
    assert not torch.allclose(pooled_ctx, pooled_pre, atol=1e-5)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_torch_action_heads_and_default_path():
    import torch
    from agent.language.torch_model import ArmGPT
    from agent.language.tokenizer import ArmTokenizer

    tok = ArmTokenizer()
    model = ArmGPT(tok.vocab_size, d_model=32, n_layer=1, n_head=4, action_path="contextual")
    assert model.action_path == "contextual"
    t = torch.tensor([_toy_ids()], dtype=torch.long)
    logits, conf, val = model.action_heads(t)
    assert logits.shape == (1, len(ACTION_ORDER))
    assert conf.shape == (1,)
    assert ((conf >= 0) & (conf <= 1)).all()
    act, p = model.predict_action_p(_toy_ids())
    assert act in ACTION_ORDER


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_torch_pre_attention_ablation_still_works():
    from agent.language.torch_model import ArmGPT
    from agent.language.tokenizer import ArmTokenizer

    tok = ArmTokenizer()
    model = ArmGPT(tok.vocab_size, d_model=32, n_layer=1, n_head=4, action_path="pre_attention")
    logits = model.action_logits(_toy_ids(), path="pre_attention")
    assert logits.shape == (len(ACTION_ORDER),)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_torch_contextual_action_loss_reaches_blocks():
    import torch
    import torch.nn.functional as F
    from agent.language.torch_model import ArmGPT
    from agent.language.tokenizer import ArmTokenizer

    tok = ArmTokenizer()
    model = ArmGPT(tok.vocab_size, d_model=32, n_layer=1, n_head=4, action_path="contextual")
    t = torch.tensor([_toy_ids()], dtype=torch.long)
    logits, _, _ = model.action_heads(t)
    loss = F.cross_entropy(logits, torch.tensor([0]))
    loss.backward()
    grads = [p.grad for p in model.blocks[0].attn.parameters() if p.grad is not None]
    assert any(g is not None and float(g.abs().sum()) > 0 for g in grads)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_torch_pre_attention_action_loss_skips_blocks():
    import torch
    import torch.nn.functional as F
    from agent.language.torch_model import ArmGPT
    from agent.language.tokenizer import ArmTokenizer

    tok = ArmTokenizer()
    model = ArmGPT(tok.vocab_size, d_model=32, n_layer=1, n_head=4, action_path="pre_attention")
    t = torch.tensor([_toy_ids()], dtype=torch.long)
    logits, _, _ = model.action_heads(t, path="pre_attention")
    loss = F.cross_entropy(logits, torch.tensor([0]))
    loss.backward()
    block_grads = [p.grad for p in model.blocks[0].parameters()]
    assert all(g is None or float(g.abs().sum()) == 0.0 for g in block_grads)
