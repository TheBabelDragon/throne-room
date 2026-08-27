# Throne Room

**Operational live Field Observer + agent-in-a-world loop for the MetaField stack.**

Two faces, one repo:

1. **Live observer** — real measurements only. CSI snake → JSONL → MetaField → Aurora → torch HUD.
2. **Agent loop** — chat as the first human actuator. PerceptionEvent → SelfState → ActionProposal → operator ABI → FieldDelta → FieldTick.

They meet at shared schemas. They do not collapse. Aurora stays fail-closed. The agent never mutates FieldTick. `act.device` is not a default capability.

```
HUMAN  ──chat──►  SELF  ──ActionProposal──►  Operator ABI  ──FieldDelta──►  FieldTick
  ▲                                                                              │
  └────────────────────────────── observe ───────────────────────────────────────┘

WORLD  ──FieldObservation──►  metafield_bridge ──JSONL──►  torch HUD
                              └── aurora.action_layer (ESCAPE sovereign)
```

See [docs/AGENT_LOOP.md](docs/AGENT_LOOP.md) for the contract.

---

## Agent loop (no hardware)

```bash
python -m agent.test_invariants
python -m agent.chat --once "What do you perceive?"
python -m agent.chat --once "Probe the energy peak"
python -m agent.chat --live --once "What do you perceive?"
python -m agent.chat --live --follow
```

`:snap` and `:step` work in the interactive REPL. Chat is an actuator — SPEAK, PROBE, REMEMBER, ATTEND are validated actions, not special cases.

Portable TypeScript twins of the same kernel: [`web/`](web/README.md).

---

## Startup walkthrough (live observer)

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
- Agent memory: `/tmp/metafield/agent_memory.jsonl`

Equivalent explicit:

```bash
python -m observer.startup --torch --action --action-mode cautious
```

Then, separately (does not bind :4210):

```bash
python -m agent.chat --live --follow
python -m agent.chat --live
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
| [docs/AGENT_LOOP.md](docs/AGENT_LOOP.md) | FieldTick · ABI · chat as actuator · Aurora mapping |
| [docs/CONTROL.md](docs/CONTROL.md) | Conductor + Aurora |
| [docs/MEASUREMENT.md](docs/MEASUREMENT.md) | Fine windows |
| [docs/SNAKE_PATH.md](docs/SNAKE_PATH.md) | CYD → host |
| [docs/METAFIELD_OBS_PATH.md](docs/METAFIELD_OBS_PATH.md) | CSI → memory |
| [docs/AURORA_ACTION.md](docs/AURORA_ACTION.md) | Action layer + escape |
| [docs/EXTRACTION_TRIBSTRUCT.md](docs/EXTRACTION_TRIBSTRUCT.md) | Cube/ensemble patterns |

Synthetic fixtures: `dev/` only — not operational. `agent/` synthetic CSI is a **loop fixture** so the ABI can be tested without the snake.

---

## Sibling repos (do not recreate here)

| Repo | Role |
|------|------|
| [self-state-kernel](https://github.com/TheBabelDragon/self-state-kernel) | Canonical SELF kernel |
| [metafield-operator-abi](https://github.com/TheBabelDragon/metafield-operator-abi) | Canonical ABI |
| [metafield-engine](https://github.com/TheBabelDragon/metafield-engine) | Canonical FieldTick engine |
| [metafield](https://github.com/TheBabelDragon/metafield) | Research / FieldMemory |
| [wifi-sensing-system](https://github.com/TheBabelDragon/wifi-sensing-system) | CSI organ |

`agent/` here is the **adapter that makes them talk** inside the live observer, not a rewrite of those repos.
