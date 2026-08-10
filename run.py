#!/usr/bin/env python3
"""
Throne Room launcher — single entry point for operational use.
Works without `pip install -e .` (uses local paths).
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
    """Prefer module form; fall back to script path."""
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
    except Exception:
        pass


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

    env = os.environ.copy()
    # ensure observer/ is importable when live_view is run as a script
    env["PYTHONPATH"] = str(ROOT / "observer") + os.pathsep + env.get("PYTHONPATH", "")

    simulator = ROOT / "simulator" / "field_observation_sim.py"

    if args.demo:
        sim = subprocess.Popen(
            [sys.executable, str(simulator)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=ROOT,
            env=env,
        )
        view = None
        try:
            view = subprocess.Popen(
                _live_cmd(),
                stdin=sim.stdout,
                cwd=ROOT,
                env=env,
            )
            # close our copy of the pipe so view sees EOF when sim dies
            if sim.stdout:
                sim.stdout.close()
            view.wait()
        except KeyboardInterrupt:
            pass
        finally:
            if view is not None:
                _kill(view)
            _kill(sim)
        # quiet exit — no traceback
        sys.exit(0)

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
    # ignore SIGPIPE so broken pipes during shutdown stay quiet
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    main()
