#!/usr/bin/env python3
"""Chat is the first human interface. Not a special architecture — an actuator.

    python -m agent.chat
    python -m agent.chat --once "What do you perceive?"
    python -m agent.chat --live
    python -m agent.chat --live --follow
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from agent.feeds import DEFAULT_AURORA, DEFAULT_CSI, DEFAULT_MEMORY, DEFAULT_TICKS
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


def _attach(world: World, args: argparse.Namespace) -> None:
    if not args.live:
        for _ in range(max(1, args.ticks)):
            world.step()
        return
    csi = args.csi or DEFAULT_CSI
    aurora = args.aurora or DEFAULT_AURORA
    journal = args.journal or DEFAULT_TICKS
    warmup = args.warmup if args.warmup is not None else 32
    counts = world.attach_feeds(csi=csi, aurora=aurora, ticks=journal, warmup=warmup)
    print(
        f"[agent] live  csi={csi}  aurora={aurora}  journal={journal}",
        flush=True,
    )
    print(
        f"[agent] warmup  csi={counts['csi']} aurora={counts['aurora']}  keep-last={warmup}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Throne Room agent loop — chat as actuator")
    parser.add_argument("--once", metavar="TEXT", help="Single utterance then exit")
    parser.add_argument("--csi", type=Path, default=None, help="FieldObservation / wifi_csi JSONL")
    parser.add_argument("--aurora", type=Path, default=None, help="aurora_actions.jsonl")
    parser.add_argument("--journal", type=Path, default=None, help="Agent FieldTick JSONL (live default /tmp/metafield/agent_ticks.jsonl)")
    parser.add_argument("--ticks", type=int, default=4, help="Offline synthetic warmup ticks (not a file path)")
    parser.add_argument("--warmup", type=int, default=None, help="Live: keep-last CSI/Aurora lines (default 32)")
    parser.add_argument("--memory", type=Path, default=None)
    parser.add_argument("--live", action="store_true", help="Follow /tmp/metafield CSI + Aurora journals")
    parser.add_argument("--follow", action="store_true", help="Tick from feeds (no REPL). Ctrl+C to stop")
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args()

    memory = args.memory
    if args.live and memory is None:
        memory = DEFAULT_MEMORY
    world = World(memory_path=memory)
    _attach(world, args)

    snap = world.snapshot()
    print(
        f"[agent] SELF online  t{format_tick(snap['sequence'])}  "
        f"integrity={snap['integrity']}  live={snap['live']}  "
        f"caps={','.join(snap['capabilities'])}",
        flush=True,
    )
    print("[agent] chat is an actuator. Try: What do you perceive? / Probe the energy peak", flush=True)

    if args.follow:
        print("[agent] follow mode — CSI/Aurora → FieldTick. No UDP bind.", flush=True)
        beat = time.monotonic()
        try:
            while True:
                try:
                    got = world.drain_feeds()
                except Exception as exc:
                    print(f"[follow] drain error: {type(exc).__name__}: {exc}", flush=True)
                    time.sleep(max(0.05, args.interval))
                    continue
                now = time.monotonic()
                if got["csi"] or got["aurora"]:
                    snap = world.snapshot()
                    rssi = snap.get("csi_rssi")
                    rssi_s = f"{rssi:.1f}dBm" if isinstance(rssi, (int, float)) else "-"
                    print(
                        f"[follow] t{format_tick(snap['sequence'])}  "
                        f"csi+={got['csi']} aurora+={got['aurora']}  "
                        f"E={snap['energy_sum']:.2f}  rssi={rssi_s}  "
                        f"body={snap['csi_body'] or '-'}  hash={snap['tick_hash']}",
                        flush=True,
                    )
                    if got["aurora"]:
                        last_a = world.self.peek("working.last_aurora") or {}
                        print(
                            f"[aurora] {last_a.get('action', '?')}  "
                            f"accepted={last_a.get('accepted')}  {last_a.get('reason', '')}",
                            flush=True,
                        )
                    beat = now
                elif now - beat >= 8.0:
                    snap = world.snapshot()
                    waiting = args.csi or DEFAULT_CSI
                    print(
                        f"[follow] idle  t{format_tick(snap['sequence'])}  waiting on {waiting}",
                        flush=True,
                    )
                    beat = now
                time.sleep(max(0.05, args.interval))
        except KeyboardInterrupt:
            print("\n[agent] stopped", flush=True)
        return

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
                world.drain_feeds()
                world.step()
                _print_turn(world, "TICK")
                continue
            if line.strip() == ":drain":
                got = world.drain_feeds()
                print(f"[drain] {got}", flush=True)
                continue
            turn = world.handle_human(line)
            if turn:
                _print_turn(world, turn.proposal.action_type)
    except KeyboardInterrupt:
        print("\n[agent] stopped", flush=True)


if __name__ == "__main__":
    main()
