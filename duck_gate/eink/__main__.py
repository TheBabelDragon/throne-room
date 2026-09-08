"""Render a committed GateEvent to the software framebuffer.

Does not bind UDP. Does not call OperatorAbi.validate.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from duck_gate.eink.display import DEFAULT_FRAME, FileDisplay
from duck_gate.eink.sink import EInkSink
from duck_gate.events import from_committed


def main() -> None:
    parser = argparse.ArgumentParser(description="Duck Gate e-ink observer (software frame)")
    parser.add_argument("--sequence", type=int, default=1842)
    parser.add_argument("--status", default="ADMITTED")
    parser.add_argument("--hash", default="91a7c02e")
    parser.add_argument("--deltas", type=int, default=3)
    parser.add_argument("--reason", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_FRAME)
    parser.add_argument("--ack", action="store_true")
    args = parser.parse_args()

    event = from_committed(
        sequence=args.sequence,
        tick_hash=args.hash,
        accepted=args.status.upper() == "ADMITTED",
        action="PROBE",
        delta_count=args.deltas,
        reason=args.reason or ("committed" if args.status.upper() == "ADMITTED" else "INVALID DELTA"),
        last_ok_sequence=None if args.status.upper() == "ADMITTED" else args.sequence - 1,
    )
    display = FileDisplay(args.out)
    sink = EInkSink(display)
    sink.accept(event)
    print(display.frame, end="")
    if args.ack:
        ack = sink.acknowledge()
        print(ack.as_dict() if ack else "no snapshot")


if __name__ == "__main__":
    main()
