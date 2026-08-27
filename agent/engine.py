"""Deterministic voxel field + FieldTick scheduler.

No wall-clock. No randomness. Replay from genesis + log == live field.
Intelligence does not live here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from agent.hashutil import canonical, fnv1a
from agent.schemas import (
    CHANNEL_COUNT,
    SYS,
    SYSTEM_NAMES,
    CellCoord,
    Channel,
    FieldDelta,
    FieldObservation,
    FieldTick,
)

N = 16
EPS = 1e-5


def _idx(x: int, y: int, z: int, ch: int) -> int:
    return ((z * N + y) * N + x) * CHANNEL_COUNT + ch


def _in_bounds(c: CellCoord) -> bool:
    return 0 <= c.x < N and 0 <= c.y < N and 0 <= c.z < N


class VoxelField:
    def __init__(self, source: list[float] | None = None) -> None:
        size = N * N * N * CHANNEL_COUNT
        self.data = list(source) if source is not None else [0.0] * size

    def clone(self) -> VoxelField:
        return VoxelField(self.data)

    def sample(self, c: CellCoord, ch: int) -> float:
        if not _in_bounds(c):
            return 0.0
        return self.data[_idx(c.x, c.y, c.z, ch)]

    def write(self, c: CellCoord, ch: int, v: float) -> None:
        if not _in_bounds(c):
            return
        self.data[_idx(c.x, c.y, c.z, ch)] = v

    def apply(self, deltas: list[FieldDelta]) -> None:
        for d in deltas:
            self.write(d.cell, d.channel, d.new_value)

    def each_cell(self, fn) -> None:
        y = 0
        for z in range(N):
            for x in range(N):
                fn(CellCoord(x, y, z))

    def slice2d(self, ch: int) -> list[float]:
        out = [0.0] * (N * N)
        for z in range(N):
            for x in range(N):
                out[z * N + x] = self.sample(CellCoord(x, 0, z), ch)
        return out

    def sum(self, ch: int) -> float:
        total = 0.0

        def add(c: CellCoord) -> None:
            nonlocal total
            total += self.sample(c, ch)

        self.each_cell(add)
        return total

    def peak(self, ch: int) -> tuple[CellCoord, float]:
        best = CellCoord(8, 0, 8)
        value = 0.0

        def walk(c: CellCoord) -> None:
            nonlocal best, value
            v = self.sample(c, ch)
            if v > value:
                best, value = c, v

        self.each_cell(walk)
        return best, value


def _push(out: list[FieldDelta], d: FieldDelta) -> None:
    if abs(d.new_value - d.old_value) < 1e-8:
        return
    out.append(d)


def _sort_deterministic(items: list[FieldDelta]) -> None:
    items.sort(key=lambda d: (d.cell.z, d.cell.y, d.cell.x, d.channel, d.system_id))


def _diffusion(field: VoxelField, dt: float, ch: int, rate: float) -> list[FieldDelta]:
    k = rate * dt
    out: list[FieldDelta] = []

    def walk(c: CellCoord) -> None:
        self_v = field.sample(c, ch)

        def nb(n: CellCoord) -> float:
            return field.sample(n, ch) if _in_bounds(n) else self_v

        avg = (
            nb(CellCoord(c.x - 1, c.y, c.z))
            + nb(CellCoord(c.x + 1, c.y, c.z))
            + nb(CellCoord(c.x, c.y - 1, c.z))
            + nb(CellCoord(c.x, c.y + 1, c.z))
            + nb(CellCoord(c.x, c.y, c.z - 1))
            + nb(CellCoord(c.x, c.y, c.z + 1))
        ) / 6.0
        next_v = self_v + (avg - self_v) * k
        _push(out, FieldDelta(c, ch, self_v, next_v, 0, SYS.DIFFUSION))

    field.each_cell(walk)
    return out


def _decay(field: VoxelField, dt: float, ch: int, lam: float, system_id: int) -> list[FieldDelta]:
    factor = math.exp(-lam * dt)
    out: list[FieldDelta] = []

    def walk(c: CellCoord) -> None:
        self_v = field.sample(c, ch)
        if self_v == 0:
            return
        next_v = self_v * factor
        if next_v > self_v:
            next_v = self_v
        _push(out, FieldDelta(c, ch, self_v, next_v, 0, system_id))

    field.each_cell(walk)
    return out


def _csi_inject(field: VoxelField, obs: FieldObservation | None) -> list[FieldDelta]:
    if obs is None or not obs.valid:
        return []
    amp = 0.0
    for r in obs.regions:
        if r.name == "csi_energy":
            amp = r.observed
            break
    if amp <= 0 and obs.csi:
        amp = sum(obs.csi) / len(obs.csi)
    if amp <= 1e-6:
        return []
    peak_i = 0
    peak_v = 0.0
    for i, v in enumerate(obs.csi):
        if v > peak_v:
            peak_v = v
            peak_i = i
    denom = max(1, len(obs.csi) - 1) if obs.csi else 1
    cx = max(0, min(N - 1, round((peak_i * (N - 1)) / denom)))
    spread = 0.4
    for r in obs.regions:
        if r.name == "csi_spread":
            spread = r.observed
            break
    cz = max(0, min(N - 1, round(spread * (N - 1))))
    out: list[FieldDelta] = []
    for dz in range(-2, 3):
        for dx in range(-2, 3):
            c = CellCoord(cx + dx, 0, cz + dz)
            if not _in_bounds(c):
                continue
            w = amp * math.exp(-0.45 * (dx * dx + dz * dz))
            old = field.sample(c, Channel.Energy)
            neu = old + w * (1 - old)
            if neu > 1:
                neu = 1.0
            _push(out, FieldDelta(c, Channel.Energy, old, neu, 0, SYS.CSI_INPUT))
    return out


def seed_field() -> VoxelField:
    field = VoxelField()
    for z in range(6, 10):
        for x in range(6, 10):
            d = (x - 7.5) ** 2 + (z - 7.5) ** 2
            v = math.exp(-d * 0.35) * 0.72
            field.write(CellCoord(x, 0, z), Channel.Energy, v)
            field.write(CellCoord(x, 0, z), Channel.Temperature, v * 0.55)
    return field


@dataclass
class TickCommit:
    tick: FieldTick
    hash: str


class FieldScheduler:
    def __init__(self, field: VoxelField) -> None:
        self.field = field
        self.sequence = 0
        self.time = 0.0
        self.last: FieldTick | None = None
        self.pending_obs: FieldObservation | None = None
        self.pending_agent: list[FieldDelta] = []
        self.log: list[FieldTick] = []
        self.genesis = list(field.data)

    def bind_observation(self, obs: FieldObservation | None) -> None:
        self.pending_obs = obs

    def queue_agent_deltas(self, deltas: list[FieldDelta]) -> None:
        self.pending_agent.extend(deltas)

    def step(self, dt: float) -> TickCommit:
        view = self.field
        all_d = (
            _diffusion(view, dt, Channel.Temperature, 0.35)
            + _decay(view, dt, Channel.Information, 0.15, SYS.INFO_DECAY)
            + _decay(view, dt, Channel.Energy, 0.18, SYS.DECAY)
            + _csi_inject(view, self.pending_obs)
            + list(self.pending_agent)
        )
        self.pending_agent = []
        self.pending_obs = None

        committed: list[FieldDelta] = []
        for d in all_d:
            present = self.field.sample(d.cell, d.channel)
            if abs(present - d.old_value) > EPS:
                continue
            committed.append(FieldDelta(d.cell, d.channel, d.old_value, d.new_value, self.sequence + 1, d.system_id))
        _sort_deterministic(committed)
        self.field.apply(committed)
        self.time += dt
        self.sequence += 1
        tick = FieldTick(sequence=self.sequence, time=self.time, dt=dt, deltas=committed)
        self.last = tick
        if len(self.log) > 400:
            self.log.pop(0)
        self.log.append(tick)
        return TickCommit(tick=tick, hash=fnv1a(canonical(tick.as_dict())))

    def replay_to(self, sequence: int) -> VoxelField:
        field = VoxelField(self.genesis)
        for tick in self.log:
            if tick.sequence > sequence:
                break
            field.apply(tick.deltas)
        return field


def tick_summary(tick: FieldTick) -> dict[str, Any]:
    by_system: dict[str, int] = {}
    for d in tick.deltas:
        name = SYSTEM_NAMES.get(d.system_id, "unknown")
        by_system[name] = by_system.get(name, 0) + 1
    return {
        "sequence": tick.sequence,
        "time": tick.time,
        "delta_count": len(tick.deltas),
        "by_system": by_system,
    }
