"""python -m qwuack --runtime [--desk field|math]"""

from __future__ import annotations

import sys

from qwuack.runtime import main


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if argv and argv[0] == "runtime":
        argv = argv[1:]
        if "--runtime" not in argv:
            argv.insert(0, "--runtime")
    sys.exit(main(argv))
