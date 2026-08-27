import { canonical, fnv1a } from "./hash";

export type KernelResult = {
  ok: boolean;
  operation: string;
  value?: unknown;
  error?: string;
  trace_sequence?: number;
};

export type TraceRecord = {
  sequence: number;
  operation: string;
  target: string;
  inputs: unknown;
  output: unknown;
  state_hash: string;
};

type CommandFn = (...args: unknown[]) => unknown;

function getPath(obj: Record<string, unknown>, path: string, fallback: unknown = undefined): unknown {
  let cur: unknown = obj;
  for (const part of path.split(".")) {
    if (!cur || typeof cur !== "object" || Array.isArray(cur)) return fallback;
    cur = (cur as Record<string, unknown>)[part];
    if (cur === undefined) return fallback;
  }
  return cur;
}

function setPath(obj: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split(".");
  if (!parts.length || parts.some((p) => !p)) throw new Error(`Invalid state path: ${path}`);
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i]!;
    const next = cur[part];
    if (!next || typeof next !== "object" || Array.isArray(next)) {
      cur[part] = {};
    }
    cur = cur[part] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]!] = value;
}

export class SelfStateKernel {
  values: Record<string, unknown> = {};
  commands = new Map<string, CommandFn>();
  trace: TraceRecord[] = [];
  sequence = 0;

  constructor() {
    this.SET("kernel.version", "1112");
    this.SET("kernel.status", "READY");
    this.SET("identity.name", "SELF");
    this.SET("identity.role", "field-agent");
    this.SET("identity.continuity", "persistent-across-ticks");
    this.SET("goals", [
      {
        id: "g0",
        text: "Maintain a coherent model of the field and answer the human operator.",
        priority: 1,
      },
    ]);
    this.SET("attention.target", "chat");
    this.SET("attention.tick", 0);
    this.SET("beliefs.world", "MetaField");
    this.SET("beliefs.loop", "observe→propose→validate→commit");
    this.SET("working", {});
    this.SET("drives.coherence", 0.7);
    this.SET("drives.curiosity", 0.45);

    this.register("CMD4", () => this.cmd4());
    this.register("SNAPSHOT", () => this.snapshot());
  }

  register(name: string, fn: CommandFn) {
    this.commands.set(name.toUpperCase(), fn);
  }

  peek(path: string, fallback: unknown = undefined): unknown {
    let cur: unknown = this.values;
    for (const part of path.split(".")) {
      if (!cur || typeof cur !== "object" || Array.isArray(cur)) return fallback;
      cur = (cur as Record<string, unknown>)[part];
      if (cur === undefined) return fallback;
    }
    return cur;
  }

  snapshot(): Record<string, unknown> {
    return structuredClone(this.values);
  }

  integrity(): string {
    return fnv1a(canonical(this.values));
  }

  GET(path: string, fallback: unknown = undefined): unknown {
    const value = structuredClone(getPath(this.values, path, fallback));
    this.record("GET", path, { default: fallback }, value);
    return value;
  }

  SET(path: string, value: unknown): unknown {
    setPath(this.values, path, structuredClone(value));
    this.record("SET", path, { value }, value);
    return value;
  }

  QUERY(query: string): unknown {
    const upper = query.toUpperCase();
    if (this.commands.has(upper)) {
      const result = { type: "command", name: upper, registered: true };
      this.record("QUERY", query, {}, result);
      return result;
    }
    return this.GET(query);
  }

  RUN(command: string, ...args: unknown[]): KernelResult {
    const name = command.toUpperCase();
    const fn = this.commands.get(name);
    if (!fn) {
      const error = `Unknown command: ${name}`;
      this.record("RUN_ERROR", name, { args }, error);
      return { ok: false, operation: "RUN", error };
    }
    try {
      const value = fn(...args);
      const rec = this.record("RUN", name, { args }, value);
      return { ok: true, operation: name, value, trace_sequence: rec.sequence };
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      this.record("RUN_ERROR", name, { args }, error);
      return { ok: false, operation: name, error };
    }
  }

  IF(condition: unknown, thenCommand: string, elseCommand?: string): KernelResult {
    if (typeof condition !== "boolean") {
      const error = `IF condition must resolve to bool; received ${typeof condition}`;
      this.record("IF_ERROR", thenCommand, { condition: String(condition) }, error);
      return { ok: false, operation: "IF", error };
    }
    if (condition) return this.RUN(thenCommand);
    if (elseCommand) return this.RUN(elseCommand);
    this.record("IF_FALSE", thenCommand, {}, false);
    return { ok: true, operation: "IF", value: false };
  }

  cmd4() {
    const goals = this.values.goals;
    const attention = this.values.attention;
    return {
      command: "CMD4",
      action: "NORMAL_STATE",
      special_case: false,
      attention,
      goals,
      integrity: this.integrity(),
    };
  }

  recentTrace(limit = 12): TraceRecord[] {
    return this.trace.slice(-limit);
  }

  private record(operation: string, target: string, inputs: unknown, output: unknown): TraceRecord {
    this.sequence += 1;
    const rec: TraceRecord = {
      sequence: this.sequence,
      operation,
      target,
      inputs,
      output: safe(output),
      state_hash: this.integrity(),
    };
    this.trace.push(rec);
    if (this.trace.length > 200) this.trace.shift();
    return rec;
  }
}

function safe(value: unknown): unknown {
  try {
    JSON.stringify(value);
    return value;
  } catch {
    return String(value);
  }
}

export function createSelfState(): SelfStateKernel {
  return new SelfStateKernel();
}
