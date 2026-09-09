"""Write a recoverable nightly report from the desks, then you can sleep."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DESK = Path("/tmp/metafield")
REPORT = DESK / "QWUACK_NIGHTLY.md"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pnp_rows = _read_jsonl(DESK / "qwuack_pnp.jsonl")
    env = _read_jsonl(DESK / "qwuack_envelope.jsonl")
    pnp_state = _load(DESK / "qwuack_pnp_state.json")
    col_state = _load(DESK / "qwuack_desk_state.json")

    two = [r for r in pnp_rows if r.get("name") == "two_sat_solver"]
    greedy = [r for r in pnp_rows if r.get("name") == "greedy_3sat_poly_claim"]
    two_ok = sum(1 for r in two if r.get("status") == "VERIFIED")
    two_bad = sum(1 for r in two if r.get("status") != "VERIFIED")
    greedy_ref = [r for r in greedy if r.get("status") == "REFUTED"]
    worst_env = max(env, key=lambda r: int(r.get("worst_stopping") or 0), default=None)
    last_env = env[-1] if env else None
    seeds = []
    for r in greedy_ref:
        seed = (r.get("evidence") or {}).get("counterexample_seed")
        if seed is not None:
            seeds.append(seed)

    lines = [
        f"# Qwuack nightly  {ts}",
        "",
        "Not a Millennium proof. Named finite computations only.",
        "",
        "## P vs NP desk",
        "",
        "Rejected once and dropped:",
        "",
        "- `P=NP` — unbounded, not an experiment",
        "- `P!=NP` — unbounded, not an experiment",
        "",
        f"- 2SAT implication-SCC vs brute: VERIFIED {two_ok} batch(es), REFUTED {two_bad}",
        f"- greedy-majority 3SAT ‘poly’ claim: REFUTED {len(greedy_ref)} / {len(greedy)} batches",
        f"- last n2={pnp_state.get('n2')} n3={pnp_state.get('n3')} gen={pnp_state.get('generation')}",
        "",
    ]
    if seeds:
        lines.append(f"First greedy counterexample seeds: `{seeds[:8]}`")
        lines.append("")
        last = greedy_ref[-1]
        ev = last.get("evidence") or {}
        lines.append(
            f"Last attack: n={ev.get('n')} misses={ev.get('misses')} "
            f"seed={ev.get('counterexample_seed')} trials={ev.get('trials')}"
        )
        lines.append("")
    lines += [
        "Claim you may keep: on each named (n, seed, trials) batch, the 2SAT solver",
        "matched brute force, and the greedy 3SAT rule missed satisfiable formulas.",
        "",
        "Claim you may not keep: P vs NP is settled.",
        "",
        "## Collatz desk",
        "",
    ]
    if last_env:
        lines.append(
            f"- last window `{last_env.get('lo')}..{last_env.get('hi')}` "
            f"worst n={last_env.get('worst_n')} st={last_env.get('worst_stopping')}"
        )
    if worst_env:
        lines.append(
            f"- hardest window `{worst_env.get('lo')}..{worst_env.get('hi')}` "
            f"n={worst_env.get('worst_n')} st={worst_env.get('worst_stopping')}"
        )
    if col_state:
        lines.append(
            f"- state gen={col_state.get('generation')} "
            f"horizon={col_state.get('horizon')} window_start={col_state.get('window_start')}"
        )
    lines += [
        "",
        "Claim you may keep: every named checked window terminated under this implementation.",
        "Claim you may not keep: Collatz is proved.",
        "",
        "## Files",
        "",
        "- `/tmp/metafield/qwuack_pnp.jsonl`",
        "- `/tmp/metafield/qwuack_envelope.jsonl`",
        "- `/tmp/metafield/qwuack_pnp_state.json`",
        "- `/tmp/metafield/qwuack_desk_state.json`",
        "",
        "Reproduce 2SAT / greedy from the seeds in the PNP journal.",
        "Independent checker still required before calling a window certain.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    DESK.mkdir(parents=True, exist_ok=True)
    text = build()
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
