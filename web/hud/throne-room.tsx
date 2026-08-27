import { useState } from "react";
import { IconPause, IconPlay, IconReset } from "./icons";
import { Button } from "./button";
import { ChatPanel } from "./chat-panel";
import { FieldPanel } from "./field-panel";
import { SelfPanel } from "./self-panel";
import { useWorld } from "./use-world";
import { formatTick } from "../src/hash";
import { cn } from "./cn";

type Tab = "chat" | "field" | "self";

export function ThroneRoom() {
  const { snap, world } = useWorld();
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <div className="flex h-dvh min-h-dvh flex-col overflow-hidden bg-bg text-fg">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 md:px-6">
        <div className="min-w-0 shrink-0 sm:flex-1">
          <p className="whitespace-nowrap font-mono text-[10px] uppercase tracking-[0.16em] text-subtle">
            MetaField · operator
          </p>
          <h1 className="text-xl font-medium tracking-[-0.03em] md:text-2xl">Throne Room</h1>
        </div>
        <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs tabular-nums text-muted">
          <div>
            <dt className="sr-only">Tick</dt>
            <dd>t{formatTick(snap.sequence)}</dd>
          </div>
          <div>
            <dt className="sr-only">Time</dt>
            <dd>{snap.time.toFixed(2)}s</dd>
          </div>
          <div className="hidden sm:block">
            <dt className="sr-only">Hash</dt>
            <dd className="text-subtle">{snap.tickHash}</dd>
          </div>
        </dl>
        <div className="flex items-center gap-1">
          <Button
            variant="subtle"
            size="icon"
            aria-label={snap.running ? "Pause field" : "Run field"}
            onClick={() => world.setRunning(!snap.running)}
          >
            {snap.running ? <IconPause className="size-4" /> : <IconPlay className="ml-px size-4" />}
          </Button>
          <Button variant="ghost" size="icon" aria-label="Reset world" onClick={() => world.reset()}>
            <IconReset className="size-4" />
          </Button>
          <Button
            variant={snap.provider === "live" ? "primary" : "outline"}
            size="sm"
            onClick={() => world.setProvider(snap.provider === "live" ? "mock" : "live")}
            className="hidden sm:inline-flex"
          >
            {snap.aiAvailable && snap.provider === "live" ? "Live reasoner" : "Mock reasoner"}
          </Button>
        </div>
      </header>

      <nav className="flex gap-1 border-b border-border px-3 py-2 lg:hidden" aria-label="Panels">
        {(["chat", "field", "self"] as Tab[]).map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "h-11 flex-1 rounded-sm text-sm capitalize",
              tab === id ? "bg-elevated text-fg" : "text-muted",
            )}
          >
            {id === "self" ? "SELF" : id}
          </button>
        ))}
      </nav>

      <main className="mx-auto grid min-h-0 w-full max-w-[1600px] flex-1 grid-cols-1 gap-3 overflow-hidden p-3 md:gap-4 md:p-4 lg:grid-cols-[minmax(16rem,0.9fr)_minmax(0,1.2fr)_minmax(18rem,0.85fr)]">
        <div className={cn("min-h-0", tab === "field" ? "block" : "hidden", "lg:block")}>
          <FieldPanel snap={snap} />
        </div>
        <div className={cn("min-h-[24rem] lg:min-h-0", tab === "chat" ? "flex" : "hidden", "lg:flex")}>
          <ChatPanel snap={snap} world={world} />
        </div>
        <div className={cn("min-h-0 overflow-y-auto", tab === "self" ? "block" : "hidden", "lg:block")}>
          <SelfPanel snap={snap} world={world} />
        </div>
      </main>
    </div>
  );
}
