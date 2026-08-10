#!/usr/bin/env python3
"""
Throne Room launcher

Quick ways to start the observer (and optionally the simulator).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Throne Room — launch the live Field Observer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                     # live view on stdin
  python run.py --demo              # simulator + live view together
  python run.py --file /tmp/x.jsonl # tail an existing JSONL stream
  python run.py --file /tmp/x.jsonl --from-start
""",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Start the built-in simulator and pipe it into the live view",
    )
    parser.add_argument(
        "--file", "-f", type=Path,
        help="JSONL file to tail (ignored when --demo is used)",
    )
    parser.add_argument(
        "--from-start", action="store_true",
        help="Read existing file content first, then tail",
    )
    args = parser.parse_args()

    live_view = ROOT / "observer" / "live_view.py"
    simulator = ROOT / "simulator" / "field_observation_sim.py"

    if args.demo:
        # Start simulator → pipe into live view
        sim = subprocess.Popen(
            [sys.executable, str(simulator)],
            stdout=subprocess.PIPE,
            cwd=ROOT,
        )
        try:
            subprocess.run(
                [sys.executable, str(live_view)],
                stdin=sim.stdout,
                cwd=ROOT,
            )
        finally:
            sim.terminate()
            sim.wait()
        return

    # Normal mode: just the observer
    cmd = [sys.executable, str(live_view)]
    if args.file:
        cmd += ["--file", str(args.file)]
    if args.from_start:
        cmd += ["--from-start"]

    subprocess.run(cmd, cwd=ROOT)


if __name__ == "__main__":
    main()
