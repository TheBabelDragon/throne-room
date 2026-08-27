"""Synthetic MetaField trajectories for the language arm.

The engine is the training environment. Teacher policy labels actions.
Recorded JSONL trajectories (observation → action → world_response) mix
in when present — that is the live corpus, not scraped chat logs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from agent.language.arm import LanguageArm
from agent.language.tokenizer import ArmTokenizer
from agent.language.transformer import ACTION_ORDER
from agent.loop import World
from agent.operator_abi import make_proposal

SCRIPTS: tuple[tuple[str, str], ...] = (
    ("What do you perceive?", "SPEAK"),
    ("What's there?", "SPEAK"),
    ("Report the field", "SPEAK"),
    ("Describe the energy", "SPEAK"),
    ("How does it look?", "SPEAK"),
    ("Tell me the state", "SPEAK"),
    ("Probe the energy peak", "PROBE"),
    ("Inject at the peak", "PROBE"),
    ("Nudge the field", "PROBE"),
    ("Excite the lattice", "PROBE"),
    ("Perturb the peak", "PROBE"),
    ("Remember this field state", "REMEMBER"),
    ("Store this observation", "REMEMBER"),
    ("Note this energy", "REMEMBER"),
    ("Memorize the field", "REMEMBER"),
    ("Attend to CSI", "ATTEND"),
    ("Focus on the field", "ATTEND"),
    ("Watch the chat", "ATTEND"),
    ("Look at CSI", "ATTEND"),
    ("Set goal keep the field stable", "SET_GOAL"),
    ("New objective: stay coherent", "SET_GOAL"),
    ("Priority is field stability", "SET_GOAL"),
    ("Wait", "WAIT"),
    ("Hold", "WAIT"),
    ("Pause a moment", "WAIT"),
    ("Query the field", "QUERY_FIELD"),
    ("Inspect the lattice", "QUERY_FIELD"),
    ("Sample the lattice", "QUERY_FIELD"),
)


@dataclass
class Example:
    prompt: list[int]
    target: list[int]
    action: str
    action_index: int
    user_text: str
    tick: int


def synthesize(n: int, *, tokenizer: ArmTokenizer | None = None) -> list[Example]:
    tok = tokenizer or ArmTokenizer()
    world = World()
    world.arm = LanguageArm(mode="teacher", tokenizer=tok, max_new=0)
    out: list[Example] = []
    i = 0
    while len(out) < n:
        world.step()
        text, _expect = SCRIPTS[i % len(SCRIPTS)]
        i += 1
        turn = world.handle_human(text)
        if turn is None or world.last_language_context is None:
            continue
        ctx = world.last_language_context
        proposal = turn.proposal
        prompt = tok.encode_context(ctx)
        target = tok.encode_target(proposal)
        action = proposal.action_type
        if action not in ACTION_ORDER:
            action = "SPEAK"
        out.append(Example(
            prompt=prompt,
            target=target,
            action=action,
            action_index=ACTION_ORDER.index(action),
            user_text=text,
            tick=turn.tick,
        ))
    return out


def from_trajectories(path: Path, tokenizer: ArmTokenizer | None = None) -> list[Example]:
    """Replay recorded language trajectories as training examples."""
    tok = tokenizer or ArmTokenizer()
    if not path.exists():
        return []
    out: list[Example] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        output = rec.get("output") or {}
        ctx = rec.get("context") or {}
        proposal = output.get("proposal") or {}
        action = str(proposal.get("action_type") or "")
        if action not in ACTION_ORDER:
            continue
        prompt = output.get("prompt_tokens") or []
        if not prompt:
            continue
        params = proposal.get("parameters") or {}
        dummy = make_proposal(
            action_type=action,
            parameters=params if isinstance(params, dict) else {},
            target=str(proposal.get("target") or "field"),
            rationale=str(proposal.get("rationale") or "replay"),
            confidence=float(proposal.get("confidence") or 0.5),
            originating_observation=str(ctx.get("observation_id") or "obs_replay"),
        )
        out.append(Example(
            prompt=[int(x) for x in prompt],
            target=tok.encode_target(dummy),
            action=action,
            action_index=ACTION_ORDER.index(action),
            user_text=str(ctx.get("user_text") or ""),
            tick=int(rec.get("sequence") or 0),
        ))
    return out


def split_hold(data: list[Example], *, frac: float = 0.2, seed: int = 7) -> tuple[list[Example], list[Example]]:
    """Hold later ticks of phrasings that also remain in train.

    v1 gate: same operator words, different field tick — not unseen paraphrases.
    """
    rng = np.random.RandomState(seed)
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, ex in enumerate(data):
        by_key[(ex.action, ex.user_text)].append(i)
    hold_idx: set[int] = set()
    for idxs in by_key.values():
        if len(idxs) < 2:
            continue
        n_hold = max(1, int(round(len(idxs) * frac)))
        n_hold = min(n_hold, len(idxs) - 1)
        order = list(idxs)
        rng.shuffle(order)
        hold_idx.update(order[:n_hold])
    if len(hold_idx) < 3:
        by_act: dict[str, list[int]] = defaultdict(list)
        for i, ex in enumerate(data):
            by_act[ex.action].append(i)
        for idxs in by_act.values():
            if len(idxs) >= 2:
                hold_idx.add(idxs[-1])
    hold = [data[i] for i in range(len(data)) if i in hold_idx]
    train = [data[i] for i in range(len(data)) if i not in hold_idx]
    if not train:
        train = list(data)
    if not hold:
        hold = data[: max(1, len(data) // 5)]
    return train, hold
