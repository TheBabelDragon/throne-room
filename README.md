# Throne Room

**Operational live Field Observer + intelligent control for the MetaField stack.**

Real measurements only. CSI snake → JSONL → MetaField → Aurora.

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
# GUI HUD (recommended):
pip install matplotlib numpy
```

MetaField sibling (memory promote):

```bash
# if not already present
# git clone https://github.com/TheBabelDragon/metafield.git ~/projects/metafield
export METAFIELD_ROOT=~/projects/metafield   # optional; auto-discovers ../metafield
```

### 1. Bring the snake online

Power CYD CSI senders + bridge ESP32s so UDP packets reach the host on **:4210**.

Only **one** process may bind 4210 (the conductor’s `metafield_bridge`).

### 2. Launch the full stack (recommended)

One command brings up bridge + throne view + torch HUD + Aurora action + MetaField consumer:

```bash
cd ~/projects/throne-room
source .venv/bin/activate
git pull

python -m observer.startup --full
```

`--full` is shorthand for:

- `metafield_bridge` (required, UDP :4210 → JSONL)
- `throne_view` (Rich TUI battleship sparks)
- `torch_display` (matplotlib live HUD @ ~36 Hz)
- `aurora_action` (cautious mode, Redis escape when available)
- `metafield_consumer` (if MetaField root found)

Equivalent explicit form:

```bash
python -m observer.startup --torch --action --action-mode cautious
```

What starts:

| Child | Role |
|-------|------|
| `metafield_bridge` | UDP :4210 → `/tmp/metafield/csi.jsonl` (required) |
| `throne_view` | Rich TUI battleship sparks |
| `torch_display` | Live 4-panel HUD: CSI · body energy map · dynamics · Aurora/host |
| `metafield_consumer` | FO → FieldMemory JSONL if MetaField found |
| `aurora_action` | Policy intents + Redis control plane (optional) |
| digest loop | health · field_pressure · host_guard every 2.5 s |

Digest: `/tmp/metafield/obs_digest.json`  
Actions journal: `/tmp/metafield/aurora_actions.jsonl`  
Escape key (Redis): `aurora:control:escape`

### 3. Torch only / second terminal

```bash
python -m visualization.torch_display
# or force file / higher rate:
python -m visualization.torch_display --file /tmp/metafield/csi.jsonl --hz 40 --size 64
```

### 4. Stop

`Ctrl+C` on the conductor — all children terminate cleanly.

---

## View-only / debug

```bash
python run.py --file /tmp/metafield/csi.jsonl --from-start
# raw UDP only if bridge is NOT running
python run.py --udp
```

---

## Measurement defaults (pre-tuned)

| Param | Value |
|-------|-------|
| Sample rate | 8 Hz |
| Fine window | 90 s → **720** samples |
| Display | 150 s → **1200** samples |
| Spark cells | 64 (decimated) |
| Field heads | 8 |
| Torch UI | ~36 Hz live dynamics |

Override: `THRONE_SAMPLE_HZ`, `THRONE_WINDOW_S`, `THRONE_TORCH=1`, …

---

## Docs

| Doc | Content |
|-----|---------|
| [docs/CONTROL.md](docs/CONTROL.md) | Conductor + Aurora |
| [docs/MEASUREMENT.md](docs/MEASUREMENT.md) | Fine windows |
| [docs/SNAKE_PATH.md](docs/SNAKE_PATH.md) | CYD → host |
| [docs/METAFIELD_OBS_PATH.md](docs/METAFIELD_OBS_PATH.md) | CSI → memory |
| [docs/EXTRACTION_TRIBSTRUCT.md](docs/EXTRACTION_TRIBSTRUCT.md) | Cube/ensemble patterns kept |

Synthetic fixtures: `dev/` only — not operational.
