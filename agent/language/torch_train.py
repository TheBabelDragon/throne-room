#!/usr/bin/env python3
"""Train the torch language-arm decoder on MetaField trajectories.

Backprops through transformer blocks. Action loss on pooled user-span
embeddings (pre-attention, same lesson as the numpy n-gram head). LM
loss on composed <PROPOSE><ACTION>body<EOS>.

    python -m agent.language.torch_train
    python -m agent.language.torch_train --examples 64 --steps 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _require_torch():
    try:
        import torch
        return torch
    except ImportError:
        print("[torch] not installed. From the venv: pip install torch", flush=True)
        raise SystemExit(2)


from agent.language.dataset import Example, from_trajectories, split_hold, synthesize
from agent.language.tokenizer import ArmTokenizer
from agent.language.transformer import ACTION_ORDER

DEFAULT_CKPT = Path("/tmp/metafield/arm_gpt_v0.pt")


def _pad_batch(examples: list[Example], pad_id: int, max_seq: int, torch):
    """Keep the user span (end of prompt) and always leave room for the target."""
    seqs = []
    labels = []
    prompt_only = []
    for ex in examples:
        body = (ex.target or [0])[:32]
        keep = max(8, max_seq - len(body))
        p = ex.prompt[-keep:]
        seq = (p + body)[:max_seq]
        lab = ([-100] * len(p) + body)[: len(seq)]
        seqs.append(seq)
        labels.append(lab)
        prompt_only.append(p)
    tlen = max(len(s) for s in seqs)
    plen = max(len(p) for p in prompt_only)
    ids = torch.full((len(seqs), tlen), pad_id, dtype=torch.long)
    lab = torch.full((len(seqs), tlen), -100, dtype=torch.long)
    pr = torch.full((len(seqs), plen), pad_id, dtype=torch.long)
    pad_mask = torch.ones((len(seqs), tlen), dtype=torch.bool)
    pr_mask = torch.ones((len(seqs), plen), dtype=torch.bool)
    act = torch.tensor([ex.action_index for ex in examples], dtype=torch.long)
    for i, (s, l, p) in enumerate(zip(seqs, labels, prompt_only)):
        ids[i, : len(s)] = torch.tensor(s, dtype=torch.long)
        lab[i, : len(l)] = torch.tensor(l, dtype=torch.long)
        pad_mask[i, : len(s)] = False
        pr[i, : len(p)] = torch.tensor(p, dtype=torch.long)
        pr_mask[i, : len(p)] = False
    return ids, lab, pad_mask, pr, pr_mask, act


def evaluate(model, examples: list[Example], torch) -> dict:
    model.eval()
    correct = 0
    by: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    with torch.no_grad():
        for ex in examples:
            pred = model.predict_action(ex.prompt)
            by[ex.action][1] += 1
            if pred == ex.action:
                correct += 1
                by[ex.action][0] += 1
    per = {k: round(v[0] / max(1, v[1]), 3) for k, v in sorted(by.items())}
    return {"n": len(examples), "action_acc": correct / max(1, len(examples)), "per_class": per}


def learn_one(model, prompt: list[int], action_index: int, *, lr: float = 1e-3) -> dict:
    """Single-example CE on the torch action head. Used by `--learn`."""
    torch = _require_torch()
    import torch.nn.functional as F
    model.train()
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    ids = torch.tensor([prompt[-model.max_seq :]], dtype=torch.long)
    pooled = model.pool_user_span(model.embed(ids), ids)
    logits = model.w_act(pooled)
    gold = torch.tensor([action_index], dtype=torch.long)
    loss = F.cross_entropy(logits, gold)
    opt.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    pred_i = int(logits[0].argmax().item())
    return {"act_loss": float(loss.item()), "pred": ACTION_ORDER[pred_i], "gold": ACTION_ORDER[action_index]}


def run(
    *,
    examples: int,
    steps: int,
    lr: float,
    ckpt: Path,
    seed: int = 7,
    batch: int = 8,
    trajectories: Path | None = None,
) -> dict:
    torch = _require_torch()
    from agent.language.torch_model import PAD_ID, ArmGPT

    torch.manual_seed(seed)
    tok = ArmTokenizer()
    model = ArmGPT(tok.vocab_size)
    data = synthesize(examples, tokenizer=tok)
    traj_path = trajectories
    if traj_path is None and os.environ.get("ARM_TRAJECTORIES"):
        traj_path = Path(os.environ["ARM_TRAJECTORIES"])
    if traj_path is not None:
        extra = from_trajectories(traj_path, tokenizer=tok)
        if extra:
            data = data + extra
            print(f"[torch] mixed {len(extra)} recorded trajectories from {traj_path}", flush=True)
    train, hold = split_hold(data, seed=seed)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    hist = []
    best = -1.0
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    import torch.nn.functional as F

    for step in range(steps):
        model.train()
        order = torch.randperm(len(train)).tolist()
        act_losses = []
        lm_losses = []
        n_ok = 0
        n_seen = 0
        for i in range(0, len(order), batch):
            chunk = [train[j] for j in order[i : i + batch]]
            ids, lab, pad_mask, pr, pr_mask, act = _pad_batch(chunk, PAD_ID, model.max_seq, torch)
            lm_logits, _ = model(ids, key_padding_mask=pad_mask)
            if (lab != -100).any():
                lm_loss = F.cross_entropy(
                    lm_logits.reshape(-1, lm_logits.size(-1)),
                    lab.reshape(-1),
                    ignore_index=-100,
                )
            else:
                lm_loss = torch.zeros((), device=ids.device)
            alogits = model.w_act(model.pool_user_span(model.embed(pr), pr))
            act_loss = F.cross_entropy(alogits, act)
            loss = act_loss + 0.4 * lm_loss
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            act_losses.append(float(act_loss.item()))
            lm_losses.append(float(lm_loss.item()))
            n_ok += int((alogits.argmax(-1) == act).sum().item())
            n_seen += len(chunk)
        if step % max(1, steps // 8) == 0 or step + 1 == steps:
            ev = evaluate(model, hold, torch)
            rec = {
                "step": step,
                "act_loss": sum(act_losses) / max(1, len(act_losses)),
                "lm_loss": sum(lm_losses) / max(1, len(lm_losses)),
                "train_acc": n_ok / max(1, n_seen),
                "hold_acc": ev["action_acc"],
                "per_class": ev["per_class"],
            }
            hist.append(rec)
            print(
                f"[torch] epoch={step:04d} act_loss={rec['act_loss']:.3f} "
                f"lm={rec['lm_loss']:.3f} train_acc={rec['train_acc']:.2f} "
                f"hold_acc={ev['action_acc']:.2f} per={ev['per_class']}",
                flush=True,
            )
            if ev["action_acc"] >= best:
                best = ev["action_acc"]
                model.save(ckpt)
    if best < 0:
        model.save(ckpt)
        best = evaluate(model, hold, torch)["action_acc"]
    loaded = ArmGPT.load(ckpt)
    reload_ev = evaluate(loaded, hold, torch)
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
        "backend": "torch",
        "history": hist[-6:],
        "ok": best >= 0.5 and reload_ev["action_acc"] >= 0.5,
    }
    return summary


def main() -> None:
    _require_torch()
    p = argparse.ArgumentParser(description="Train torch language arm on MetaField trajectories")
    p.add_argument("--examples", type=int, default=64)
    p.add_argument("--steps", type=int, default=16, help="Epochs over the train split")
    p.add_argument("--lr", type=float, default=3e-3)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--trajectories", type=Path, default=None)
    args = p.parse_args()
    summary = run(
        examples=args.examples,
        steps=args.steps,
        lr=args.lr,
        ckpt=args.checkpoint,
        batch=args.batch,
        trajectories=args.trajectories,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "history"}, indent=2), flush=True)
    if not summary["ok"]:
        raise SystemExit(1)
    print("[torch] checkpoint written. Decoder blocks actually trained.", flush=True)


if __name__ == "__main__":
    main()
