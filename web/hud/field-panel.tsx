import type { WorldSnapshot } from "../src/world";

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function energyColor(e: number, info: number): string {
  const t = Math.max(0, Math.min(1, e));
  let r: number, g: number, b: number;
  if (t < 0.55) {
    const u = t / 0.55;
    r = lerp(17, 184, u);
    g = lerp(19, 196, u);
    b = lerp(21, 188, u);
  } else {
    const u = (t - 0.55) / 0.45;
    r = lerp(184, 236, u);
    g = lerp(196, 234, u);
    b = lerp(188, 225, u);
  }
  if (info > 0.08) {
    r = lerp(r, 236, info * 0.45);
    g = lerp(g, 234, info * 0.45);
    b = lerp(b, 225, info * 0.45);
  }
  return `rgb(${r | 0} ${g | 0} ${b | 0})`;
}

export function FieldPanel({ snap }: { snap: WorldSnapshot }) {
  const n = snap.n;
  const peakIndex = snap.energyPeak.z * n + snap.energyPeak.x;

  return (
    <section className="flex h-full min-h-0 flex-col gap-3 rounded-xl bg-surface p-3 shadow-[var(--shadow-border)] md:p-4">
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium tracking-wide text-muted">FieldTick</h2>
        <p className="font-mono text-xs tabular-nums text-subtle">
          ΣE {snap.energySum.toFixed(2)} · ΣI {snap.infoSum.toFixed(2)} · {snap.deltaCount} Δ
        </p>
      </header>
      <div
        className="aspect-square w-full overflow-hidden rounded-md bg-elevated p-1"
        role="img"
        aria-label="Energy lattice"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`,
          gap: 1,
        }}
      >
        {snap.energy.map((e, i) => (
          <div
            key={i}
            title={`${i % n},${Math.floor(i / n)} e=${e.toFixed(2)}`}
            className={i === peakIndex ? "outline outline-1 outline-fg/50" : undefined}
            style={{ backgroundColor: energyColor(e, snap.information[i] ?? 0), minHeight: 4 }}
          />
        ))}
      </div>
      <CsiBars values={snap.csi} rssi={snap.rssi} energy={snap.csiEnergy} />
      <p className="font-mono text-xs text-subtle">
        peak {snap.energyPeak.x},{snap.energyPeak.z} · {snap.energyPeak.value.toFixed(2)} · CSI {snap.csiEnergy.toFixed(2)} @{" "}
        {snap.rssi.toFixed(1)} dBm
      </p>
    </section>
  );
}

function CsiBars({ values, rssi, energy }: { values: number[]; rssi: number; energy: number }) {
  const bars = values.length ? values : Array.from({ length: 32 }, () => 0);
  return (
    <div className="flex h-14 items-end gap-px rounded-sm bg-elevated px-1 py-1" aria-label="CSI subcarriers">
      {bars.map((v, i) => (
        <div
          key={i}
          className="min-w-0 flex-1 rounded-[1px] bg-accent"
          style={{ height: `${Math.max(6, Math.min(100, v * 100))}%`, opacity: 0.35 + v * 0.65 }}
        />
      ))}
      <span className="sr-only">
        RSSI {rssi.toFixed(1)} dBm, energy {energy.toFixed(2)}
      </span>
    </div>
  );
}
