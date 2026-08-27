import { makeProposal } from "./operator-abi";
import type { ActionProposal, ActionType } from "./schemas";

export type ReasoningContext = {
  observation_id: string;
  user_text: string;
  tick: number;
  energy_sum: number;
  info_sum: number;
  temp_sum: number;
  energy_peak: { x: number; z: number; value: number };
  csi_energy: number;
  csi_rssi: number;
  integrity: string;
  goals: string[];
  attention: string;
  memories: string[];
};

export type ReasonResult =
  | { ok: true; proposal: ActionProposal; provider: "mock" | "live" }
  | { ok: false; error: string; proposal: ActionProposal; provider: "mock" | "live" };

export function mockReason(ctx: ReasoningContext): ActionProposal {
  const text = ctx.user_text.toLowerCase();
  const peak = `${ctx.energy_peak.x},${ctx.energy_peak.z}`;

  if (/\b(probe|inject|nudge|excite|perturb)\b/.test(text)) {
    return makeProposal({
      action_type: "PROBE",
      parameters: { x: ctx.energy_peak.x, z: ctx.energy_peak.z, magnitude: 0.55 },
      target: peak,
      rationale: "Operator asked for an active probe at the current energy peak.",
      confidence: 0.86,
      originating_observation: ctx.observation_id,
    });
  }
  if (/\b(remember|memor(y|ise|ize)|note this|store)\b/.test(text)) {
    const note = `Tick ${ctx.tick}: energy ${ctx.energy_sum.toFixed(2)}, CSI ${ctx.csi_energy.toFixed(2)}. ${ctx.user_text}`;
    return makeProposal({
      action_type: "REMEMBER",
      parameters: { note },
      target: "memory",
      rationale: "Operator asked to retain the current field state.",
      confidence: 0.9,
      originating_observation: ctx.observation_id,
    });
  }
  if (/\b(goal|objective|priority)\b/.test(text)) {
    return makeProposal({
      action_type: "SET_GOAL",
      parameters: { text: ctx.user_text.replace(/^.*?(goal|objective)\s*(is|:)?\s*/i, "").trim() || ctx.user_text },
      target: "goals",
      rationale: "Operator updated goals.",
      confidence: 0.8,
      originating_observation: ctx.observation_id,
    });
  }
  if (/\b(attend|look at|focus|watch)\b/.test(text)) {
    const target = /\bcsi\b/.test(text) ? "csi" : /\bchat\b/.test(text) ? "chat" : "field";
    return makeProposal({
      action_type: "ATTEND",
      parameters: { target },
      target,
      rationale: "Shifted attention as requested.",
      confidence: 0.84,
      originating_observation: ctx.observation_id,
    });
  }

  const memories = ctx.memories.length ? ctx.memories.slice(0, 2).join(" / ") : "none yet";
  const reply =
    `Tick ${ctx.tick}. I am SELF — agency without authority. ` +
    `Energy Σ ${ctx.energy_sum.toFixed(2)} (peak ${peak} = ${ctx.energy_peak.value.toFixed(2)}), ` +
    `information Σ ${ctx.info_sum.toFixed(2)}, CSI energy ${ctx.csi_energy.toFixed(2)} @ ${ctx.csi_rssi.toFixed(1)} dBm. ` +
    `Attention on ${ctx.attention}. Integrity ${ctx.integrity}. ` +
    `Recent memory: ${memories}. ` +
    `I can SPEAK, PROBE, REMEMBER, ATTEND — never mutate FieldTick directly.`;

  return makeProposal({
    action_type: "SPEAK",
    parameters: { text: reply },
    target: "chat",
    rationale: "Language is the first actuator. Report the observed field.",
    confidence: 0.78,
    originating_observation: ctx.observation_id,
  });
}

export const REASON_SYSTEM = `You are SELF, the agent in the MetaField world kernel.
You do not own the world. You observe FieldTick, then propose one ActionProposal.
The operator ABI validates. The engine commits FieldDelta. You never mutate FieldTick.

Return ONLY a JSON object:
{
  "action_type": "SPEAK" | "PROBE" | "REMEMBER" | "ATTEND" | "SET_GOAL" | "QUERY_FIELD" | "WAIT",
  "parameters": {},
  "target": "string",
  "rationale": "short",
  "confidence": 0.0
}

Rules:
- SPEAK: parameters.text is the utterance to the human. Default action for questions.
- PROBE: parameters.x, parameters.z, parameters.magnitude (0-1). Injects energy. Use only if asked to probe/perturb.
- REMEMBER: parameters.note. Use if asked to remember.
- ATTEND: parameters.target (chat|field|csi).
- SET_GOAL: parameters.text.
- Be concise. SPEAK text ≤ 80 words. No markdown. No emoji.
- You are not a chatbot bolted on. Chat is simply the language actuator.`;

export function parseProposal(raw: string, ctx: ReasoningContext): ActionProposal | null {
  const trimmed = raw.trim();
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const obj = JSON.parse(trimmed.slice(start, end + 1)) as {
      action_type?: string;
      parameters?: Record<string, unknown>;
      target?: string;
      rationale?: string;
      confidence?: number;
    };
    const action_type = (obj.action_type ?? "SPEAK").toUpperCase() as ActionType;
    return makeProposal({
      action_type: (
        ["SPEAK", "PROBE", "REMEMBER", "ATTEND", "SET_GOAL", "QUERY_FIELD", "WAIT"] as string[]
      ).includes(action_type)
        ? action_type
        : "SPEAK",
      parameters: { text: trimmed.slice(0, 400), ...sanitizeParams(obj.parameters) },
      target: obj.target ?? "chat",
      rationale: obj.rationale ?? "",
      confidence: typeof obj.confidence === "number" ? obj.confidence : 0.6,
      originating_observation: ctx.observation_id,
    });
  } catch {
    return null;
  }
}

function sanitizeParams(raw: unknown): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  if (!raw || typeof raw !== "object") return out;
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") out[k] = v;
    else if (v != null) out[k] = String(v);
  }
  return out;
}
