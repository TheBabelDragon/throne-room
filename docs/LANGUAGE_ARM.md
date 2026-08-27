# Language Arm v0

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
- `model` — tiny numpy decoder; valid structured decode wins, else teacher bootstrap

Untrained genesis weights will not speak English. That is expected. The
**environment + protocol + trajectory format + harness** are the v0
milestone. Training is a later decision that must not change this shape.

## Tokenizer

Owned here: `agent/language/tokenizer.json`

- bytes 0–255 identity
- specials from 256: `<OBSERVE>` `<ATTEND>` `<QUERY>` `<REMEMBER>` `<PROPOSE>` `<SPEAK>` …
- version `arm-tok-v0`

## Trajectories

Each turn can append `/tmp/metafield/arm_trajectories.jsonl`:

```
observation → context → tokens/proposal → ABI → FieldTick → world_response
```

The engine can generate these forever, deterministically. That is the
training environment. Do not scrape chat logs as the primary corpus.

## Run

```bash
python -m agent.language.harness
python -m agent.language.harness --arm model --steps 8
python -m agent.chat --once "What do you perceive?"
python -m agent.chat --arm teacher --live
```

## Milestone (v0)

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
