"""The startup that starts the Duck.

observer.startup --full does not start Qwuack.
"""

from __future__ import annotations

import argparse
import os
import time

from qwuack.desk import DESK_DIR, MathDesk, utcnow
from qwuack.pnp import PNPDesk

PID_PATH = DESK_DIR / "qwuack_desk.pid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start Qwuack desks and keep them up.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--body", choices=("collatz", "pnp", "all"), default="all")
    args = parser.parse_args(argv)

    DESK_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    print(f"{utcnow()} QWUACK STARTUP pid={os.getpid()} body={args.body}", flush=True)

    collatz = MathDesk.load()
    pnp = PNPDesk.load()
    interval = max(0.25, args.interval)

    def one_turn(which: str) -> None:
        if which == "collatz":
            results = collatz.session(cycles=2)
            collatz.persist(results)
        else:
            claims = pnp.session()
            pnp.persist(claims)

    try:
        if args.body in {"pnp", "all"} and not pnp.rejected_prize:
            print(f"{utcnow()} REJECTED P=NP reason=unbounded_not_an_experiment", flush=True)
            print(f"{utcnow()} REJECTED P!=NP reason=unbounded_not_an_experiment", flush=True)
            pnp.rejected_prize = True
            pnp.save()
        if args.once:
            if args.body in {"collatz", "all"}:
                one_turn("collatz")
            if args.body in {"pnp", "all"}:
                one_turn("pnp")
            return 0
        turn = 0
        while True:
            if args.body == "collatz":
                one_turn("collatz")
            elif args.body == "pnp":
                one_turn("pnp")
            else:
                one_turn("pnp" if turn % 2 == 0 else "collatz")
                turn += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        collatz.save()
        pnp.save()
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
