#!/usr/bin/env python3
"""
Throne Room launcher — operational entry point.

Observes real FieldObservation streams only.
Synthetic generators live under dev/ and are not part of this path.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _live_cmd() -> list[str]:
    return [sys.executable, str(ROOT / "observer" / "live_view.py")]


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Throne Room — live observer for real FieldObservation streams",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (real measurements only):
  python run.py --udp                         # Echo Grid / CSI on 4210
  python run.py --file /tmp/optical.jsonl     # tail a live JSONL feed
  python run.py --file a.jsonl --udp          # multiple sources
  python run.py --file a.jsonl --from-start

No synthetic / demo path. For development fixtures see dev/.
""",
    )
    parser.add_argument(
        "--file", "-f", type=Path, action="append", default=[],
        help="JSONL file of real observations to tail (repeatable)",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Read existing file content first, then tail",
    )
    parser.add_argument(
        "--udp", type=int, nargs="?", const=4210, default=None,
        help="Listen on UDP for real packets (default port 4210)",
    )
    args = parser.parse_args()

    if not args.file and args.udp is None:
        # Default operational posture: listen for live UDP traffic
        args.udp = 4210

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "observer") + os.pathsep + env.get("PYTHONPATH", "")

    cmd = _live_cmd()
    for f in args.file:
        cmd += ["--file", str(f)]
    if args.from_start:
        cmd.append("--from-start")
    if args.udp is not None:
        cmd += ["--udp", str(args.udp)]

    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
        proc.wait()
        sys.exit(proc.returncode or 0)
    except KeyboardInterrupt:
        _kill(proc)
        sys.exit(0)


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    main()
