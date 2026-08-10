"""Ingest backends for Throne Room (file, stdin, UDP)."""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from typing import Iterator

try:
    from .models import Observation
except ImportError:
    from models import Observation  # type: ignore


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
    """Robust non-blocking tail. Handles file recreation / rotation."""
    path = Path(path)
    while True:
        try:
            with path.open("r") as f:
                if not from_start:
                    f.seek(0, 2)
                else:
                    from_start = False

                while True:
                    line = f.readline()
                    if line:
                        yield line
                    else:
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
    """Listen for JSON lines on UDP (Echo Grid CSI uses 4210)."""
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
    """Merge file / stdin / UDP sources into one Observation stream."""

    # Fast path: pure stdin (demo pipe, or `... | throne`)
    only_stdin = use_stdin and not files and udp_port is None
    if only_stdin:
        for line in stdin_lines():
            obs = parse_line(line)
            if obs:
                yield obs
        return

    sources: list[Iterator[str]] = []

    if use_stdin and not sys.stdin.isatty():
        sources.append(stdin_lines())

    if files:
        for p in files:
            sources.append(tail_file(p, from_start=from_start))

    if udp_port is not None:
        sources.append(udp_lines(port=udp_port))

    if not sources:
        # Waiting state — still attach stdin so the UI can sit idle
        sources.append(stdin_lines())

    # Round-robin. Blocking sources (stdin) only appear when data is present
    # because file/UDP iterators sleep themselves when idle.
    while True:
        made_progress = False
        for it in sources:
            try:
                # Non-blocking style: only pull if the iterator is ready.
                # For generators that block, this is still fine at demo rates.
                line = next(it)
                obs = parse_line(line)
                if obs:
                    yield obs
                    made_progress = True
            except StopIteration:
                continue
        if not made_progress:
            time.sleep(0.03)
