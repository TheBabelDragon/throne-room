import { Channel, type ChatMessage, type PerceptionEvent, type PipelineStage } from "./schemas";
import { FieldScheduler, N, seedField, tickSummary, type VoxelField } from "./engine";
import { createSelfState, type SelfStateKernel, type TraceRecord } from "./self-state";
import { OperatorAbi, type AbiDecision } from "./operator-abi";
import { MemoryStore } from "./memory";
import { chatPerception, makeSyntheticCsi, observationToPerception } from "./perception";
import { mockReason, type ReasoningContext } from "./reasoning";
import type { ActionProposal, Capability, FieldObservation, FieldTick } from "./schemas";

export type WorldSnapshot = {
  sequence: number;
  time: number;
  dt: number;
  running: boolean;
  energy: number[];
  information: number[];
  temperature: number[];
  energySum: number;
  infoSum: number;
  tempSum: number;
  energyPeak: { x: number; z: number; value: number };
  csi: number[];
  rssi: number;
  csiEnergy: number;
  integrity: string;
  status: string;
  attention: string;
  goals: { id: string; text: string; priority: number }[];
  identity: string;
  capabilities: Capability[];
  messages: ChatMessage[];
  pipeline: PipelineStage;
  lastTick: FieldTick | null;
  lastDecision: AbiDecision | null;
  lastProposal: ActionProposal | null;
  lastPerception: PerceptionEvent | null;
  trace: TraceRecord[];
  memories: { id: string; tick: number; text: string; kind: string }[];
  tickHash: string;
  provider: "mock" | "live";
  aiAvailable: boolean;
  reasoning: boolean;
  n: number;
  deltaCount: number;
  bySystem: Record<string, number>;
};

const DT = 0.125;

export class World {
  scheduler: FieldScheduler;
  self: SelfStateKernel;
  abi: OperatorAbi;
  memory: MemoryStore;
  messages: ChatMessage[] = [];
  pipeline: PipelineStage = "idle";
  lastDecision: AbiDecision | null = null;
  lastProposal: ActionProposal | null = null;
  lastPerception: PerceptionEvent | null = null;
  lastObs: FieldObservation | null = null;
  lastHash = "00000000";
  running = true;
  provider: "mock" | "live" = "mock";
  aiAvailable = false;
  reasoning = false;
  liveReason: ((
    ctx: ReasoningContext,
  ) => Promise<{ ok: boolean; proposal: ActionProposal; provider: "mock" | "live"; error?: string }>) | null = null;
  listeners = new Set<() => void>();
  cached: WorldSnapshot;

  constructor() {
    this.scheduler = new FieldScheduler(seedField());
    this.self = createSelfState();
    this.abi = new OperatorAbi();
    this.memory = new MemoryStore();
    this.messages.push({
      id: "sys_0",
      role: "system",
      text: "Loop locked. You speak. SELF perceives. ABI validates. Engine commits. Chat is an actuator.",
      tick: 0,
    });
    this.cached = this.buildSnapshot();
  }

  on(fn: () => void) {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private emit() {
    this.cached = this.buildSnapshot();
    for (const fn of this.listeners) fn();
  }

  snapshot(): WorldSnapshot {
    return this.cached;
  }

  hydrateMemory() {
    this.memory.load();
    this.emit();
  }

  buildSnapshot(): WorldSnapshot {
    const field = this.scheduler.field;
    const peak = field.peak(Channel.Energy);
    const tick = this.scheduler.last;
    const summary = tick ? tickSummary(tick) : { delta_count: 0, by_system: {} };
    const goals = (this.self.peek("goals") as { id: string; text: string; priority: number }[]) ?? [];
    return {
      sequence: this.scheduler.sequence,
      time: this.scheduler.time,
      dt: DT,
      running: this.running,
      energy: field.slice2d(Channel.Energy),
      information: field.slice2d(Channel.Information),
      temperature: field.slice2d(Channel.Temperature),
      energySum: field.sum(Channel.Energy),
      infoSum: field.sum(Channel.Information),
      tempSum: field.sum(Channel.Temperature),
      energyPeak: { x: peak.cell.x, z: peak.cell.z, value: peak.value },
      csi: this.lastObs?.csi ?? [],
      rssi: this.lastObs?.rssi_dbm ?? -90,
      csiEnergy: Number(this.lastObs?.regions.find((r) => r.name === "csi_energy")?.observed ?? 0),
      integrity: this.self.integrity(),
      status: String(this.self.peek("kernel.status") ?? "READY"),
      attention: String(this.self.peek("attention.target") ?? "chat"),
      goals,
      identity: String(this.self.peek("identity.name") ?? "SELF"),
      capabilities: [...this.abi.capabilities],
      messages: this.messages.slice(-40),
      pipeline: this.pipeline,
      lastTick: tick,
      lastDecision: this.lastDecision,
      lastProposal: this.lastProposal,
      lastPerception: this.lastPerception,
      trace: this.self.recentTrace(10),
      memories: this.memory.recent(6).map((m) => ({
        id: m.id,
        tick: m.tick,
        text: m.text,
        kind: m.kind,
      })),
      tickHash: this.lastHash,
      provider: this.provider,
      aiAvailable: this.aiAvailable,
      reasoning: this.reasoning,
      n: N,
      deltaCount: summary.delta_count,
      bySystem: summary.by_system,
    };
  }

  setRunning(v: boolean) {
    this.running = v;
    this.emit();
  }

  setProvider(p: "mock" | "live") {
    this.provider = p;
    this.emit();
  }

  setAiAvailable(v: boolean) {
    this.aiAvailable = v;
    if (!v && this.provider === "live") this.provider = "mock";
    this.emit();
  }

  toggleCapability(cap: Capability) {
    if (this.abi.has(cap)) this.abi.revoke(cap);
    else this.abi.grant(cap);
    this.emit();
  }

  step() {
    const nextSeq = this.scheduler.sequence + 1;
    const obs = makeSyntheticCsi(nextSeq);
    this.lastObs = obs;
    this.scheduler.bindObservation(obs);
    const { tick, hash } = this.scheduler.step(DT);
    this.lastHash = hash;
    if (tick.sequence % 8 === 0) {
      const perc = observationToPerception(obs, tick.sequence);
      this.self.SET("working.last_csi", {
        energy: perc.features.energy,
        rssi: perc.features.rssi_dbm,
        tick: tick.sequence,
      });
    }
    this.emit();
    return tick;
  }

  replayField(sequence: number): VoxelField {
    return this.scheduler.replayTo(sequence);
  }

  reset() {
    this.scheduler = new FieldScheduler(seedField());
    this.self = createSelfState();
    this.lastDecision = null;
    this.lastProposal = null;
    this.lastPerception = null;
    this.lastObs = null;
    this.lastHash = "00000000";
    this.pipeline = "idle";
    this.messages = [
      {
        id: "sys_reset",
        role: "system",
        text: "World reset. Genesis field reseeding. Continuity of SELF identity preserved in name only.",
        tick: 0,
      },
    ];
    this.emit();
  }

  async handleHuman(text: string) {
    const trimmed = text.trim();
    if (!trimmed || this.reasoning) return;
    const tick = this.scheduler.sequence;
    const perception = chatPerception(trimmed, tick);
    this.lastPerception = perception;
    this.pipeline = "perceive";
    this.messages.push({
      id: perception.id,
      role: "human",
      text: trimmed,
      tick,
      observation_id: perception.id,
    });
    this.emit();

    this.pipeline = "self";
    this.self.SET("working.last_utterance", trimmed);
    this.self.SET("attention.target", "chat");
    this.memory.append({
      tick,
      text: `human: ${trimmed}`,
      kind: "episodic",
      tags: ["chat", "human"],
      observation_id: perception.id,
    });
    this.emit();

    this.pipeline = "reason";
    this.reasoning = true;
    this.emit();

    const ctx = this.reasoningContext(perception.id, trimmed);
    let proposal: ActionProposal;
    let provider: "mock" | "live" = "mock";
    // Live LLM is a host concern (outside FieldTick). Default: mock.
    proposal = mockReason(ctx);
    provider = "mock";
    if (this.provider === "live" && this.aiAvailable && this.liveReason) {
      const result = await this.liveReason(ctx);
      proposal = result.proposal;
      provider = result.provider;
      if (!result.ok) {
        this.messages.push({
          id: `sys_${tick}_fallback`,
          role: "system",
          text: `Live reasoner unavailable (${result.error}). Mock provider filled the job.`,
          tick,
        });
      }
    }
    this.lastProposal = proposal;
    this.pipeline = "propose";
    this.reasoning = false;
    this.emit();

    this.pipeline = "validate";
    const decision = this.abi.validate(proposal, this.scheduler.field, this.scheduler.sequence + 1);
    this.lastDecision = decision;
    this.emit();

    this.pipeline = "commit";
    if (decision.accepted && decision.deltas.length) {
      this.scheduler.queueAgentDeltas(decision.deltas);
    }
    if (decision.accepted && decision.memoryNote) {
      this.memory.append({
        tick: this.scheduler.sequence,
        text: decision.memoryNote,
        kind: "episodic",
        tags: ["remember", "agent"],
        observation_id: perception.id,
      });
    }
    if (decision.accepted && decision.attend) {
      this.self.SET("attention.target", decision.attend);
    }
    if (decision.accepted && decision.goal) {
      const goals = (this.self.GET("goals") as { id: string; text: string; priority: number }[]) ?? [];
      goals.push({ id: `g${goals.length}`, text: decision.goal, priority: 1 });
      this.self.SET("goals", goals);
    }
    if (decision.accepted && decision.utterance) {
      this.messages.push({
        id: decision.action.proposal_id,
        role: "agent",
        text: decision.utterance,
        tick: this.scheduler.sequence,
        proposal_id: proposal.proposal_id,
        observation_id: perception.id,
      });
    } else if (!decision.accepted) {
      this.messages.push({
        id: `rej_${proposal.proposal_id}`,
        role: "system",
        text: `ABI rejected ${proposal.action_type}: ${decision.reason}`,
        tick: this.scheduler.sequence,
        proposal_id: proposal.proposal_id,
      });
    } else if (decision.accepted && proposal.action_type !== "SPEAK") {
      this.messages.push({
        id: decision.action.proposal_id,
        role: "agent",
        text: `${proposal.action_type} committed. ${decision.reason}`,
        tick: this.scheduler.sequence,
        proposal_id: proposal.proposal_id,
        observation_id: perception.id,
      });
    }

    this.self.SET("working.last_action", {
      type: proposal.action_type,
      accepted: decision.accepted,
      provider,
    });

    this.step();
    this.pipeline = "observe";
    this.emit();
    const done = () => {
      this.pipeline = "idle";
      this.emit();
    };
    if (typeof window !== "undefined") window.setTimeout(done, 700);
    else done();
  }

  private reasoningContext(observation_id: string, user_text: string): ReasoningContext {
    const field = this.scheduler.field;
    const peak = field.peak(Channel.Energy);
    const goals = (this.self.peek("goals") as { text: string }[]) ?? [];
    return {
      observation_id,
      user_text,
      tick: this.scheduler.sequence,
      energy_sum: field.sum(Channel.Energy),
      info_sum: field.sum(Channel.Information),
      temp_sum: field.sum(Channel.Temperature),
      energy_peak: { x: peak.cell.x, z: peak.cell.z, value: peak.value },
      csi_energy: Number(this.lastObs?.regions.find((r) => r.name === "csi_energy")?.observed ?? 0),
      csi_rssi: this.lastObs?.rssi_dbm ?? -90,
      integrity: this.self.integrity(),
      goals: goals.map((g) => g.text),
      attention: String(this.self.peek("attention.target") ?? "chat"),
      memories: this.memory.recent(4).map((m) => m.text),
    };
  }
}

let singleton: World | null = null;

export function getWorld(): World {
  if (!singleton) singleton = new World();
  return singleton;
}
