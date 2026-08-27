"""Tiny decoder transformer. Local, numpy, no network.

v1 trains an action head on user-span hashed char-ngrams (fastText) plus
a weakly-scaled embedding bag, and a prefix LM head. Decoder blocks stay
genesis until a torch path exists — that is honest, not a stub.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from agent.language.tokenizer import BYTE_SIZE, SPECIALS

MODEL_VERSION = "arm-dec-v1"
ACTION_ORDER: tuple[str, ...] = (
    "SPEAK", "PROBE", "REMEMBER", "ATTEND", "SET_GOAL", "QUERY_FIELD", "WAIT",
)
USER_ID = BYTE_SIZE + SPECIALS.index("<USER>")
ARM_ID = BYTE_SIZE + SPECIALS.index("<ARM>")
NGRAM_DIM = 64
BAG_SCALE = 0.2


def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    z = x - np.max(x, axis=axis, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=axis, keepdims=True)


def _layernorm(x: np.ndarray, gain: np.ndarray, bias: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    mu = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return gain * (x - mu) / np.sqrt(var + eps) + bias


def user_span_ids(ids: list[int], user_id: int = USER_ID, arm_id: int = ARM_ID) -> list[int]:
    last_user = None
    last_arm = None
    for i, tok in enumerate(ids):
        if int(tok) == user_id:
            last_user = i
        elif int(tok) == arm_id:
            last_arm = i
    if last_user is None:
        return ids[-32:] if ids else [0]
    end = last_arm if (last_arm is not None and last_arm > last_user) else len(ids)
    span = ids[last_user:end]
    if span and int(span[0]) == user_id:
        span = span[1:]
    return span if span else (ids[-32:] if ids else [0])


def hashed_ngrams(ids: list[int], dim: int = NGRAM_DIM, ns: tuple[int, ...] = (1, 2, 3)) -> np.ndarray:
    """Deterministic hashed byte n-grams of the user span. FastText-style."""
    v = np.zeros(dim, dtype=np.float32)
    seq = [int(i) for i in ids if 0 <= int(i) < BYTE_SIZE]
    if not seq:
        seq = [0]
    for n in ns:
        limit = len(seq) - n + 1
        if limit <= 0:
            continue
        for i in range(limit):
            h = 2166136261
            for k in range(n):
                h ^= seq[i + k]
                h = (h * 16777619) & 0xFFFFFFFF
            v[h % dim] += 1.0
    nrm = float(np.linalg.norm(v))
    if nrm > 1e-8:
        v /= nrm
    return v


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
        self.ngram_dim = NGRAM_DIM
        self.bag_scale = BAG_SCALE
        self.feat_dim = d_model + NGRAM_DIM
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
        self.w_act = rng.randn(self.feat_dim, len(ACTION_ORDER)).astype(np.float32) * scale
        self.b_act = np.zeros(len(ACTION_ORDER), dtype=np.float32)

    def forward(self, ids: list[int], *, return_hidden: bool = False):
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
        hidden = _layernorm(x, self.fng, self.fnb)
        logits = hidden @ self.head
        if return_hidden:
            return logits, hidden
        return logits

    def action_span(self, ids: list[int]) -> list[int]:
        return user_span_ids(ids)

    def embed_bag(self, ids: list[int]) -> tuple[np.ndarray, np.ndarray, float]:
        if not ids:
            ids = [0]
        arr = np.array(ids, dtype=np.int64)
        vecs = self.tok[arr]
        h = vecs.mean(axis=0)
        n = float(np.linalg.norm(h))
        if n < 1e-8:
            return h, h, n
        return h / n, h, n

    def action_features(self, ids: list[int]) -> np.ndarray:
        span = self.action_span(ids)
        bag, _, _ = self.embed_bag(span)
        grams = hashed_ngrams(span, self.ngram_dim)
        return np.concatenate([self.bag_scale * bag, grams]).astype(np.float32)

    def action_logits(self, ids: list[int]) -> np.ndarray:
        return self.action_features(ids) @ self.w_act + self.b_act

    def predict_action(self, ids: list[int]) -> str:
        idx = int(np.argmax(self.action_logits(ids)))
        return ACTION_ORDER[idx]

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
            "fng": self.fng, "fnb": self.fnb, "w_act": self.w_act, "b_act": self.b_act,
        }
        for i, layer in enumerate(self.layers):
            for k, v in layer.items():
                payload[f"l{i}_{k}"] = v
        np.savez_compressed(
            path,
            **payload,
            meta=np.array([self.vocab_size, self.d_model, self.n_layer, self.n_head, self.max_seq, self.seed]),
        )

    @classmethod
    def load(cls, path: Path) -> "DecoderTransformer":
        data = np.load(path, allow_pickle=True)
        meta = data["meta"]
        model = cls(
            int(meta[0]),
            d_model=int(meta[1]),
            n_layer=int(meta[2]),
            n_head=int(meta[3]),
            max_seq=int(meta[4]),
            seed=int(meta[5]) if len(meta) > 5 else 7,
        )
        model.tok = data["tok"]
        model.pos = data["pos"]
        model.head = data["head"]
        model.fng = data["fng"]
        model.fnb = data["fnb"]
        if "w_act" in data.files and data["w_act"].shape == model.w_act.shape:
            model.w_act = data["w_act"]
        if "b_act" in data.files and data["b_act"].shape == model.b_act.shape:
            model.b_act = data["b_act"]
        for i, layer in enumerate(model.layers):
            for k in list(layer.keys()):
                key = f"l{i}_{k}"
                if key in data.files:
                    layer[k] = data[key]
        return model
