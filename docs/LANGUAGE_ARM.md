# Language Arm v0 → training runtime

The language arm is a **local Aurora participant**. It is not an API
client with a system prompt. The model does not define the architecture.

```
Aurora Participant
        │
        ▼
   SELF / State
        │
        ▼
 Language Arm
 tokenizer → transformer → generation → action decoding
        │
        ▼
 Operator ABI
        │
        ▼
    MetaField / FieldTick
```

## Separation that must not collapse

| Layer | Is |
|-------|----|
| Model weights | learned general capability |
| SELF | who this participant currently is |
| Memory | what happened / what it knows |
| MetaField | what is happening |

No network request is required for the cognition loop.

## Protocol first

`LanguageContext` → `LanguageOutput` → `ActionProposal`

Also: `ConversationEvent`, `MemoryReference`, `ParticipantObservation`.

Any runtime that satisfies the protocol can be the arm. Today:

- `teacher` — local structured policy (same as the old mock reasoner)
- `model` — tiny numpy decoder; action head selects SPEAK/PROBE/…; valid structured decode wins, else grounded bootstrap

Untrained genesis weights will not speak English. That is expected. After
`python -m agent.language.train` the **action head** is the part that
deserves to run.

## Tokenizer

Owned here: `agent/language/tokenizer.json`

- bytes 0–255 identity
- specials from 256: `<OBSERVE>` `<ATTEND>` `<QUERY>` `<REMEMBER>` `<PROPOSE>` `<SPEAK>` `<PROBE>` `<SET_GOAL>` …
- version `arm-tok-v1`
- `user_span()` is the current utterance (`<USER>`…`<ARM>`). Field/SELF
  prefixes are context for generation, not the action-head features.

## What actually trains (v1)

Numpy only. No torch required. Decoder blocks stay genesis until a later
torch path (`pip install throne-room[head-torch]`) exists — that is
honest, not a stub.

| Piece | Input | Target |
|-------|-------|--------|
| Action head `w_act`, `b_act` | user-span embed-bag ⊕ hashed byte-trigrams | SPEAK/PROBE/REMEMBER/ATTEND/SET_GOAL/QUERY_FIELD/WAIT |
| Token embeddings | those user-span ids | same labels (fastText-style) |
| LM head prefix | prompt hidden | teacher-forced `<PROPOSE><ACTION>` |

Hold-out action accuracy ≥ 0.5 is the gate. Best checkpoint is kept.

Corpus: MetaField engine rollouts labeled by the teacher policy, mixed
with `/tmp/metafield/arm_trajectories.jsonl` when present. Do not scrape
chat logs as the primary corpus.

```
observation → LanguageContext → tokens/proposal → ABI → FieldTick → world_response
```

## Run

```bash
python -m agent.language.harness
python -m agent.language.harness --arm model --steps 8
python -m agent.language.train --examples 64 --steps 40
python -m agent.chat --arm model --once "Probe the energy peak"
python -m agent.chat --arm teacher --live
```

Checkpoint: `/tmp/metafield/arm_dec_v0.npz` (or `ARM_CHECKPOINT=`).
Trajectories: `ARM_TRAJECTORIES=` (default `/tmp/metafield/arm_trajectories.jsonl`).

## Milestone

1. Join the loop as a participant (capabilities, no `act.device`)
2. Receive only permitted observations
3. Maintain SELF
4. Consume conversation as perception
5. Generate token-by-token locally
6. Generate structured ActionProposal
7. Send actions through the ABI
8. Observe resulting FieldTicks
9. Provenance on every proposal
10. Replay the field interaction deterministically
11. Fit an action head on engine trajectories until hold-out ≥ 0.5
