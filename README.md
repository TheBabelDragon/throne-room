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

`:snap` `:step` `:status` `:arm` work in the interactive REPL. Chat is an actuator — SPEAK, PROBE, REMEMBER, ATTEND, QUERY_FIELD, WAIT are validated actions, not special cases. The arm's voice is `compose()` over the field, not a chatbot.

Local language arm (no API):

```bash
pip install torch    # optional decoder; numpy stays the default
python -m agent.language.harness
python -m agent.language.train --examples 64 --steps 40
python -m agent.language.torch_train --examples 64 --steps 16
python -m agent.chat --arm teacher --once "What do you perceive?"
python -m agent.chat --arm model --once "Probe the energy peak"
python -m agent.chat --arm model --backend torch --learn
```
See [docs/LANGUAGE_ARM.md](docs/LANGUAGE_ARM.md). Tokenizer and protocol are owned here. Numpy trains a fastText action head (no torch required). `python -m agent.language.torch_train` backprops through decoder blocks. `compose()` is the operator voice — genesis tokens do not invent field numbers. `--learn` does one imitation step per turn from the teacher label.

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

REPL commands: `:snap` `:drain` `:status` `:q`. The prompt no longer blocks CSI ingest — backlog is drained while you sit at `operator>`. Bridge logs: `/tmp/metafield/bridge.log`. Conductor prints `csi_stale` if `/tmp/metafield/csi.jsonl` stops growing.

`--ticks` is a **count** (offline synthetic warmup). The journal path is `--journal` (default `/tmp/metafield/agent_ticks.jsonl`). Do not pass a file to `--ticks`.

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
| [docs/LANGUAGE_ARM.md](docs/LANGUAGE_ARM.md) | Local language arm protocol · tokenizer · trajectories |
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
| [metafield-operator-abi](https://github.com/TheBabelDragon/metafield-operator-abi) | Canonical operator ABI (Wilson–Dirac frozen) |
| [metafield-engine](https://github.com/TheBabelDragon/metafield-engine) | Canonical FieldTick / ECS engine |
| [metafield](https://github.com/TheBabelDragon/metafield) | Research / FieldMemory / QCD lab |
| [metafield-work](https://github.com/TheBabelDragon/metafield-work) | Operator isolation workbench |
| [wifi-sensing-system](https://github.com/TheBabelDragon/wifi-sensing-system) | CSI organ |
| [optical-body-s3](https://github.com/TheBabelDragon/optical-body-s3) | Laser + BPW34 body |
| [echo-grid-ultrasonic-os](https://github.com/TheBabelDragon/echo-grid-ultrasonic-os) | Ultrasonic array OS |
| [hall-node-s3](https://github.com/TheBabelDragon/hall-node-s3) | Hall-array edge node |
| [field-bus](https://github.com/TheBabelDragon/field-bus) | CAN / CAN-FD for field nodes |
| [BabelBus](https://github.com/TheBabelDragon/BabelBus) | HDMI-CSI video bus (transport, not semantics) |
| [arty-realtime](https://github.com/TheBabelDragon/arty-realtime) | Fast physical loop vs slow model loop |
| [aurora-swarm-btc](https://github.com/TheBabelDragon/aurora-swarm-btc) | Swarm compute fabric |
| [aurora-coordination](https://github.com/TheBabelDragon/aurora-coordination) | Private Overlord / ESCAPE |
| [zvs-node](https://github.com/TheBabelDragon/zvs-node) | Private ZVS / ultrasonic power stage |

`agent/` here is the **adapter that makes them talk** inside the live observer, not a rewrite of those repos.

---

## Multi-window layout (operator desk)

Clone once:

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/TheBabelDragon/throne-room.git
git clone https://github.com/TheBabelDragon/metafield.git          # optional FieldMemory
# engine / ABI / SELF stay sibling-canonical; throne-room adapters them, does not vendor them
cd throne-room && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pip install torch   # optional language-arm decoder. numpy stays the default.
```

Two desks. Same venv. Same `/tmp/metafield` journals.

### A · no hardware (language arm)

| Window | Directory | Command | Looking at |
|--------|-----------|---------|------------|
| A1 · invariants | `~/projects/throne-room` | `python -m agent.test_invariants` | FieldTick replay, ABI, arm. Torch tests skip if torch is missing. |
| A2 · numpy train | same | `python -m agent.language.train --examples 64 --steps 40` | fastText action head. Writes `/tmp/metafield/arm_dec_v0.npz`. |
| A3 · torch train | same | `python -m agent.language.torch_train --examples 64 --steps 16` | Decoder blocks + action head. Writes `/tmp/metafield/arm_gpt_v0.pt`. |
| A4 · teacher REPL | same | `python -m agent.chat --arm teacher` | Structured policy. `compose()` is the voice. `:snap` `:arm` `:q` |
| A5 · model REPL | same | `python -m agent.chat --arm model --backend torch --learn` | Trained head. `--learn` imitates the **teacher label**. Abstains if `p < 0.22`. |

Smoke without a REPL:

```bash
python -m agent.chat --arm teacher --once "What do you perceive?"
python -m agent.chat --arm model --backend numpy --once "Probe the energy peak"
python -m agent.chat --arm model --backend torch --once "Probe the energy peak"
```

`--ticks` is a **count** (offline synthetic warmup). Journal path is `--journal`. Do not pass a file to `--ticks`.

### B · live observer (snake on)

Power CYD CSI senders + bridge ESP32s so UDP reaches the host on **:4210**. Only **one** process binds 4210 (window B1).

| Window | Directory | Command | Looking at |
|--------|-----------|---------|------------|
| B1 · conductor | `~/projects/throne-room` | `python -m observer.startup --full` | Bridge :4210 → digest → torch HUD → Aurora (fail-closed). |
| B2 · agent REPL | same | `python -m agent.chat --live --arm model --backend torch` | Chat as actuator on live CSI. Does **not** bind UDP. `:snap` `:drain` `:status` `:arm` `:q` |
| B3 · follow | same | `python -m agent.chat --live --follow` | CSI/Aurora → FieldTick. No REPL. Watch the journal. |
| B4 · snake | `wifi-sensing-system` firmware on CYDs | power + UDP :4210 | Physical organ. If this is quiet, B1 prints `csi_stale`. |
| B5 · engine | `metafield-engine` | its own tests | Canonical World. Do not patch it from throne-room. |
| B6 · ABI / SELF | `metafield-operator-abi` / `self-state-kernel` | their tests | Contracts. `agent/` here is the adapter. |
| B7 · bodies | `optical-body-s3` / `echo-grid-ultrasonic-os` / `hall-node-s3` / `zvs-node` | flash firmware | Organs emit FieldObservation. They do not run MetaField. |
| B8 · field-bus / arty | `field-bus` / `arty-realtime` | bring-up docs there | Fast physical loop. Slow model loop stays in throne-room. |
| B9 · aurora private | `aurora-coordination` | ESCAPE / Redis | Device actuators. `act.device` is **not** default here. |

Journals (all under `/tmp/metafield/`):

| File | Writer | Reader |
|------|--------|--------|
| `csi.jsonl` | bridge (B1) | HUD, agent `--live`, consumer |
| `aurora_actions.jsonl` | aurora.action_layer | agent `--live`, HUD |
| `agent_ticks.jsonl` | agent loop | replay |
| `arm_dec_v0.npz` | numpy train | `--backend numpy` |
| `arm_gpt_v0.pt` | torch train | `--backend torch` / auto |
| `arm_trajectories.jsonl` | `--live` agent | mix into the next train |
| `obs_digest.json` | conductor | health |
| `bridge.log` | metafield_bridge | debug |

`Ctrl+C` the conductor stops its children. Follow and REPL are separate processes — stop those yourself.

Paths if you `cd`'d off:

```bash
cd ~/projects/throne-room
source .venv/bin/activate
```
