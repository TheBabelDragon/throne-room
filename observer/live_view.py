#!/usr/bin/env python3
"""
Throne Room – operational live Field Observer

Renders a live Rich dashboard of real FieldObservation streams.
Battleship-style time sparks show measurement intensity over time.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

try:
    from .ingest import multi_source
    from .models import BodyState, Observation, RegionHistory
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ingest import multi_source  # type: ignore
    from models import BodyState, Observation, RegionHistory  # type: ignore


def _is_synthetic(obs: Observation) -> bool:
    if not obs.meta:
        return False
    src = str(obs.meta.get("source", "")).lower()
    return src in {"sim", "synthetic"} or bool(obs.meta.get("dev_only"))


def _intensity_style(v: float) -> str:
    if v >= 0.85:
        return "bold bright_green"
    if v >= 0.65:
        return "green"
    if v >= 0.40:
        return "yellow"
    if v >= 0.20:
        return "dark_orange3"
    return "bright_black"


def _battle_spark(hist: RegionHistory | None) -> Text:
    """Coloured battleship time-grid of measurement intensity."""
    text = Text()
    if not hist or not hist.values:
        text.append("·" * 16, style="bright_black")
        return text
    for glyph, intensity in hist.cells():
        text.append(glyph, style=_intensity_style(intensity))
    return text


def _empty_fleet_board() -> Text:
    """Beautiful idle load — empty battleship grids awaiting contact."""
    rows = [
        "    A B C D E F G H I J K L M N O P",
        "  1 · · · · · · · · · · · · · · · ·",
        "  2 · · · · · · · · · · · · · · · ·",
        "  3 · · · · · · · · · · · · · · · ·",
        "  4 · · · · · · · · · · · · · · · ·",
        "  5 · · · · · · · · · · · · · · · ·",
        "  6 · · · · · · · · · · · · · · · ·",
        "  7 · · · · · · · · · · · · · · · ·",
        "  8 · · · · · · · · · · · · · · · ·",
    ]
    t = Text()
    t.append("awaiting real field contact\n", style="dim cyan")
    t.append("\n".join(rows), style="bright_black")
    t.append("\n\n", style="")
    t.append("UDP :4210  ·  JSONL file  ·  live body stdin", style="dim")
    return t


class ThroneRoom:
    def __init__(self) -> None:
        self.bodies: dict[str, BodyState] = defaultdict(BodyState)
        self.total_packets = 0
        self.start_time = time.time()
        self._last_rate_check = self.start_time
        self._packets_at_last_check = 0
        self.rate_hz = 0.0
        self.synthetic_seen = False

    def ingest(self, obs: Observation) -> None:
        if _is_synthetic(obs):
            self.synthetic_seen = True

        now = time.time()
        state = self.bodies[obs.body_id]
        state.regions[obs.region] = obs
        state.last_seen = now
        state.packet_count += 1

        if obs.region not in state.history:
            state.history[obs.region] = RegionHistory()
        state.history[obs.region].push(obs.value)

        self.total_packets += 1

        if now - self._last_rate_check >= 1.0:
            dt = now - self._last_rate_check
            self.rate_hz = (self.total_packets - self._packets_at_last_check) / dt
            self._last_rate_check = now
            self._packets_at_last_check = self.total_packets

    def render(self) -> Group:
        now = time.time()
        uptime = now - self.start_time

        header = Table.grid(expand=True)
        header.add_column(justify="left")
        header.add_column(justify="center")
        header.add_column(justify="right")

        active = sum(1 for b in self.bodies.values() if now - b.last_seen < 5.0)
        stalled = sum(1 for b in self.bodies.values() if now - b.last_seen >= 5.0)

        header.add_row(
            Text("THRONE ROOM", style="bold magenta"),
            Text(
                f"{active} active  ·  {stalled} stalled  ·  {self.rate_hz:.1f} Hz",
                style="cyan",
            ),
            Text(f"pkts {self.total_packets}   up {uptime:.0f}s", style="dim"),
        )

        panels: list[Panel] = []

        if self.synthetic_seen:
            panels.append(
                Panel(
                    "[yellow]Synthetic / non-measured packets present. "
                    "Operational use expects real body streams only.[/]",
                    border_style="yellow",
                    title="[yellow]dev warning[/]",
                )
            )

        for body_id in sorted(self.bodies.keys()):
            state = self.bodies[body_id]
            age = now - state.last_seen

            if age < 2.0:
                age_style, border = "green", "green"
            elif age < 8.0:
                age_style, border = "yellow", "yellow"
            else:
                age_style, border = "red", "red"

            table = Table(
                show_header=True,
                header_style="bold cyan",
                box=None,
                pad_edge=False,
                expand=True,
            )
            table.add_column("region", style="white", min_width=10)
            table.add_column("value", justify="right", min_width=7)
            table.add_column("time →", min_width=18)
            table.add_column("conf", justify="right", min_width=5)

            for region, obs in sorted(state.regions.items()):
                hist = state.history.get(region)
                spark = _battle_spark(hist)

                if obs.value > 0.7:
                    val_style = "bold green"
                elif obs.value > 0.35:
                    val_style = "yellow"
                else:
                    val_style = "dim"

                table.add_row(
                    region,
                    Text(f"{obs.value:.3f}", style=val_style),
                    spark,
                    f"{obs.confidence:.2f}",
                )

            title = (
                f"[bold]{body_id}[/]  [{age_style}]●[/]  "
                f"[dim]{state.packet_count} pkts[/]"
            )
            panels.append(Panel(table, title=title, border_style=border, padding=(0, 1)))

        if not self.bodies:
            panels.append(
                Panel(
                    _empty_fleet_board(),
                    title="[dim]fleet grid[/]",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        return Group(header, Text(""), *panels)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Throne Room – live observer for real FieldObservation streams",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        action="append",
        default=[],
        help="JSONL file of real observations to tail (repeatable)",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Read existing file content first, then tail",
    )
    parser.add_argument(
        "--udp",
        type=int,
        nargs="?",
        const=4210,
        default=None,
        help="Listen on UDP for real packets (default 4210)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Force reading from stdin",
    )
    args = parser.parse_args()

    console = Console()
    throne = ThroneRoom()

    use_stdin = args.stdin or (not args.file and args.udp is None)

    source = multi_source(
        files=args.file or None,
        use_stdin=use_stdin,
        udp_port=args.udp,
        from_start=args.from_start,
    )

    try:
        with Live(
            throne.render(),
            console=console,
            refresh_per_second=10,
            screen=False,
        ) as live:
            for obs in source:
                throne.ingest(obs)
                live.update(throne.render())
    except KeyboardInterrupt:
        console.print("\n[dim]Throne Room closed.[/]")
        sys.exit(0)


if __name__ == "__main__":
    main()
