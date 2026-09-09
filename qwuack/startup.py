"""The startup that starts the Duck.

observer.startup --full starts the CSI conductor. It does not start Qwuack.
This module starts Qwuack.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from qwuack.desk import DESK_DIR, DESK_STATUS, LATEST_PATH, MEMORY_PATH, STATE_PATH, MathDesk, utcnow

PID_PATH = DESK_DIR / "qwuack_desk.pid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the Qwuack math desk and keep it up.")
    parser.add_argument("--once", action="store_true", help="One batch, then exit")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)

    DESK_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    print(f"{utcnow()}  QWUACK STARTUP", flush=True)
    print(f"  pid      {os.getpid()}", flush=True)
    print(f"  desk     math/collatz", flush=True)
    print(f"  once     {args.once}", flush=True)
    print(f"  interval {args.interval}s", flush=True)
    print(f"  journal  {MEMORY_PATH}", flush=True)
    print(f"  state    {STATE_PATH}", flush=True)
    print(f"  snapshot {DESK_STATUS}", flush=True)
    print(f"  latest   {LATEST_PATH}", flush=True)
    print(f"  note     observer.startup --full is a different process and does not start this", flush=True)

    desk = MathDesk.load()
    print(
        f"  resume   gen={desk.generation} horizon={desk.horizon} "
        f"admitted={desk.admitted_total} killed={desk.killed_total}",
        flush=True,
    )
    try:
        if args.once:
            results = desk.session(cycles=3)
            desk.persist(results)
            return 0
        return desk.run_forever(interval=max(0.25, args.interval))
    finally:
        try:
            if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
