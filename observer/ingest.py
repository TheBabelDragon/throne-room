"""Ingest backends for Throne Room (file, stdin, UDP)."""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from typing import Iterator

from .models import Observation


def parse_line(line: str) -> Observation | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
        return Observation(
            timestamp=str(data.get("timestamp", "")),
            body_id=str(data.get("body_id", "unknown")),
            region=str(data.get("region", "unknown")),
            value=float(data.get("value", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
            meta=data.get("meta"),
        )
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return None


def tail_file(path: Path, from_start: bool = False) -> Iterator[str]:
    """Robust non-blocking tail. Handles file recreation."""
    path = Path(path)
    while True:
        try:
            with path.open("r") as f:
                if not from_start:
                    f.seek(0, 2)
                else:
                    from_start = False  # only once

                while True:
                    line = f.readline()
                    if line:
                        yield line
                    else:
                        # detect truncation / rotation
                        try:
                            if path.stat().st_size < f.tell():
                                f.seek(0)
                        except OSError:
                            break
                        time.sleep(0.04)
        except FileNotFoundError:
            time.sleep(0.3)
        except OSError:
            time.sleep(0.3)


def stdin_lines() -> Iterator[str]:
    for line in sys.stdin:
        yield line


def udp_lines(host: str = "0.0.0.0", port: int = 4210) -> Iterator[str]:
    """Listen for newline-delimited or single-packet JSON on UDP.

    Compatible with Echo Grid CSI emission (UDP 4210).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(0.2)

    try:
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
                text = data.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    if line.strip():
                        yield line
            except socket.timeout:
                continue
    finally:
        sock.close()


def multi_source(
    files: list[Path] | None = None,
    use_stdin: bool = False,
    udp_port: int | None = None,
    from_start: bool = False,
) -> Iterator[Observation]:
    """Merge multiple sources. Simple round-robin polling."""
    import select

    sources: list[tuple[str, Iterator[str]]] = []

    if use_stdin and not sys.stdin.isatty():
        sources.append(("stdin", stdin_lines()))

    if files:
        for p in files:
            sources.append((f"file:{p}", tail_file(p, from_start=from_start)))

    if udp_port is not None:
        sources.append((f"udp:{udp_port}", udp_lines(port=udp_port)))

    if not sources:
        # default to stdin even if tty so user sees the waiting state
        sources.append(("stdin", stdin_lines()))

    # naive sequential merge — good enough for operational demo rates
    # (real high-rate systems can move to threads later)
    iterators = [it for _, it in sources]
    while True:
        made_progress = False
        for it in iterators:
            try:
                line = next(it)
                obs = parse_line(line)
                if obs:
                    yield obs
                    made_progress = True
            except StopIteration:
                continue
        if not made_progress:
            time.sleep(0.03)
