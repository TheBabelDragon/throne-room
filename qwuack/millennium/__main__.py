"""python -m qwuack.millennium [--once] [--pond rh] [--interval 5]"""

from __future__ import annotations

import argparse
import sys

from qwuack.millennium.lab import DEFAULT_ROTATION, MillenniumLab


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Millennium Lab — progress only. Victory is illegal.",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--pond",
        choices=("all",) + DEFAULT_ROTATION,
        default="all",
        help="Attack one pond or rotate through all eight.",
    )
    args = parser.parse_args(argv)
    lab = MillenniumLab.load()
    ponds = None if args.pond == "all" else (args.pond,)
    if args.once:
        for _ in range(max(1, args.cycles)):
            batch = lab.session(ponds=ponds)
            lab.persist(batch)
        return 0
    return lab.run_forever(interval=max(0.25, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
