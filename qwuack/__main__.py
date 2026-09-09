"""python -m qwuack --runtime [--desk field|math]

--runtime means stay up. --once is the only polite exit.
"""

from __future__ import annotations

import sys


def _flag(argv: list[str], name: str, default: str | None = None) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            return argv[i + 1]
    return default


def _forward() -> int:
    argv = list(sys.argv[1:])
    if argv and argv[0] == "runtime":
        argv = argv[1:]
        if "--runtime" not in argv:
            argv.insert(0, "--runtime")

    desk = _flag(argv, "--desk", "field") or "field"
    once = "--once" in argv
    interval = float(_flag(argv, "--interval", "5") or "5")
    cycles = int(_flag(argv, "--cycles", "3") or "3")

    if desk == "math":
        from qwuack.desk import MathDesk, render_desk, write_desk

        desk_obj = MathDesk.load()
        if once:
            results = desk_obj.session(cycles=max(1, cycles))
            write_desk(results, generation=desk_obj.generation)
            print(render_desk(results, desk_obj), flush=True)
            return 0
        return desk_obj.run_forever(interval=max(0.25, interval))

    from qwuack.runtime import main
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(_forward())
