# Throne Room

**Operational live Field Observer + closed-loop spatial HUD for the MetaField stack.**

Real measurements only. CSI snake → JSONL → MetaField → Aurora → torch HUD.

---

## Startup walkthrough

### 0. Once

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/TheBabelDragon/throne-room.git
cd throne-room
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

MetaField sibling (memory promote):

```bash
# git clone https://github.com/TheBabelDragon/metafield.git ~/projects/metafield
export METAFIELD_ROOT=~/projects/metafield   # optional; auto-discovers ../metafield
```

### 1. Bring the snake online

Power CYD CSI senders + bridge ESP32s so UDP packets reach the host on **:4210**.

Only **one** process may bind 4210 (the conductor’s `metafield_bridge`).

### 2. Launch the full stack (recommended)

```bash
cd ~/projects/throne-room
source .venv/bin/activate
git pull

python -m observer.startup --full
```

`--full` starts:

| Child | Role |
|-------|------|
| `metafield_bridge` | UDP :4210 → `/tmp/metafield/csi.jsonl` (required) |
| `throne_view` | Rich TUI battleship sparks |
| `torch_display` | Closed-loop HUD @ ~36 Hz (CSI · body map · dynamics · Aurora) |
| `metafield_consumer` | FO → FieldMemory if MetaField found |
| `aurora_action` | Policy intents + Redis escape (cautious) |
| digest loop | health · field_pressure · host_guard every 2.5 s |

Paths:

- Digest: `/tmp/metafield/obs_digest.json`
- Actions: `/tmp/metafield/aurora_actions.jsonl`
- Escape: Redis `aurora:control:escape`

Equivalent explicit:

```bash
python -m observer.startup --torch --action --action-mode cautious
```

### 3. Torch only

```bash
python -m visualization.torch_display
python -m visualization.torch_display --file /tmp/metafield/csi.jsonl --hz 40 --size 64
# disable head if needed:
python -m visualization.torch_display --no-head
```

### 4. Stop

`Ctrl+C` on the conductor — all children terminate cleanly.

---

## Spatial intelligence HUD

Torch is the closed-loop face of the field:

| Panel | Content |
|-------|---------|
| 1 · CSI | Subcarrier bars |
| 2 · body energy | Multi-scale Gaussian map + action flash |
| 3 · dynamics | mean · energy · spread · pressure · pred · residual + Aurora marks |
| 4 · Aurora | host · children · loop chip · head state · intents |

**Field head** is ON by default (`OnlineFieldHead`):

- both hands equal (mean 0.40 + energy 0.40) — no mean-skew
- no slope-to-start — first sample seeds EMA, residual quiet until real window
- multi-head entropy modulates surprise threshold only
- optional torch checkpoint at `/tmp/metafield/throne_head.pt` auto-upgrades

---

## Measurement defaults (pre-tuned — not placeholders)

| Param | Value |
|-------|-------|
| Sample rate | 8 Hz |
| Fine window | 90 s → **720** samples (`FINE_LEN`) |
| Display | 150 s → **1200** samples (`DISPLAY_LEN`) |
| Spark cells | 64 (decimated) |
| Field heads | 8 |
| Torch UI | ~36 Hz |

Rings never use a small placeholder cap. Override: `THRONE_SAMPLE_HZ`, `THRONE_WINDOW_S`, `THRONE_TORCH=1`.

---

## View-only / debug

```bash
python run.py --file /tmp/metafield/csi.jsonl --from-start
# raw UDP only if bridge is NOT running
python run.py --udp
```

---

## Docs

| Doc | Content |
|-----|---------|
| [docs/CONTROL.md](docs/CONTROL.md) | Conductor + Aurora |
| [docs/MEASUREMENT.md](docs/MEASUREMENT.md) | Fine windows |
| [docs/SNAKE_PATH.md](docs/SNAKE_PATH.md) | CYD → host |
| [docs/METAFIELD_OBS_PATH.md](docs/METAFIELD_OBS_PATH.md) | CSI → memory |
| [docs/AURORA_ACTION.md](docs/AURORA_ACTION.md) | Action layer + escape |
| [docs/EXTRACTION_TRIBSTRUCT.md](docs/EXTRACTION_TRIBSTRUCT.md) | Cube/ensemble patterns |

Synthetic fixtures: `dev/` only — not operational.
