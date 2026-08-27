export const SCHEMA = {
  tick: "metafield.tick",
  delta: "metafield.delta",
  observation: "metafield.observation",
  perception: "metafield.perception",
  proposal: "metafield.action_proposal",
  action: "metafield.action",
  memory: "metafield.memory",
} as const;

export const SCHEMA_VERSION = 1;

export const Channel = {
  Matter: 0,
  Energy: 1,
  Temperature: 2,
  Pressure: 3,
  Charge: 4,
  MomentumX: 5,
  MomentumY: 6,
  MomentumZ: 7,
  Entropy: 8,
  Information: 9,
} as const;

export type ChannelId = (typeof Channel)[keyof typeof Channel];

export const CHANNEL_COUNT = 10;
export const CHANNEL_NAMES = [
  "matter",
  "energy",
  "temperature",
  "pressure",
  "charge",
  "momentum_x",
  "momentum_y",
  "momentum_z",
  "entropy",
  "information",
] as const;

export type ChannelName = (typeof CHANNEL_NAMES)[number];

export function channelName(id: ChannelId): ChannelName {
  return CHANNEL_NAMES[id] ?? "energy";
}

export function channelFromName(name: string): ChannelId {
  const i = CHANNEL_NAMES.indexOf(name as ChannelName);
  return (i >= 0 ? i : Channel.Energy) as ChannelId;
}

export const SYS = {
  DIFFUSION: 1,
  INFO_DECAY: 2,
  ADVECTION: 3,
  CSI_INPUT: 4,
  DECAY: 5,
  AGENT: 6,
} as const;

export function systemName(id: number): string {
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

export type CellCoord = { x: number; y: number; z: number };

export type FieldDelta = {
  cell: CellCoord;
  channel: ChannelId;
  old_value: number;
  new_value: number;
  tick: number;
  system_id: number;
};

export type FieldTick = {
  schema: typeof SCHEMA.tick;
  version: number;
  sequence: number;
  time: number;
  dt: number;
  deltas: FieldDelta[];
};

export type FieldRegion = {
  name: string;
  observed: number;
  confidence: number;
};

export type FieldObservation = {
  body_id: string;
  body_type: string;
  timestamp: string;
  regions: FieldRegion[];
  csi: number[];
  rssi_dbm: number;
  synthetic: boolean;
  valid: boolean;
};

export type PerceptionEvent = {
  schema: typeof SCHEMA.perception;
  version: number;
  id: string;
  source: string;
  timestamp: string;
  tick: number;
  modality: "language" | "csi" | "optical" | "ultrasonic" | "hall" | "internal";
  coordinates?: CellCoord;
  features: Record<string, number | string>;
  confidence: number;
};

export const ACTION_TYPES = [
  "SPEAK",
  "PROBE",
  "REMEMBER",
  "ATTEND",
  "SET_GOAL",
  "QUERY_FIELD",
  "WAIT",
] as const;

export type ActionType = (typeof ACTION_TYPES)[number];

export type ActionProposal = {
  schema: typeof SCHEMA.proposal;
  version: number;
  proposal_id: string;
  action_type: ActionType;
  parameters: Record<string, string | number | boolean>;
  target: string;
  rationale: string;
  confidence: number;
  originating_observation: string;
  agent_id: string;
  capability: string;
};

export type CommittedAction = {
  schema: typeof SCHEMA.action;
  version: number;
  agent_id: string;
  capability: string;
  observation_id: string;
  proposal_id: string;
  tick: number;
  action_type: ActionType;
  accepted: boolean;
  reason: string;
  resulting_delta_count: number;
};

export type Capability =
  | "observe.field"
  | "observe.history"
  | "act.field"
  | "act.device"
  | "communicate"
  | "remember";

export const DEFAULT_CAPABILITIES: Capability[] = [
  "observe.field",
  "observe.history",
  "act.field",
  "communicate",
  "remember",
];

export const ACTION_CAPABILITY: Record<ActionType, Capability> = {
  SPEAK: "communicate",
  PROBE: "act.field",
  REMEMBER: "remember",
  ATTEND: "observe.field",
  SET_GOAL: "remember",
  QUERY_FIELD: "observe.field",
  WAIT: "observe.field",
};

export type MemoryEntry = {
  schema: typeof SCHEMA.memory;
  version: number;
  id: string;
  tick: number;
  kind: "episodic" | "semantic" | "working";
  text: string;
  tags: string[];
  observation_id?: string;
  created_at: number;
};

export type ChatRole = "human" | "agent" | "system";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  tick: number;
  proposal_id?: string;
  observation_id?: string;
};

export type PipelineStage =
  | "idle"
  | "perceive"
  | "self"
  | "reason"
  | "propose"
  | "validate"
  | "commit"
  | "observe";

export const PIPELINE_ORDER: PipelineStage[] = [
  "perceive",
  "self",
  "reason",
  "propose",
  "validate",
  "commit",
  "observe",
];
