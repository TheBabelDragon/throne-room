"""
Host load guard — extracted from OptimizerDaemon pattern.

When CPU or memory pressure is high, recommend Aurora scale_down / hold.
No mining coupling. Pure observability.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass


@dataclass
class HostSnapshot:
    cpu_pct: float
    mem_pct: float
    stressed: bool
    advice: str  # "ok" | "scale_down" | "hold"


def cpu_percent() -> float:
    system = platform.system()
    if system in ("Linux", "Darwin"):
        try:
            load1 = os.getloadavg()[0]
            n = os.cpu_count() or 1
            return min(100.0, (load1 / n) * 100.0)
        except OSError:
            return 0.0
    return 0.0


def mem_percent() -> float:
    system = platform.system()
    if system == "Linux":
        try:
            info: dict[str, int] = {}
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    parts = v.strip().split()
                    if parts and parts[0].isdigit():
                        info[k.strip()] = int(parts[0])
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            if total > 0:
                return ((total - avail) / total) * 100.0
        except OSError:
            return 0.0
    return 0.0


def snapshot(cpu_high: float = 80.0, mem_high: float = 75.0) -> HostSnapshot:
    cpu = cpu_percent()
    mem = mem_percent()
    if cpu > cpu_high or mem > mem_high:
        advice = "hold" if (cpu > 92 or mem > 90) else "scale_down"
        return HostSnapshot(cpu, mem, True, advice)
    return HostSnapshot(cpu, mem, False, "ok")
