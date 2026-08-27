import {
  CHANNEL_COUNT,
  Channel,
  SCHEMA,
  SCHEMA_VERSION,
  SYS,
  type ChannelId,
  type CellCoord,
  type FieldDelta,
  type FieldObservation,
  type FieldTick,
} from "./schemas";
import { canonical, fnv1a } from "./hash";

export const N = 16;
const EPS = 1e-5;

function idx(x: number, y: number, z: number, ch: ChannelId): number {
  return ((z * N + y) * N + x) * CHANNEL_COUNT + ch;
}

function inBounds(c: CellCoord): boolean {
  return c.x >= 0 && c.x < N && c.y >= 0 && c.y < N && c.z >= 0 && c.z < N;
}

export class VoxelField {
  data: Float32Array;

  constructor(source?: Float32Array) {
    this.data = source ? Float32Array.from(source) : new Float32Array(N * N * N * CHANNEL_COUNT);
  }

  clone(): VoxelField {
    return new VoxelField(this.data);
  }

  sample(c: CellCoord, ch: ChannelId): number {
    if (!inBounds(c)) return 0;
    return this.data[idx(c.x, c.y, c.z, ch)] ?? 0;
  }

  write(c: CellCoord, ch: ChannelId, v: number) {
    if (!inBounds(c)) return;
    this.data[idx(c.x, c.y, c.z, ch)] = v;
  }

  apply(deltas: FieldDelta[]) {
    for (const d of deltas) this.write(d.cell, d.channel, d.new_value);
  }

  eachCell(fn: (c: CellCoord) => void) {
    const y = 0;
    for (let z = 0; z < N; z++) {
      for (let x = 0; x < N; x++) fn({ x, y, z });
    }
  }

  slice2d(ch: ChannelId): number[] {
    const out = new Array<number>(N * N);
    for (let z = 0; z < N; z++) {
      for (let x = 0; x < N; x++) {
        out[z * N + x] = this.sample({ x, y: 0, z }, ch);
      }
    }
    return out;
  }

  sum(ch: ChannelId): number {
    let s = 0;
    this.eachCell((c) => {
      s += this.sample(c, ch);
    });
    return s;
  }

  peak(ch: ChannelId): { cell: CellCoord; value: number } {
    let best: { cell: CellCoord; value: number } = { cell: { x: 8, y: 0, z: 8 }, value: 0 };
    this.eachCell((c) => {
      const v = this.sample(c, ch);
      if (v > best.value) best = { cell: c, value: v };
    });
    return best;
  }
}

function pushDelta(out: FieldDelta[], d: FieldDelta) {
  if (Math.abs(d.new_value - d.old_value) < 1e-8) return;
  out.push(d);
}

function sortDeterministic(items: FieldDelta[]) {
  items.sort((a, b) => {
    if (a.cell.z !== b.cell.z) return a.cell.z - b.cell.z;
    if (a.cell.y !== b.cell.y) return a.cell.y - b.cell.y;
    if (a.cell.x !== b.cell.x) return a.cell.x - b.cell.x;
    if (a.channel !== b.channel) return a.channel - b.channel;
    return a.system_id - b.system_id;
  });
}

function diffusion(field: VoxelField, dt: number, ch: ChannelId, rate: number): FieldDelta[] {
  const k = rate * dt;
  const out: FieldDelta[] = [];
  field.eachCell((c) => {
    const self = field.sample(c, ch);
    const nb = (n: CellCoord) => (inBounds(n) ? field.sample(n, ch) : self);
    const avg =
      (nb({ x: c.x - 1, y: c.y, z: c.z }) +
        nb({ x: c.x + 1, y: c.y, z: c.z }) +
        nb({ x: c.x, y: c.y - 1, z: c.z }) +
        nb({ x: c.x, y: c.y + 1, z: c.z }) +
        nb({ x: c.x, y: c.y, z: c.z - 1 }) +
        nb({ x: c.x, y: c.y, z: c.z + 1 })) /
      6;
    const next = self + (avg - self) * k;
    pushDelta(out, {
      cell: c,
      channel: ch,
      old_value: self,
      new_value: next,
      tick: 0,
      system_id: SYS.DIFFUSION,
    });
  });
  return out;
}

function decay(field: VoxelField, dt: number, ch: ChannelId, lambda: number, system_id: number): FieldDelta[] {
  const factor = Math.exp(-lambda * dt);
  const out: FieldDelta[] = [];
  field.eachCell((c) => {
    const self = field.sample(c, ch);
    if (self === 0) return;
    let next = self * factor;
    if (next > self) next = self;
    pushDelta(out, {
      cell: c,
      channel: ch,
      old_value: self,
      new_value: next,
      tick: 0,
      system_id,
    });
  });
  return out;
}

function csiInject(field: VoxelField, obs: FieldObservation | null): FieldDelta[] {
  if (!obs?.valid) return [];
  let amp = obs.regions.find((r) => r.name === "csi_energy")?.observed ?? 0;
  if (amp <= 0 && obs.csi.length) {
    amp = obs.csi.reduce((s, v) => s + v, 0) / obs.csi.length;
  }
  if (amp <= 1e-6) return [];
  let peak = 0;
  let pv = 0;
  for (let i = 0; i < obs.csi.length; i++) {
    if (obs.csi[i]! > pv) {
      pv = obs.csi[i]!;
      peak = i;
    }
  }
  const denom = Math.max(1, obs.csi.length - 1);
  const cx = Math.max(0, Math.min(N - 1, Math.round((peak * (N - 1)) / denom)));
  const spread = obs.regions.find((r) => r.name === "csi_spread")?.observed ?? 0.4;
  const cz = Math.max(0, Math.min(N - 1, Math.round(spread * (N - 1))));
  const out: FieldDelta[] = [];
  for (let dz = -2; dz <= 2; dz++) {
    for (let dx = -2; dx <= 2; dx++) {
      const c = { x: cx + dx, y: 0, z: cz + dz };
      if (!inBounds(c)) continue;
      const w = amp * Math.exp(-0.45 * (dx * dx + dz * dz));
      const old = field.sample(c, Channel.Energy);
      let neu = old + w * (1 - old);
      if (neu > 1) neu = 1;
      pushDelta(out, {
        cell: c,
        channel: Channel.Energy,
        old_value: old,
        new_value: neu,
        tick: 0,
        system_id: SYS.CSI_INPUT,
      });
    }
  }
  return out;
}

export function seedField(): VoxelField {
  const field = new VoxelField();
  for (let z = 6; z <= 9; z++) {
    for (let x = 6; x <= 9; x++) {
      const d = (x - 7.5) * (x - 7.5) + (z - 7.5) * (z - 7.5);
      const v = Math.exp(-d * 0.35) * 0.72;
      field.write({ x, y: 0, z }, Channel.Energy, v);
      field.write({ x, y: 0, z }, Channel.Temperature, v * 0.55);
    }
  }
  return field;
}

export type TickCommit = {
  tick: FieldTick;
  hash: string;
};

export class FieldScheduler {
  field: VoxelField;
  sequence = 0;
  time = 0;
  last: FieldTick | null = null;
  pendingObs: FieldObservation | null = null;
  pendingAgent: FieldDelta[] = [];
  log: FieldTick[] = [];
  genesis: Float32Array;

  constructor(field: VoxelField) {
    this.field = field;
    this.genesis = Float32Array.from(field.data);
  }

  bindObservation(obs: FieldObservation | null) {
    this.pendingObs = obs;
  }

  queueAgentDeltas(deltas: FieldDelta[]) {
    this.pendingAgent.push(...deltas);
  }

  step(dt: number): TickCommit {
    const view = this.field;
    const all: FieldDelta[] = [
      ...diffusion(view, dt, Channel.Temperature, 0.35),
      ...decay(view, dt, Channel.Information, 0.15, SYS.INFO_DECAY),
      ...decay(view, dt, Channel.Energy, 0.18, SYS.DECAY),
      ...csiInject(view, this.pendingObs),
      ...this.pendingAgent,
    ];
    this.pendingAgent = [];
    this.pendingObs = null;

    const committed: FieldDelta[] = [];
    for (const d of all) {
      const present = this.field.sample(d.cell, d.channel);
      if (Math.abs(present - d.old_value) > EPS) continue;
      committed.push({ ...d, tick: this.sequence + 1 });
    }
    sortDeterministic(committed);
    this.field.apply(committed);
    this.time += dt;
    this.sequence += 1;
    const tick: FieldTick = {
      schema: SCHEMA.tick,
      version: SCHEMA_VERSION,
      sequence: this.sequence,
      time: this.time,
      dt,
      deltas: committed,
    };
    this.last = tick;
    if (this.log.length > 400) this.log.shift();
    this.log.push(tick);
    return { tick, hash: fnv1a(canonical(tick)) };
  }

  replayTo(sequence: number): VoxelField {
    const field = new VoxelField(this.genesis);
    for (const tick of this.log) {
      if (tick.sequence > sequence) break;
      field.apply(tick.deltas);
    }
    return field;
  }
}

export function tickSummary(tick: FieldTick) {
  const bySystem: Record<string, number> = {};
  for (const d of tick.deltas) {
    const n = systemNameSafe(d.system_id);
    bySystem[n] = (bySystem[n] ?? 0) + 1;
  }
  return {
    sequence: tick.sequence,
    time: tick.time,
    delta_count: tick.deltas.length,
    by_system: bySystem,
  };
}

function systemNameSafe(id: number): string {
  switch (id) {
    case 1:
      return "diffusion";
    case 2:
      return "information_decay";
    case 3:
      return "advection";
    case 4:
      return "csi";
    case 5:
      return "decay";
    case 6:
      return "agent";
    default:
      return "unknown";
  }
}
