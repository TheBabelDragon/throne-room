# Fine measurement standard

History length is **rate × duration**, not a placeholder integer.

| Symbol | Default | Meaning |
|--------|---------|---------|
| `THRONE_SAMPLE_HZ` | 5 | Nominal body packet rate |
| `THRONE_WINDOW_S` | 120 | Fine analysis window (seconds) |
| `THRONE_DISPLAY_S` | 180 | Torch-display history (seconds) |
| `THRONE_SPARK_CELLS` | 48 | TUI spark width (decimated) |

Derived:

```
FINE_LEN    = ceil(SAMPLE_HZ × WINDOW_S)     # ≥64  — full-fidelity ring
DISPLAY_LEN = ceil(SAMPLE_HZ × DISPLAY_S)    # display / policy tail
```

At defaults: **600** fine samples (2 minutes @ 5 Hz), spark shows 48 decimated cells.

JSONL `memory_lines` / `csi_lines` in the digest are **uncapped file counts** — never a soft max.

Tune:

```bash
export THRONE_SAMPLE_HZ=8
export THRONE_WINDOW_S=180
python -m observer.startup
```
