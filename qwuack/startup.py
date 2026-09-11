"""The startup that starts the Duck.

observer.startup --full does not start Qwuack.
"""

from __future__ import annotations

import argparse
import os
import time

from qwuack.desk import DESK_DIR, MathDesk, utcnow
from qwuack.millennium.lab import MillenniumLab
from qwuack.pnp import PNPDesk
from qwuack.workbench.desk import DuckDesk
from qwuack.workbench.registry import get_problem
from qwuack.workbench.store import ObjectStore

PID_PATH = DESK_DIR / "qwuack_desk.pid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start Qwuack desks and keep them up.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--body",
        choices=("collatz", "pnp", "millennium", "workbench", "all"),
        default="all",
    )
    parser.add_argument("--problem", default="Riemann")
    args = parser.parse_args(argv)

    DESK_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    print(f"{utcnow()} QWUACK STARTUP pid={os.getpid()} body={args.body}", flush=True)

    collatz = MathDesk.load()
    pnp = PNPDesk.load()
    lab = MillenniumLab.load()
    bench = DuckDesk(get_problem(args.problem), store=ObjectStore())
    interval = max(0.25, args.interval)

    def one_turn(which: str) -> None:
        if which == "collatz":
            results = collatz.session(cycles=2)
            collatz.persist(results)
        elif which == "pnp":
            claims = pnp.session()
            pnp.persist(claims)
        elif which == "workbench":
            bench.session(cycles=1)
        else:
            batch = lab.session()
            lab.persist(batch)

    try:
        if args.body in {"pnp", "all"} and not pnp.rejected_prize:
            print(f"{utcnow()} REJECTED P=NP reason=unbounded_not_an_experiment", flush=True)
            print(f"{utcnow()} REJECTED P!=NP reason=unbounded_not_an_experiment", flush=True)
            pnp.rejected_prize = True
            pnp.save()
        if args.body in {"millennium", "all"}:
            print(
                f"{utcnow()} MILLENNIUM rule=progress_not_victory "
                "proof_killer=on victory=illegal",
                flush=True,
            )
        if args.body in {"workbench", "all"}:
            print(
                f"{utcnow()} WORKBENCH problem={args.problem} "
                "proof=typed_state victory=illegal",
                flush=True,
            )
        if args.once:
            if args.body == "all":
                one_turn("workbench")
                one_turn("millennium")
            else:
                one_turn(args.body)
            return 0
        turn = 0
        order = {
            "collatz": ("collatz",),
            "pnp": ("pnp",),
            "millennium": ("millennium",),
            "workbench": ("workbench",),
            "all": ("workbench", "millennium", "pnp", "collatz"),
        }[args.body]
        while True:
            one_turn(order[turn % len(order)])
            turn += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        collatz.save()
        pnp.save()
        lab.state.save()
        print(f"{utcnow()} QWUACK halt", flush=True)
        return 0
    finally:
        try:
            if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
