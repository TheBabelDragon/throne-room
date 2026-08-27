#!/usr/bin/env python3
"""Local training runtime for the language arm.

No API. MetaField trajectories are the corpus. Each --steps value is one
epoch over the train split. Trains:

  1) action head  (user-span hashed n-grams ⊕ weak embed-bag → action)
  2) token embeddings of that span
  3) LM head prefix  (teacher-forced <PROPOSE><ACTION>)

    python -m agent.language.train
    python -m agent.language.train --examples 96 --steps 80
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.language.dataset import Example, from_trajectories, split_hold, synthesize
from agent.language.tokenizer import ArmTokenizer
from agent.language.transformer import ACTION_ORDER, DecoderTransformer, hashed_ngrams

DEFAULT_CKPT = Path("/tmp/metafield/arm_dec_v0.npz")


def _softmax_rows(x: np.ndarray) -> np.ndarray:
    z = x - np.max(x, axis=1, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=1, keepdims=True)


def _ce_scalar(logits: np.ndarray, idx: int) -> tuple[float, np.ndarray]:
    z = logits - np.max(logits)
    e = np.exp(z)
    p = e / np.sum(e)
    loss = float(-np.log(max(float(p[idx]), 1e-9)))
    grad = p.astype(np.float32)
    grad[idx] -= 1.0
    return loss, grad


def train_epoch(model: DecoderTransformer, train: list[Example], lr: float, rng: np.random.RandomState) -> dict:
    n = len(train)
    n_act = len(ACTION_ORDER)
    feats = np.zeros((n, model.feat_dim), dtype=np.float32)
    labels = np.zeros(n, dtype=np.int64)
    spans: list[list[int]] = []
    bags = np.zeros((n, model.d_model), dtype=np.float32)
    nrms = np.zeros(n, dtype=np.float32)
    for i, ex in enumerate(train):
        span = model.action_span(ex.prompt)
        bag_hat, _, nrm = model.embed_bag(span)
        grams = hashed_ngrams(span, model.ngram_dim)
        feats[i] = np.concatenate([model.bag_scale * bag_hat, grams])
        labels[i] = ex.action_index
        spans.append(span)
        bags[i] = bag_hat
        nrms[i] = nrm

    logits = feats @ model.w_act + model.b_act
    P = _softmax_rows(logits.astype(np.float64)).astype(np.float32)
    Y = np.eye(n_act, dtype=np.float32)[labels]
    counts = np.bincount(labels, minlength=n_act).astype(np.float32)
    class_w = 1.0 / np.maximum(counts, 1.0)
    class_w *= n_act / class_w.sum()
    sample_w = class_w[labels][:, None]
    G = ((P - Y) * sample_w) / n
    act_loss = float(-np.log(np.clip(P[np.arange(n), labels], 1e-9, 1.0)).mean())
    d_feat = G @ model.w_act.T
    model.w_act -= lr * (feats.T @ G + 1e-4 * model.w_act)
    model.b_act -= lr * G.sum(axis=0)

    d_bag = d_feat[:, : model.d_model] * model.bag_scale
    for i, span in enumerate(spans):
        nrm = float(nrms[i])
        if nrm < 1e-8 or not span:
            continue
        bag_hat = bags[i]
        d_h = (d_bag[i] - bag_hat * float(np.dot(d_bag[i], bag_hat))) / nrm
        d_vec = (d_h / len(span)).astype(np.float32)
        arr = np.array(span, dtype=np.int64)
        np.add.at(model.tok, arr, -lr * d_vec)
    np.clip(model.tok, -2.0, 2.0, out=model.tok)

    lm_loss = 0.0
    n_lm = 0
    lm_lr = lr * 0.15
    pick = [train[int(rng.randint(0, n))] for _ in range(min(4, n))]
    for ex in pick:
        if not ex.target:
            continue
        prefix = list(ex.prompt)
        take = min(2, len(ex.target))
        for k in range(take):
            _, hidden = model.forward(prefix, return_hidden=True)
            t_loss, d_t = _ce_scalar(hidden[-1] @ model.head, ex.target[k])
            lm_loss += t_loss
            n_lm += 1
            model.head -= lm_lr * np.outer(hidden[-1], d_t)
            prefix.append(ex.target[k])

    pred_i = int(np.argmax(P[-1]))
    return {
        "act_loss": act_loss,
        "lm_loss": lm_loss / max(1, n_lm),
        "pred": ACTION_ORDER[pred_i],
        "gold": ACTION_ORDER[int(labels[-1])],
        "train_acc": float((P.argmax(1) == labels).mean()),
    }


def learn_one(model: DecoderTransformer, prompt: list[int], action_index: int, *, lr: float = 1.0) -> dict:
    """Single-example CE on the action head. Used by `--learn` in the live loop."""
    span = model.action_span(prompt)
    bag_hat, _, nrm = model.embed_bag(span)
    grams = hashed_ngrams(span, model.ngram_dim)
    feat = np.concatenate([model.bag_scale * bag_hat, grams]).astype(np.float32)
    logits = feat @ model.w_act + model.b_act
    loss, d_act = _ce_scalar(logits, action_index)
    d_feat = model.w_act @ d_act
    model.w_act -= lr * (np.outer(feat, d_act) + 1e-4 * model.w_act)
    model.b_act -= lr * d_act
    d_bag = d_feat[: model.d_model] * model.bag_scale
    if nrm >= 1e-8 and span:
        d_h = (d_bag - bag_hat * float(np.dot(d_bag, bag_hat))) / nrm
        d_vec = (d_h / max(1, len(span))).astype(np.float32)
        np.add.at(model.tok, np.array(span, dtype=np.int64), -lr * d_vec)
        np.clip(model.tok, -2.0, 2.0, out=model.tok)
    pred_i = int(np.argmax(logits))
    return {
        "act_loss": loss,
        "pred": ACTION_ORDER[pred_i],
        "gold": ACTION_ORDER[action_index],
    }


def evaluate(model: DecoderTransformer, examples: list[Example]) -> dict:
    correct = 0
    by: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for ex in examples:
        pred = model.predict_action(ex.prompt)
        by[ex.action][1] += 1
        if pred == ex.action:
            correct += 1
            by[ex.action][0] += 1
    per = {k: round(v[0] / max(1, v[1]), 3) for k, v in sorted(by.items())}
    return {
        "n": len(examples),
        "action_acc": correct / max(1, len(examples)),
        "per_class": per,
    }


def run(
    *,
    examples: int,
    steps: int,
    lr: float,
    ckpt: Path,
    seed: int = 7,
    trajectories: Path | None = None,
) -> dict:
    tok = ArmTokenizer()
    model = DecoderTransformer(tok.vocab_size, seed=seed)
    data = synthesize(examples, tokenizer=tok)
    traj_path = None
    if trajectories is not None:
        traj_path = trajectories
    elif os.environ.get("ARM_TRAJECTORIES"):
        traj_path = Path(os.environ["ARM_TRAJECTORIES"])
    if traj_path is not None:
        extra = from_trajectories(traj_path, tokenizer=tok)
        if extra:
            data = data + extra
            print(f"[train] mixed {len(extra)} recorded trajectories from {traj_path}", flush=True)
    train, hold = split_hold(data, seed=seed)
    rng = np.random.RandomState(seed)
    hist = []
    best = -1.0
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    for step in range(steps):
        rec = train_epoch(model, train, lr, rng)
        if step % max(1, steps // 8) == 0 or step + 1 == steps:
            ev = evaluate(model, hold)
            hist.append({"step": step, **rec, "hold_acc": ev["action_acc"], "per_class": ev["per_class"]})
            print(
                f"[train] epoch={step:04d} act_loss={rec['act_loss']:.3f} "
                f"lm={rec['lm_loss']:.3f} train_acc={rec['train_acc']:.2f} "
                f"hold_acc={ev['action_acc']:.2f} per={ev['per_class']}",
                flush=True,
            )
            if ev["action_acc"] >= best:
                best = ev["action_acc"]
                model.save(ckpt)
    if best < 0:
        model.save(ckpt)
        best = evaluate(model, hold)["action_acc"]
    loaded = DecoderTransformer.load(ckpt)
    reload_ev = evaluate(loaded, hold)
    summary = {
        "examples": len(data),
        "train": len(train),
        "hold": len(hold),
        "steps": steps,
        "hold_acc": best,
        "reload_acc": reload_ev["action_acc"],
        "per_class": reload_ev["per_class"],
        "checkpoint": str(ckpt),
        "tokenizer": tok.version,
        "model": loaded.version,
        "history": hist[-6:],
        "ok": best >= 0.5 and reload_ev["action_acc"] >= 0.5,
    }
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Train local language arm on MetaField trajectories")
    p.add_argument("--examples", type=int, default=64)
    p.add_argument("--steps", type=int, default=40, help="Epochs over the train split")
    p.add_argument("--lr", type=float, default=1.5)
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--trajectories", type=Path, default=None, help="Optional recorded JSONL corpus")
    args = p.parse_args()
    summary = run(
        examples=args.examples,
        steps=args.steps,
        lr=args.lr,
        ckpt=args.checkpoint,
        trajectories=args.trajectories,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "history"}, indent=2), flush=True)
    if not summary["ok"]:
        raise SystemExit(1)
    print("[train] checkpoint written. Arm deserves this runtime.", flush=True)


if __name__ == "__main__":
    main()
