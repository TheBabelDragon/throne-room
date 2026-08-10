#!/usr/bin/env python3
"""
Throne Room – first live view

Tails a FieldObservation JSONL stream (file or stdin) and renders a live
Rich dashboard grouped by body → region.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class Observation:
    timestamp: str
    body_id: str
    region: str
    value: float
    confidence: float = 1.0
    meta: dict[str, Any] | None = None


@dataclass
class BodyState:
    last_seen: float = 0.0
    regions: dict[str, Observation] = field(default_factory=dict)


class ThroneRoom:
    def __init__(self) -> None:
        self.bodies: dict[str, BodyState] = defaultdict(BodyState)
        self.total_packets = 0
        self.start_time = time.time()

    def ingest(self, obs: Observation) -> None:
        state = self.bodies[obs.body_id]
        state.regions[obs.region] = obs
        state.last_seen = time.time()
        self.total_packets += 1

    def render(self) -> Group:
        now = time.time()
        uptime = now - self.start_time

        header = Table.grid(expand=True)
        header.add_column(justify="left")
        header.add_column(justify="right")
        header.add_row(
            Text("THRONE ROOM", style="bold magenta"),
            Text(f"packets: {self.total_packets}   uptime: {uptime:.0f}s", style="dim"),
        )

        panels = []
        for body_id in sorted(self.bodies.keys()):
            state = self.bodies[body_id]
            age = now - state.last_seen
            age_style = "green" if age < 2.0 else "yellow" if age < 8.0 else "red"

            table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
            table.add_column("region", style="white", min_width=12)
            table.add_column("value", justify="right", min_width=8)
            table.add_column("conf", justify="right", min_width=6)
            table.add_column("age", justify="right", min_width=6)

            for region, obs in sorted(state.regions.items()):
                val_style = "bold green" if obs.value > 0.7 else "yellow" if obs.value > 0.35 else "dim"
                table.add_row(
                    region,
                    Text(f"{obs.value:.3f}", style=val_style),
                    f"{obs.confidence:.2f}",
                    Text(f"{age:.1f}s", style=age_style),
                )

            title = f"[bold]{body_id}[/]  [{age_style}]●[/]"
            panels.append(Panel(table, title=title, border_style="blue", padding=(0, 1)))

        if not panels:
            panels.append(Panel("[dim]waiting for FieldObservation packets…[/]", border_style="dim"))

        return Group(header, *panels)


def parse_line(line: str) -> Observation | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
        return Observation(
            timestamp=data.get("timestamp", ""),
            body_id=str(data.get("body_id", "unknown")),
            region=str(data.get("region", "unknown")),
            value=float(data.get("value", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
            meta=data.get("meta"),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def tail_file(path: Path):
    """Simple non-blocking tail."""
    with path.open("r") as f:
        f.seek(0, 2)  # go to end
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.05)


def main() -> None:
    parser = argparse.ArgumentParser(description="Throne Room – live Field Observer")
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="JSONL file to tail (default: stdin)",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Read existing content first, then tail",
    )
    args = parser.parse_args()

    console = Console()
    throne = ThroneRoom()

    def source():
        if args.file:
            if args.from_start and args.file.exists():
                with args.file.open() as f:
                    for line in f:
                        yield line
            yield from tail_file(args.file)
        else:
            for line in sys.stdin:
                yield line

    with Live(throne.render(), console=console, refresh_per_second=8) as live:
        try:
            for line in source():
                obs = parse_line(line)
                if obs:
                    throne.ingest(obs)
                    live.update(throne.render())
        except KeyboardInterrupt:
            console.print("\n[dim]Throne Room closed.[/]")


if __name__ == "__main__":
    main()
