import { DEFAULT_CAPABILITIES, type Capability } from "../src/schemas";
import { REPOS } from "../src/repos";
import type { World, WorldSnapshot } from "../src/world";
import { cn } from "./cn";

const ALL_CAPS: Capability[] = [...DEFAULT_CAPABILITIES, "act.device"];

export function SelfPanel({ snap, world }: { snap: WorldSnapshot; world: World }) {
  const proposal = snap.lastProposal;
  const decision = snap.lastDecision;

  return (
    <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto">
      <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
        <h2 className="text-sm font-medium tracking-wide text-muted">SELF</h2>
        <dl className="mt-3 space-y-2 font-mono text-xs">
          <Row label="identity" value={snap.identity} />
          <Row label="status" value={snap.status} />
          <Row label="attention" value={snap.attention} />
          <Row label="integrity" value={snap.integrity} mono />
        </dl>
        <div className="mt-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-subtle">Goals</p>
          <ul className="mt-2 space-y-1.5">
            {snap.goals.map((g) => (
              <li key={g.id} className="text-sm leading-snug text-fg">
                {g.text}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
        <h2 className="text-sm font-medium tracking-wide text-muted">Operator ABI</h2>
        <p className="mt-1 text-xs text-subtle">Capabilities are data. Agent proposes; engine commits.</p>
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {ALL_CAPS.map((cap) => {
            const on = snap.capabilities.includes(cap);
            return (
              <li key={cap}>
                <button
                  type="button"
                  onClick={() => world.toggleCapability(cap)}
                  className={cn(
                    "h-9 rounded-sm px-3 font-mono text-[11px] transition-colors duration-150",
                    on ? "bg-elevated text-fg" : "text-subtle line-through",
                  )}
                >
                  {cap}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
        <h2 className="text-sm font-medium tracking-wide text-muted">Last proposal</h2>
        {proposal ? (
          <div className="mt-3 space-y-2">
            <p className="font-mono text-xs text-accent">
              {proposal.action_type}
              {decision ? (decision.accepted ? " · accepted" : " · rejected") : ""}
            </p>
            <p className="text-sm leading-relaxed text-fg">{proposal.rationale || "—"}</p>
            <pre className="overflow-x-auto rounded-sm bg-bg p-3 font-mono text-[11px] leading-relaxed text-muted">
              {JSON.stringify(
                {
                  schema: proposal.schema,
                  action_type: proposal.action_type,
                  parameters: proposal.parameters,
                  capability: proposal.capability,
                  confidence: proposal.confidence,
                  proposal_id: proposal.proposal_id,
                },
                null,
                2,
              )}
            </pre>
          </div>
        ) : (
          <p className="mt-3 text-sm text-subtle">No proposal yet. Speak to start the loop.</p>
        )}
      </section>

      <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
        <h2 className="text-sm font-medium tracking-wide text-muted">Memory</h2>
        <ul className="mt-3 space-y-2">
          {snap.memories.length === 0 && <li className="text-sm text-subtle">Empty store.</li>}
          {snap.memories.map((m) => (
            <li key={m.id} className="text-sm leading-snug text-fg">
              <span className="font-mono text-[10px] text-subtle">t{m.tick} · {m.kind}</span>
              <p className="text-muted">{m.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
        <h2 className="text-sm font-medium tracking-wide text-muted">Trace</h2>
        <ol className="mt-3 space-y-1 font-mono text-[11px] text-muted">
          {snap.trace.slice().reverse().map((t) => (
            <li key={t.sequence}>
              [{String(t.sequence).padStart(4, "0")}] {t.operation} {t.target}
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
        <h2 className="text-sm font-medium tracking-wide text-muted">Repos</h2>
        <ul className="mt-3 space-y-2">
          {REPOS.map((r) => (
            <li key={r.name} className="flex items-start justify-between gap-2">
              <div>
                <p className="font-mono text-xs text-fg">{r.name}</p>
                <p className="text-xs text-subtle">{r.role}</p>
              </div>
              <span className={cn("font-mono text-[10px] uppercase tracking-[0.14em]", r.live ? "text-ok" : "text-subtle")}>
                {r.live ? "in loop" : "organ"}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-subtle">{label}</dt>
      <dd className={cn("truncate text-fg", mono && "tracking-tight")}>{value}</dd>
    </div>
  );
}
