import {
  ACTION_CAPABILITY,
  ACTION_TYPES,
  Channel,
  DEFAULT_CAPABILITIES,
  SCHEMA,
  SCHEMA_VERSION,
  SYS,
  type ActionProposal,
  type ActionType,
  type Capability,
  type CellCoord,
  type CommittedAction,
  type FieldDelta,
} from "./schemas";
import { uid } from "./hash";
import type { VoxelField } from "./engine";
import { N } from "./engine";

export type AbiDecision = {
  accepted: boolean;
  reason: string;
  proposal: ActionProposal;
  action: CommittedAction;
  deltas: FieldDelta[];
  utterance?: string;
  memoryNote?: string;
  attend?: string;
  goal?: string;
  query?: string;
};

export class OperatorAbi {
  capabilities: Set<Capability>;
  agentId: string;

  constructor(agentId = "self-0", capabilities: Capability[] = DEFAULT_CAPABILITIES) {
    this.agentId = agentId;
    this.capabilities = new Set(capabilities);
  }

  has(cap: Capability) {
    return this.capabilities.has(cap);
  }

  grant(cap: Capability) {
    this.capabilities.add(cap);
  }

  revoke(cap: Capability) {
    this.capabilities.delete(cap);
  }

  validate(proposal: ActionProposal, field: VoxelField, tick: number): AbiDecision {
    const capability = ACTION_CAPABILITY[proposal.action_type] ?? "observe.field";
    const baseAction = (accepted: boolean, reason: string, deltas: FieldDelta[] = []): CommittedAction => ({
      schema: SCHEMA.action,
      version: SCHEMA_VERSION,
      agent_id: this.agentId,
      capability,
      observation_id: proposal.originating_observation,
      proposal_id: proposal.proposal_id,
      tick,
      action_type: proposal.action_type,
      accepted,
      reason,
      resulting_delta_count: deltas.length,
    });

    if (!ACTION_TYPES.includes(proposal.action_type)) {
      const action = baseAction(false, `Unknown action_type: ${proposal.action_type}`);
      return { accepted: false, reason: action.reason, proposal, action, deltas: [] };
    }

    if (!this.has(capability)) {
      const action = baseAction(false, `Missing capability: ${capability}`);
      return { accepted: false, reason: action.reason, proposal, action, deltas: [] };
    }

    switch (proposal.action_type) {
      case "SPEAK": {
        const text = String(proposal.parameters.text ?? "").trim();
        if (!text) {
          const action = baseAction(false, "SPEAK requires parameters.text");
          return { accepted: false, reason: action.reason, proposal, action, deltas: [] };
        }
        const cell = clampCell(proposal.target, field);
        const old = field.sample(cell, Channel.Information);
        let next = old + 0.35 * (1 - old);
        if (next > 1) next = 1;
        const deltas: FieldDelta[] = [
          {
            cell,
            channel: Channel.Information,
            old_value: old,
            new_value: next,
            tick,
            system_id: SYS.AGENT,
          },
        ];
        const action = baseAction(true, "committed SPEAK", deltas);
        return { accepted: true, reason: action.reason, proposal, action, deltas, utterance: text.slice(0, 2000) };
      }
      case "PROBE": {
        const magnitude = clamp01(Number(proposal.parameters.magnitude ?? 0.45));
        const cell = clampCell(proposal.target, field, proposal.parameters);
        const old = field.sample(cell, Channel.Energy);
        let next = old + magnitude * (1 - old);
        if (next > 1) next = 1;
        const deltas: FieldDelta[] = [];
        for (let dz = -1; dz <= 1; dz++) {
          for (let dx = -1; dx <= 1; dx++) {
            const c = { x: cell.x + dx, y: 0, z: cell.z + dz };
            if (c.x < 0 || c.x >= N || c.z < 0 || c.z >= N) continue;
            const o = field.sample(c, Channel.Energy);
            const w = magnitude * Math.exp(-0.7 * (dx * dx + dz * dz));
            let n = o + w * (1 - o);
            if (n > 1) n = 1;
            deltas.push({
              cell: c,
              channel: Channel.Energy,
              old_value: o,
              new_value: n,
              tick,
              system_id: SYS.AGENT,
            });
          }
        }
        const action = baseAction(true, `committed PROBE @ ${cell.x},${cell.z}`, deltas);
        return { accepted: true, reason: action.reason, proposal, action, deltas };
      }
      case "REMEMBER": {
        const note = String(proposal.parameters.note ?? proposal.rationale ?? "").trim();
        if (!note) {
          const action = baseAction(false, "REMEMBER requires parameters.note");
          return { accepted: false, reason: action.reason, proposal, action, deltas: [] };
        }
        const action = baseAction(true, "committed REMEMBER");
        return { accepted: true, reason: action.reason, proposal, action, deltas: [], memoryNote: note };
      }
      case "ATTEND": {
        const target = String(proposal.parameters.target ?? proposal.target ?? "field").trim();
        const action = baseAction(true, `committed ATTEND ${target}`);
        return { accepted: true, reason: action.reason, proposal, action, deltas: [], attend: target };
      }
      case "SET_GOAL": {
        const text = String(proposal.parameters.text ?? "").trim();
        if (!text) {
          const action = baseAction(false, "SET_GOAL requires parameters.text");
          return { accepted: false, reason: action.reason, proposal, action, deltas: [] };
        }
        const action = baseAction(true, "committed SET_GOAL");
        return { accepted: true, reason: action.reason, proposal, action, deltas: [], goal: text };
      }
      case "QUERY_FIELD": {
        const action = baseAction(true, "committed QUERY_FIELD");
        return { accepted: true, reason: action.reason, proposal, action, deltas: [], query: "field" };
      }
      case "WAIT": {
        const action = baseAction(true, "committed WAIT");
        return { accepted: true, reason: action.reason, proposal, action, deltas: [] };
      }
    }
  }
}

function clamp01(n: number) {
  if (!Number.isFinite(n)) return 0.4;
  return Math.max(0.05, Math.min(0.95, n));
}

function clampCell(
  target: string,
  field: VoxelField,
  params?: Record<string, string | number | boolean>,
): CellCoord {
  const px = Number(params?.x);
  const pz = Number(params?.z ?? params?.y);
  if (Number.isFinite(px) && Number.isFinite(pz)) {
    return {
      x: Math.max(0, Math.min(N - 1, Math.round(px))),
      y: 0,
      z: Math.max(0, Math.min(N - 1, Math.round(pz))),
    };
  }
  const m = /^(\d+)\s*,\s*(\d+)/.exec(target);
  if (m) {
    return {
      x: Math.max(0, Math.min(N - 1, Number(m[1]))),
      y: 0,
      z: Math.max(0, Math.min(N - 1, Number(m[2]))),
    };
  }
  const peak = field.peak(Channel.Energy);
  return peak.cell;
}

export function makeProposal(
  partial: Omit<ActionProposal, "schema" | "version" | "proposal_id" | "agent_id" | "capability"> & {
    agent_id?: string;
  },
): ActionProposal {
  const action_type = partial.action_type;
  return {
    schema: SCHEMA.proposal,
    version: SCHEMA_VERSION,
    proposal_id: uid("prp"),
    agent_id: partial.agent_id ?? "self-0",
    capability: ACTION_CAPABILITY[action_type],
    action_type,
    parameters: partial.parameters,
    target: partial.target,
    rationale: partial.rationale,
    confidence: partial.confidence,
    originating_observation: partial.originating_observation,
  };
}
