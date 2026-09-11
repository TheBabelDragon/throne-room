"""python -m qwuack.workbench --problem Riemann --once"""

from __future__ import annotations

import argparse
import sys

from qwuack.workbench.desk import DuckDesk
from qwuack.workbench.registry import MILLENNIUM, get_problem
from qwuack.workbench.store import ObjectStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Duck proof-workbench. Proof is a typed state. Victory is illegal.",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--problem",
        default="Riemann",
        help="Registry key, pond id, or MATH-MP-XX",
    )
    parser.add_argument("--list", action="store_true", help="Print the registry and exit")
    args = parser.parse_args(argv)
    if args.list:
        for spec in MILLENNIUM.values():
            print(f"{spec.id}  {spec.key:16} {spec.status:8} {spec.title}")
        return 0
    spec = get_problem(args.problem)
    desk = DuckDesk(spec, store=ObjectStore())
    if args.once:
        desk.session(cycles=max(1, args.cycles))
        return 0
    return desk.run_forever(interval=max(0.25, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
