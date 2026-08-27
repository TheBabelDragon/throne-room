import { SCHEMA, SCHEMA_VERSION, type MemoryEntry } from "./schemas";
import { uid } from "./hash";

const KEY = "throne.memory.v1";

export class MemoryStore {
  entries: MemoryEntry[] = [];

  constructor() {}

  append(input: { tick: number; text: string; kind?: MemoryEntry["kind"]; tags?: string[]; observation_id?: string }) {
    const entry: MemoryEntry = {
      schema: SCHEMA.memory,
      version: SCHEMA_VERSION,
      id: uid("mem"),
      tick: input.tick,
      kind: input.kind ?? "episodic",
      text: input.text,
      tags: input.tags ?? [],
      observation_id: input.observation_id,
      created_at: Date.now(),
    };
    this.entries.push(entry);
    if (this.entries.length > 200) this.entries.shift();
    this.persist();
    return entry;
  }

  retrieve(query: string, limit = 6): MemoryEntry[] {
    const q = query.trim().toLowerCase();
    if (!q) return this.entries.slice(-limit);
    const scored = this.entries
      .map((e) => {
        const hay = `${e.text} ${e.tags.join(" ")}`.toLowerCase();
        let score = 0;
        for (const token of q.split(/\s+/)) if (hay.includes(token)) score += 1;
        return { e, score };
      })
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score || b.e.tick - a.e.tick);
    return (scored.length ? scored.map((s) => s.e) : this.entries.slice(-limit)).slice(0, limit);
  }

  associate(a: string, b: string, tick: number) {
    return this.append({
      tick,
      kind: "semantic",
      text: `${a} ↔ ${b}`,
      tags: ["associate", a, b],
    });
  }

  consolidate(tick: number) {
    const recent = this.entries.slice(-8);
    if (!recent.length) return null;
    const text = recent.map((e) => e.text).join(" · ").slice(0, 280);
    return this.append({ tick, kind: "semantic", text, tags: ["consolidate"] });
  }

  forget(id: string) {
    this.entries = this.entries.filter((e) => e.id !== id);
    this.persist();
  }

  recent(limit = 8) {
    return this.entries.slice(-limit).reverse();
  }

  private persist() {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(KEY, JSON.stringify(this.entries));
    } catch {
      /* ignore quota */
    }
  }

  load() {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as MemoryEntry[];
      if (Array.isArray(parsed)) this.entries = parsed.slice(-200);
    } catch {
      this.entries = [];
    }
  }
}
