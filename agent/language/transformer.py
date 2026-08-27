"""Tiny decoder transformer. Local, numpy, no network.

v0 is conventional on purpose: embed → pos → blocks → LM head → P(next).
Weights start from a seeded genesis. Training is a later decision that
must not change this shape.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL_VERSION = "arm-dec-v0"


def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    z = x - np.max(x, axis=axis, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=axis, keepdims=True)


def _layernorm(x: np.ndarray, gain: np.ndarray, bias: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    mu = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return gain * (x - mu) / np.sqrt(var + eps) + bias


class DecoderTransformer:
    def __init__(
        self,
        vocab_size: int,
        *,
        d_model: int = 32,
        n_layer: int = 2,
        n_head: int = 4,
        max_seq: int = 192,
        seed: int = 7,
    ) -> None:
        if d_model % n_head != 0:
            raise ValueError("d_model must divide n_head")
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.n_layer = n_layer
        self.n_head = n_head
        self.d_head = d_model // n_head
        self.max_seq = max_seq
        self.seed = seed
        self.version = MODEL_VERSION
        rng = np.random.RandomState(seed)
        scale = 0.02
        self.tok = rng.randn(vocab_size, d_model).astype(np.float32) * scale
        self.pos = rng.randn(max_seq, d_model).astype(np.float32) * scale
        self.layers = []
        for _ in range(n_layer):
            self.layers.append({
                "wq": rng.randn(d_model, d_model).astype(np.float32) * scale,
                "wk": rng.randn(d_model, d_model).astype(np.float32) * scale,
                "wv": rng.randn(d_model, d_model).astype(np.float32) * scale,
                "wo": rng.randn(d_model, d_model).astype(np.float32) * scale,
                "w1": rng.randn(d_model, 4 * d_model).astype(np.float32) * scale,
                "w2": rng.randn(4 * d_model, d_model).astype(np.float32) * scale,
                "ln1g": np.ones(d_model, dtype=np.float32),
                "ln1b": np.zeros(d_model, dtype=np.float32),
                "ln2g": np.ones(d_model, dtype=np.float32),
                "ln2b": np.zeros(d_model, dtype=np.float32),
            })
        self.fng = np.ones(d_model, dtype=np.float32)
        self.fnb = np.zeros(d_model, dtype=np.float32)
        self.head = rng.randn(d_model, vocab_size).astype(np.float32) * scale

    def forward(self, ids: list[int]) -> np.ndarray:
        if not ids:
            ids = [0]
        ids = ids[-self.max_seq :]
        t = len(ids)
        x = self.tok[np.array(ids, dtype=np.int64)] + self.pos[:t]
        causal = np.triu(np.full((t, t), -1e9, dtype=np.float32), k=1)
        for layer in self.layers:
            h = _layernorm(x, layer["ln1g"], layer["ln1b"])
            q = h @ layer["wq"]
            k = h @ layer["wk"]
            v = h @ layer["wv"]
            q = q.reshape(t, self.n_head, self.d_head).transpose(1, 0, 2)
            k = k.reshape(t, self.n_head, self.d_head).transpose(1, 0, 2)
            v = v.reshape(t, self.n_head, self.d_head).transpose(1, 0, 2)
            att = (q @ k.transpose(0, 2, 1)) / np.sqrt(self.d_head)
            att = _softmax(att + causal, axis=-1)
            y = (att @ v).transpose(1, 0, 2).reshape(t, self.d_model)
            x = x + y @ layer["wo"]
            h = _layernorm(x, layer["ln2g"], layer["ln2b"])
            x = x + (np.maximum(h @ layer["w1"], 0.0) @ layer["w2"])
        x = _layernorm(x, self.fng, self.fnb)
        return x @ self.head

    def generate(self, ids: list[int], *, max_new: int = 48, eos: int | None = None) -> list[int]:
        out = list(ids)
        new: list[int] = []
        for _ in range(max_new):
            logits = self.forward(out)
            nxt = int(np.argmax(logits[-1]))
            new.append(nxt)
            out.append(nxt)
            if eos is not None and nxt == eos:
                break
        return new

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tok": self.tok, "pos": self.pos, "head": self.head,
            "fng": self.fng, "fnb": self.fnb,
        }
        for i, layer in enumerate(self.layers):
            for k, v in layer.items():
                payload[f"l{i}_{k}"] = v
        np.savez_compressed(
            path,
            **payload,
            meta=np.array([self.vocab_size, self.d_model, self.n_layer, self.n_head, self.max_seq, self.seed]),
        )
