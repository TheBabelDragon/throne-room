#!/usr/bin/env python3
"""
Aurora autonomous action layer

Rate limits tuned for learning feedback (not starvation):
  - base cooldown 5s (was 8s)
  - high-priority probe / head-surprise gets shorter cooldown
  - decide interval default 1.25s (was 2.0s)

ESCAPE remains sovereign. Fail-closed when Redis absent.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aurora.policies import decide
from aurora.redis_control import RedisControl

try:
    from observer.measurement import AURORA_BASE_COOLDOWN_S, AURORA_DECIDE_INTERVAL_S
except ImportError:
    AURORA_BASE_COOLDOWN_S = 5.0
    AURORA_DECIDE_INTERVAL_S = 1.25

DEFAULT_DIGEST = Path("/tmp/metafield/obs_digest.json")
DEFAULT_CSI = Path("/tmp/metafield/csi.jsonl")
DEFAULT_LOG = Path("/tmp/metafield/aurora_actions.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cooldown_for(action: str, priority: float, base: float) -> float:
    if action in {"hold", "scale_down"}:
        return base
    if action == "probe" and priority >= 0.7:
        return max(2.5, base * 0.55)
    if action == "probe" and priority >= 0.55:
        return max(3.5, base * 0.75)
    if action == "attention":
        return max(3.0, base * 0.7)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Aurora autonomous action layer")
    parser.add_argument("--digest", type=Path, default=DEFAULT_DIGEST)
    parser.add_argument("--csi", type=Path, default=DEFAULT_CSI)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--mode", choices=("observe", "cautious", "auto"), default=None)
    parser.add_argument("--interval", type=float, default=AURORA_DECIDE_INTERVAL_S)
    parser.add_argument("--min-priority", type=float, default=0.45)
    parser.add_argument("--cooldown", type=float, default=AURORA_BASE_COOLDOWN_S)
    parser.add_argument("--file-only", action="store_true")
    args = parser.parse_args()

    args.log.parent.mkdir(parents=True, exist_ok=True)
    control = RedisControl()
    if args.mode and not args.file_only:
        if control.set_mode(args.mode):
            print(f"[aurora] mode → {args.mode}", flush=True)
        else:
            print("[aurora] Redis unavailable — cannot set mode (fail-closed)", flush=True)

    stopping = False

    def _stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    last_fired: dict[str, float] = {}
    print(
        f"[aurora] action layer up  digest={args.digest}  "
        f"file_only={args.file_only}  redis={control.connected}  "
        f"interval={args.interval:g}s  cooldown={args.cooldown:g}s",
        flush=True,
    )

    while not stopping:
        snap = control.snapshot() if not args.file_only else None
        mode = snap.mode if snap else (args.mode or "observe")
        if not args.file_only:
            control.pulse_heartbeat()

        intents = decide(
            digest_path=args.digest,
            csi_jsonl=args.csi,
            mode=mode if not args.file_only else (args.mode or "auto"),
        )

        dispatched = 0
        for intent in intents:
            if intent.priority < args.min_priority:
                continue
            key = f"{intent.action}:{intent.body_id or '*'}"
            now = time.time()
            cd = _cooldown_for(intent.action, intent.priority, args.cooldown)
            if now - last_fired.get(key, 0) < cd:
                continue

            action = intent.to_action()
            action["control"] = {
                "mode": mode,
                "escape": bool(snap.escape) if snap else None,
                "allowed": bool(snap.allowed) if snap else False,
                "redis": bool(snap.connected) if snap else False,
                "cooldown_s": round(cd, 2),
            }

            with args.log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(action, separators=(",", ":")) + "\n")

            if args.file_only:
                print(f"[aurora:file] {intent.action} p={intent.priority:.2f}  {intent.reason}", flush=True)
                last_fired[key] = now
                dispatched += 1
                continue

            if snap is None or not snap.allowed:
                print(
                    f"[aurora:hold] {intent.action} blocked  "
                    f"escape={getattr(snap, 'escape', True)} mode={mode}",
                    flush=True,
                )
                continue

            ok = control.publish_action(action)
            if ok:
                print(f"[aurora:fire] {intent.action} p={intent.priority:.2f}  {intent.reason}", flush=True)
                last_fired[key] = now
                dispatched += 1
            else:
                print(f"[aurora:drop] publish failed for {intent.action}", flush=True)

        state = {
            "timestamp": _now(),
            "mode": mode,
            "intents": len(intents),
            "dispatched": dispatched,
            "escape": bool(snap.escape) if snap else None,
            "allowed": bool(snap.allowed) if snap else False,
        }
        if not args.file_only:
            control.write_state(state)

        time.sleep(max(0.4, args.interval))

    print("[aurora] action layer stopped", flush=True)


if __name__ == "__main__":
    main()
