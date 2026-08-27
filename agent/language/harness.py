#!/usr/bin/env python3
"""Language Arm evaluation harness.

Builds synthetic FieldTick trajectories, runs the local arm, records the
protocol, and checks replay. No network.

    python -m agent.language.harness
    python -m agent.language.harness --steps 16 --arm model
    python -m agent.language.train          # separate: fit the action head
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.engine import FieldScheduler, seed_field
from agent.language.arm import LanguageArm
from agent.language.tokenizer import ArmTokenizer
from agent.language.trajectories import append_trajectory, trajectory_record
from agent.loop import World
from agent.perception import make_synthetic_csi

SCRIPTS = (
    "What do you perceive?",
    "Probe the energy peak",
    "Remember this field state",
    "Attend to CSI",
    "What do you perceive?",
)


def run(steps: int, arm_mode: str, out: Path) -> dict:
    tok = ArmTokenizer()
    arm = LanguageArm(mode=arm_mode)  # type: ignore[arg-type]
    world = World()
    world.arm = arm
    records = []
    for i in range(max(4, steps)):
        world.step()
        if i < 4:
            continue
        text = SCRIPTS[(i - 4) % len(SCRIPTS)]
        seq0 = world.scheduler.sequence
        turn = world.handle_human(text)
        assert turn is not None
        rec = {
            "i": i,
            "text": text,
            "action": turn.proposal.action_type,
            "accepted": turn.decision.accepted,
            "tick": turn.tick,
            "hash": turn.tick_hash,
            "source": getattr(world.arm.last, "source", None) if world.arm.last else None,
            "tokenizer": tok.version,
        }
        records.append(rec)
        if world.arm.last is not None:
            ctx = world.last_language_context
            if ctx is not None:
                append_trajectory(
                    out,
                    trajectory_record(
                        ctx=ctx,
                        output=world.arm.last,
                        sequence=turn.tick,
                        tick_hash=turn.tick_hash,
                        world_response={
                            "energy_sum": world.snapshot()["energy_sum"],
                            "sequence": world.scheduler.sequence,
                        },
                        accepted=bool(turn.decision.accepted),
                    ),
                )
        assert world.scheduler.sequence == seq0 + 1

    live = list(world.scheduler.field.data)
    replayed = world.scheduler.replay_to(world.scheduler.sequence)
    replay_ok = live == replayed.data

    sched = FieldScheduler(seed_field())
    for i in range(8):
        sched.bind_observation(make_synthetic_csi(i + 1))
        sched.step(0.125)
    twin = FieldScheduler(seed_field())
    for i in range(8):
        twin.bind_observation(make_synthetic_csi(i + 1))
        twin.step(0.125)
    field_det = sched.last is not None and twin.last is not None and sched.last.sequence == twin.last.sequence

    summary = {
        "arm_mode": arm_mode,
        "steps": len(records),
        "actions": [r["action"] for r in records],
        "replay_ok": replay_ok,
        "field_deterministic": field_det,
        "tokenizer_version": tok.version,
        "model_version": arm.model.version,
        "vocab_size": tok.vocab_size,
        "generated_tokens": len(arm.last.tokens) if arm.last else 0,
        "trajectory": str(out),
        "ok": replay_ok and field_det and len(records) > 0,
    }
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Language Arm v0 harness")
    p.add_argument("--steps", type=int, default=12)
    p.add_argument("--arm", choices=("teacher", "model"), default="teacher")
    p.add_argument("--out", type=Path, default=Path("/tmp/metafield/arm_trajectories.jsonl"))
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    summary = run(args.steps, args.arm, args.out)
    print(json.dumps(summary, indent=2), flush=True)
    if not summary["ok"]:
        raise SystemExit(1)
    print("[arm] Language Arm v0 harness passed. No network. Protocol held.", flush=True)


if __name__ == "__main__":
    main()
