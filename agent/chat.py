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
import select
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


def _run_turn(world: World, line: str) -> None:
    print("[agent] …", flush=True)
    try:
        turn = world.handle_human(line)
    except Exception as exc:
        print(f"[agent] turn error: {type(exc).__name__}: {exc}", flush=True)
        return
    if turn:
        _print_turn(world, turn.proposal.action_type)


def _repl(world: World, interval: float) -> None:
    print("[agent] type a line. :snap  :drain  :status  :q", flush=True)
    prompt = "operator> "
    use_select = sys.stdin.isatty()
    print(prompt, end="", flush=True)
    while True:
        if use_select:
            try:
                ready, _, _ = select.select([sys.stdin], [], [], max(0.05, interval))
            except (ValueError, OSError):
                use_select = False
                ready = [sys.stdin]
            if not ready:
                world.drain_feeds(max_records=16)
                continue
            line = sys.stdin.readline()
            if line == "":
                print()
                return
        else:
            try:
                line = input(prompt)
            except EOFError:
                print()
                return
        text = line.strip()
        if not text:
            if use_select:
                print(prompt, end="", flush=True)
            continue
        if text in {":q", ":quit", "exit"}:
            return
        if text == ":snap":
            print(json.dumps(world.snapshot(), indent=2, default=str), flush=True)
        elif text == ":step":
            world.drain_feeds(max_records=16)
            world.step()
            _print_turn(world, "TICK")
        elif text == ":drain":
            got = world.drain_feeds(max_records=64)
            print(f"[drain] {got}", flush=True)
        elif text == ":status":
            snap = world.snapshot()
            backlog = 0
            if world.csi_cursor is not None:
                backlog = world.csi_cursor.backlog_bytes()
            print(
                f"[status] t{format_tick(snap['sequence'])} live={snap['live']} "
                f"packets={snap['packets_ingested']} aurora={snap['aurora_seen']} "
                f"body={snap['csi_body'] or '-'} rssi={snap.get('csi_rssi')} "
                f"backlog={backlog}B hash={snap['tick_hash']}",
                flush=True,
            )
        else:
            _run_turn(world, text)
        if use_select:
            print(prompt, end="", flush=True)


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
                    got = world.drain_feeds(max_records=32)
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
        _run_turn(world, args.once)
        return

    if not sys.stdin.isatty():
        for line in sys.stdin:
            if line.strip():
                _run_turn(world, line)
        return

    try:
        _repl(world, args.interval)
    except KeyboardInterrupt:
        print("\n[agent] stopped", flush=True)


if __name__ == "__main__":
    main()
