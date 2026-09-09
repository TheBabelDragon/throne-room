"""python -m qwuack --runtime [--desk field|math]"""

from __future__ import annotations

import sys


def _forward() -> int:
    argv = list(sys.argv[1:])
    if argv and argv[0] == "runtime":
        argv = argv[1:]
        if "--runtime" not in argv:
            argv.insert(0, "--runtime")

    desk = "field"
    if "--desk" in argv:
        i = argv.index("--desk")
        if i + 1 < len(argv):
            desk = argv[i + 1]

    if desk == "math":
        cycles = 3
        if "--cycles" in argv:
            j = argv.index("--cycles")
            if j + 1 < len(argv):
                cycles = int(argv[j + 1])
        from qwuack.desk import MathDesk, render_desk, write_desk
        results = MathDesk().session(cycles=max(1, cycles))
        write_desk(results)
        print(render_desk(results), flush=True)
        return 0

    from qwuack.runtime import main
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(_forward())
