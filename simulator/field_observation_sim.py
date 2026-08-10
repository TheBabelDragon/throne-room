#!/usr/bin/env python3
"""
Simple FieldObservation simulator for Throne Room development.
Emits synthetic packets that match the schema used by optical-body-s3 / Echo / MetaField.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass
class FieldObservation:
    timestamp: str
    body_id: str
    region: str
    value: float
    confidence: float = 1.0
    meta: dict | None = None

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_optical(body_id: str = "optical-01") -> Iterator[FieldObservation]:
    t = 0.0
    while True:
        # gentle oscillation + occasional spikes
        base = 0.4 + 0.3 * math.sin(t * 0.7)
        spike = 0.8 if random.random() < 0.04 else 0.0
        yield FieldObservation(
            timestamp=now_iso(),
            body_id=body_id,
            region="intensity",
            value=round(min(1.0, base + spike + random.gauss(0, 0.03)), 4),
            confidence=0.95,
            meta={"source": "sim"},
        )
        t += 0.15
        time.sleep(0.12)


def generate_echo(body_id: str = "echo-01") -> Iterator[FieldObservation]:
    regions = ["motion", "entropy", "df_max", "drive", "fuse"]
    t = 0.0
    while True:
        for region in regions:
            val = 0.5 + 0.4 * math.sin(t * (0.4 + hash(region) % 7 * 0.1))
            val += random.gauss(0, 0.05)
            yield FieldObservation(
                timestamp=now_iso(),
                body_id=body_id,
                region=region,
                value=round(max(0.0, min(1.0, val)), 4),
                confidence=0.9,
                meta={"source": "sim"},
            )
        t += 0.25
        time.sleep(0.18)


def run_simulator(output: Path | None = None, duration_s: float | None = None):
    """Write JSONL to stdout or file."""
    generators = [
        generate_optical("optical-01"),
        generate_echo("echo-01"),
        generate_optical("optical-02"),
    ]

    start = time.time()
    out = open(output, "a") if output else None

    try:
        while True:
            if duration_s and (time.time() - start) > duration_s:
                break
            for gen in generators:
                obs = next(gen)
                line = obs.to_jsonl()
                print(line, flush=True)
                if out:
                    out.write(line + "\n")
                    out.flush()
    finally:
        if out:
            out.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FieldObservation simulator for Throne Room")
    parser.add_argument("--file", type=Path, help="Also write JSONL to this path")
    parser.add_argument("--duration", type=float, help="Stop after N seconds")
    args = parser.parse_args()

    run_simulator(output=args.file, duration_s=args.duration)
