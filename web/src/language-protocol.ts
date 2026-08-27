/** Language-arm protocol twin. No model lives here. */

export type ConversationEvent = {
  schema: "metafield.conversation_event";
  version: number;
  role: "user" | "arm" | "system";
  text: string;
  tick: number;
  tokens: number[] | null;
};

export type MemoryReference = {
  schema: "metafield.memory_reference";
  version: number;
  id: string;
  tick: number;
  text: string;
  kind: string;
};

export type ParticipantObservation = {
  schema: "metafield.participant_observation";
  version: number;
  tick: number;
  energy_sum: number;
  info_sum: number;
  temp_sum: number;
  energy_peak: { x: number; z: number; value: number };
  csi_energy: number;
  csi_rssi: number;
  integrity: string;
  body_id: string | null;
  permitted: string[];
};

export type LanguageContext = {
  schema: "metafield.language_context";
  version: number;
  observation_id: string;
  user_text: string;
  observation: ParticipantObservation;
  conversation: ConversationEvent[];
  memories: MemoryReference[];
  goals: string[];
  attention: string;
  capabilities: string[];
};

export type LanguageOutput = {
  schema: "metafield.language_output";
  version: number;
  tokens: number[];
  text: string;
  source: "model" | "teacher";
  tokenizer_version: string;
  model_version: string;
  prompt_tokens: number[];
  confidence: number;
  predicted_action: string;
  abstained: boolean;
};
