import { useEffect, useRef, useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { Button } from "./button";
import type { World } from "../src/world";
import type { WorldSnapshot } from "../src/world";
import { PIPELINE_ORDER } from "../src/schemas";
import { cn } from "./cn";

const PROMPTS = [
  "What do you perceive?",
  "Probe the energy peak",
  "Remember this field state",
  "Attend to CSI",
];

export function ChatPanel({ snap, world }: { snap: WorldSnapshot; world: World }) {
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [snap.messages.length, snap.reasoning]);

  async function send(text: string) {
    const t = text.trim();
    if (!t) return;
    setDraft("");
    await world.handleHuman(t);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(draft);
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-xl bg-surface shadow-[var(--shadow-border)]">
      <header className="flex items-center justify-between gap-3 px-4 pt-4">
        <div>
          <h2 className="text-sm font-medium tracking-wide text-muted">Human interface</h2>
          <p className="mt-0.5 text-xs text-subtle">Chat is an actuator. SPEAK is an action.</p>
        </div>
        <span className="font-mono text-xs tabular-nums text-subtle">
          {snap.provider === "live" && snap.aiAvailable ? "grok-4.5" : "mock"}
        </span>
      </header>
      <Pipeline stage={snap.pipeline} busy={snap.reasoning} />
      <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {snap.messages.map((m) => (
          <article
            key={m.id}
            className={cn(
              "max-w-[42rem] rounded-md px-3 py-2 text-sm leading-relaxed",
              m.role === "human" && "ml-auto bg-elevated text-fg",
              m.role === "agent" && "bg-bg text-fg shadow-[var(--shadow-border)]",
              m.role === "system" && "mx-auto max-w-md bg-transparent text-center text-xs text-muted",
            )}
          >
            {m.role !== "system" && (
              <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-subtle">
                {m.role === "human" ? "operator" : "self"} · t{m.tick}
              </p>
            )}
            <p>{m.text}</p>
          </article>
        ))}
        {snap.reasoning && (
          <p className="font-mono text-xs text-muted">
            Reasoning job in flight — tick clock keeps moving.
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5 px-4 pb-2">
        {PROMPTS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => void send(p)}
            disabled={snap.reasoning}
            className="h-9 rounded-sm px-3 text-xs text-muted shadow-[var(--shadow-border)] transition-colors duration-150 hover:text-fg disabled:opacity-40"
          >
            {p}
          </button>
        ))}
      </div>
      <form onSubmit={onSubmit} className="flex items-end gap-2 p-3 pt-0">
        <label className="sr-only" htmlFor="operator-input">
          Message to SELF
        </label>
        <textarea
          id="operator-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(draft);
            }
          }}
          rows={2}
          placeholder="Speak to the agent in the world…"
          className="min-h-11 flex-1 resize-none rounded-md bg-elevated px-3 py-2.5 text-sm text-fg placeholder:text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
        />
        <Button type="submit" size="icon" disabled={snap.reasoning || !draft.trim()} aria-label="Send">
          <Send className="size-4" />
        </Button>
      </form>
    </section>
  );
}

function Pipeline({ stage, busy }: { stage: WorldSnapshot["pipeline"]; busy: boolean }) {
  return (
    <ol className="mx-4 mt-3 flex flex-wrap gap-1">
      {PIPELINE_ORDER.map((s) => {
        const on = stage === s || (busy && s === "reason");
        return (
          <li
            key={s}
            className={cn(
              "rounded-sm px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors duration-150",
              on ? "bg-accent text-accent-fg" : "text-subtle",
            )}
          >
            {s}
          </li>
        );
      })}
    </ol>
  );
}
