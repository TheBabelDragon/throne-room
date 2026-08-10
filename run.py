#!/usr/bin/env python3
"""
Throne Room launcher — single entry point for operational use.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Throne Room — operational live Field Observer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --demo                  # simulator + live view
  python run.py --file /tmp/x.jsonl     # tail a JSONL stream
  python run.py --udp                   # listen on UDP 4210 (Echo)
  python run.py --file a.jsonl --udp    # both at once
  python run.py --file a.jsonl --from-start
""",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Start built-in simulator and pipe into the live view",
    )
    parser.add_argument(
        "--file", "-f", type=Path, action="append", default=[],
        help="JSONL file to tail (repeatable)",
    )
    parser.add_argument(
        "--from-start", action="store_true",
        help="Read existing file content first, then tail",
    )
    parser.add_argument(
        "--udp", type=int, nargs="?", const=4210, default=None,
        help="Also listen on UDP (default port 4210)",
    )
    args = parser.parse_args()

    live_view = [sys.executable, "-m", "observer.live_view"]
    simulator = ROOT / "simulator" / "field_observation_sim.py"

    if args.demo:
        sim = subprocess.Popen(
            [sys.executable, str(simulator)],
            stdout=subprocess.PIPE,
            cwd=ROOT,
        )
        try:
            subprocess.run(live_view, stdin=sim.stdout, cwd=ROOT)
        finally:
            sim.terminate()
            sim.wait()
        return

    cmd = live_view[:]
    for f in args.file:
        cmd += ["--file", str(f)]
    if args.from_start:
        cmd.append("--from-start")
    if args.udp is not None:
        cmd += ["--udp", str(args.udp)]

    # if nothing specified, default to stdin behaviour inside live_view
    subprocess.run(cmd, cwd=ROOT)


if __name__ == "__main__":
    main()
