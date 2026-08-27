#!/usr/bin/env python3
"""Chat is the first human interface. Not a special architecture — an actuator.

    python -m agent.chat
    python -m agent.chat --once "What do you perceive?"
    python -m agent.chat --csi /tmp/metafield/csi.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.hashutil import format_tick
from agent.loop import World


def _print_turn(world: World, label: str) -> None:
    snap = world.snapshot()
    print(
        f"[{label}] t{format_tick(snap['sequence'])}  "
        f"hash={snap['tick_hash']}  "
        f"E={snap['energy_sum']:.2f}  I={snap['info_sum']:.2f}  "
        f"att={snap['attention']}  "
        f"accepted={snap['last_accepted']}",
        flush=True,
    )
    if world.messages:
        last = world.messages[-1]
        if last.get("role") in {"agent", "system"}:
            print(f"  {last['role']}: {last['text']}", flush=True)


def _ingest_csi_tail(world: World, path: Path, n: int = 8) -> None:
    if not path.exists():
        print(f"[agent] CSI file not found: {path} — using synthetic", flush=True)
        for _ in range(n):
            world.step()
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError as e:
        print(f"[agent] CSI read failed: {e}", flush=True)
        return
    used = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            pkt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(pkt, dict):
            world.ingest_packet(pkt)
            used += 1
    if used == 0:
        for _ in range(n):
            world.step()
    else:
        print(f"[agent] ingested {used} live FieldObservation packets", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Throne Room agent loop — chat as actuator")
    parser.add_argument("--once", metavar="TEXT", help="Single utterance then exit")
    parser.add_argument("--csi", type=Path, default=None, help="Optional live CSI JSONL")
    parser.add_argument("--ticks", type=int, default=4, help="Warmup ticks before chat")
    parser.add_argument("--memory", type=Path, default=None)
    args = parser.parse_args()

    world = World(memory_path=args.memory)
    if args.csi:
        _ingest_csi_tail(world, args.csi, n=max(args.ticks, 8))
    else:
        for _ in range(args.ticks):
            world.step()

    snap = world.snapshot()
    print(
        f"[agent] SELF online  t{format_tick(snap['sequence'])}  "
        f"integrity={snap['integrity']}  caps={','.join(snap['capabilities'])}",
        flush=True,
    )
    print("[agent] chat is an actuator. Try: What do you perceive? / Probe the energy peak", flush=True)

    if args.once:
        turn = world.handle_human(args.once)
        if turn:
            _print_turn(world, turn.proposal.action_type)
        return

    if not sys.stdin.isatty():
        for line in sys.stdin:
            if line.strip():
                turn = world.handle_human(line)
                if turn:
                    _print_turn(world, turn.proposal.action_type)
        return

    try:
        while True:
            try:
                line = input("operator> ")
            except EOFError:
                print()
                break
            if not line.strip():
                continue
            if line.strip() in {":q", ":quit", "exit"}:
                break
            if line.strip() == ":snap":
                print(json.dumps(world.snapshot(), indent=2, default=str))
                continue
            if line.strip() == ":step":
                world.step()
                _print_turn(world, "TICK")
                continue
            turn = world.handle_human(line)
            if turn:
                _print_turn(world, turn.proposal.action_type)
    except KeyboardInterrupt:
        print("\n[agent] stopped", flush=True)


if __name__ == "__main__":
    main()
