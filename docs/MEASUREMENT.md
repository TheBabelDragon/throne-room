# Fine measurement standard

History length is **rate × duration**, not a placeholder integer.
Never a 179-style memory cap — rings are full fine windows only.

## Pre-tuned defaults

| Symbol | Default | Meaning |
|--------|---------|---------|
| `THRONE_SAMPLE_HZ` | **8** | Nominal CSI body rate |
| `THRONE_WINDOW_S` | **90** | Fine analysis window (seconds) |
| `THRONE_DISPLAY_S` | **150** | Torch-display history (seconds) |
| `THRONE_SPARK_CELLS` | **64** | TUI spark width (decimated) |
| `THRONE_FIELD_HEADS` | **8** | Multi-head CSI band split |
| `THRONE_FIELD_SC` | **32** | Subcarriers used per packet |

Derived:

```
FINE_LEN    = ceil(8 × 90)  = 720 samples   # full-fidelity ring
DISPLAY_LEN = ceil(8 × 150) = 1200 samples
```

JSONL `memory_lines` / `csi_lines` in the digest are **uncapped live file counts**.

## Multi-head field (substance only)

`observer/multi_head_field.py`:

- split CSI into `FIELD_HEADS` contiguous bands
- per-head mean / energy / spread / peak
- soft routing weights + routing entropy
- fused scalars for Aurora / torch head features

## Field head (both hands)

`visualization/field_head.py` — ON by default:

- **both hands equal** — mean 0.40 + energy 0.40 base (no mean-skew)
- **no slope-to-start** — first real sample seeds EMA; residual quiet until window filled
- multi-head entropy modulates surprise threshold only
- optional torch checkpoint upgrade at `/tmp/metafield/throne_head.pt`

## Tune

```bash
export THRONE_SAMPLE_HZ=10
export THRONE_WINDOW_S=120
export THRONE_FIELD_HEADS=8
python -m observer.startup --full
```
