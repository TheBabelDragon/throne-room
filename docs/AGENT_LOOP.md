# Agent loop

Throne Room already had a live observer and a fail-closed Aurora action layer.
This document is the spine that lets those pieces talk to an agent without
putting a chatbot inside FieldTick.

```
                    HUMAN INTERFACES
                    Chat / Voice / HUD / API
                              │
                              ▼
                    AGENT / COGNITION
                    self-state-kernel
                    (identity, goals, attention, memory)
                              │
                      ActionProposal
                              ▼
                    Operator ABI
                    capability check · clamp · provenance
                              │
                       FieldDelta
                              ▼
                    FieldTick  ← WORLD (engine)
                              │
                         observe
```

Chat is not a special architecture. It is the first actuator: modality
`language` on a `PerceptionEvent`. SPEAK is an action like PROBE.

## What already existed here

| Surface | Owns | Does not own |
|---------|------|----------------|
| `observer/` | real CSI, FieldObservation JSONL, UDP :4210 | cognition, LLM |
| `visualization/` | torch HUD, field head | world commit |
| `aurora/` | policy intents, Redis ESCAPE, fail-closed fire | FieldTick, chat |
| `metafield` sibling | FieldMemory promotion | operator ABI |

## What this adds (`agent/`)

| Module | Role |
|--------|------|
| `schemas.py` | FieldTick, FieldDelta, ActionProposal, PerceptionEvent |
| `engine.py` | deterministic voxel field + replay |
| `operator_abi.py` | capability contract |
| `self_state.py` | SELF adapter (canonical kernel: `self-state-kernel`) |
| `bridge.py` | FieldObservation ↔ PerceptionEvent, Aurora Intent ↔ ActionProposal |
| `loop.py` | perceive → self → reason → propose → validate → commit |
| `chat.py` | first human interface |

The TypeScript HUD kernel that ran the same loop in Grok Build lives in
`web/src/` so the contracts stay bilingual.

## Two action planes

They meet at `ActionProposal`. They do **not** collapse.

1. **Aurora** — `probe` / `attention` / `hold` / `scale_down`. Fail-closed.
   Redis `aurora:control:escape` is sovereign. Bodies never receive power
   or motion from this layer without a separate actuator bridge.
2. **Operator ABI** — `SPEAK` / `PROBE` / `REMEMBER` / `ATTEND` / `SET_GOAL` /
   `QUERY_FIELD` / `WAIT`. Capability-based. Default caps do **not** include
   `act.device`. A chat agent cannot fire the swarm by talking.

`aurora.proposals.aurora_intent_to_proposal` wraps a policy Intent so SELF
can observe it. `proposal_to_aurora_action` is a journal view, not a fire.

## Invariants

1. FieldTick is the only commit object. Intelligence never writes the field
   directly.
2. Systems inside the scheduler use no wall-clock and no RNG.
   `replay_to(n)` from genesis equals the live field at sequence n.
3. LLM / mock reasoner runs *outside* the tick. Structured ActionProposal only.
4. Synthetic CSI is a fixture (`dev/` energy, `make_synthetic_csi` here).
   Operational ingest remains real-measurement-only.
5. Provenance: every CommittedAction carries proposal_id, observation_id,
   capability, tick.

## Run

```bash
# invariants (no hardware)
python -m agent.test_invariants

# chat on synthetic field
python -m agent.chat --once "What do you perceive?"

# same loop, live CSI + Aurora journals (no second UDP bind)
python -m agent.chat --live --once "What do you perceive?"

# FieldTick follower next to the conductor
python -m observer.startup --full
python -m agent.chat --live --follow
```

`--live` tails `/tmp/metafield/csi.jsonl` and `aurora_actions.jsonl`. Aurora probes
commit **local** FieldDeltas so SELF sees them. Redis ESCAPE still gates hardware.

Full hardware stack is unchanged:

```bash
python -m observer.startup --full
```

## Placement in the repo graph

```
wifi-sensing-system / optical-body-s3 / echo-grid / hall-node
        │  FieldObservation
        ▼
observer.metafield_bridge ─────────────► metafield FieldMemory
        │
        ├── visualization.torch_display     (spatial HUD)
        ├── aurora.action_layer             (policy, ESCAPE)
        └── agent.loop                      (SELF + ABI + FieldTick)
                    ▲
                    │ language PerceptionEvent
                 agent.chat
```

Distributed / Aurora swarm expansion stays last, as designed.
