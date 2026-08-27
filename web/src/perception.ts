import type { FieldObservation, PerceptionEvent } from "./schemas";
import { SCHEMA, SCHEMA_VERSION } from "./schemas";
import { uid } from "./hash";

export function makeSyntheticCsi(tick: number, body = "synthetic_cyd"): FieldObservation {
  const t = tick * 0.08;
  const rssi = -58 + 8 * Math.sin(t * 0.35);
  const csi: number[] = [];
  for (let i = 0; i < 32; i++) {
    const k = i / 31;
    let v =
      0.35 +
      0.25 * Math.sin(t + k * 6.28) +
      0.12 * Math.sin(t * 2.2 + k * 12) +
      0.05 * Math.sin(t * 7 + i);
    if (v < 0) v = 0;
    if (v > 1) v = 1;
    csi.push(v);
  }
  let sum = 0;
  let sq = 0;
  let peak = 0;
  for (const v of csi) {
    sum += v;
    sq += v * v;
    if (v > peak) peak = v;
  }
  const n = 32;
  const mean = sum / n;
  const energy = Math.sqrt(sq / n);
  let variance = 0;
  for (const v of csi) {
    const d = v - mean;
    variance += d * d;
  }
  const spread = Math.sqrt(variance / n);
  const rssi_n = Math.max(0, Math.min(1, (rssi + 90) / 60));
  return {
    body_id: body,
    body_type: "wifi_csi",
    timestamp: String(tick),
    synthetic: true,
    valid: true,
    rssi_dbm: rssi,
    csi,
    regions: [
      { name: "rssi", observed: rssi_n, confidence: 0.4 },
      { name: "csi_mean", observed: mean, confidence: 0.4 },
      { name: "csi_peak", observed: peak, confidence: 0.4 },
      { name: "csi_energy", observed: energy, confidence: 0.4 },
      { name: "csi_spread", observed: Math.min(1, spread * 2), confidence: 0.4 },
    ],
  };
}

export function observationToPerception(obs: FieldObservation, tick: number): PerceptionEvent {
  const energy = obs.regions.find((r) => r.name === "csi_energy")?.observed ?? 0;
  return {
    schema: SCHEMA.perception,
    version: SCHEMA_VERSION,
    id: uid("obs"),
    source: obs.body_id,
    timestamp: obs.timestamp,
    tick,
    modality: "csi",
    features: {
      rssi_dbm: obs.rssi_dbm,
      energy,
      mean: obs.regions.find((r) => r.name === "csi_mean")?.observed ?? 0,
      peak: obs.regions.find((r) => r.name === "csi_peak")?.observed ?? 0,
      spread: obs.regions.find((r) => r.name === "csi_spread")?.observed ?? 0,
    },
    confidence: 0.4,
  };
}

export function chatPerception(text: string, tick: number): PerceptionEvent {
  return {
    schema: SCHEMA.perception,
    version: SCHEMA_VERSION,
    id: uid("obs"),
    source: "throne-room",
    timestamp: new Date().toISOString(),
    tick,
    modality: "language",
    features: { text },
    confidence: 1,
  };
}
