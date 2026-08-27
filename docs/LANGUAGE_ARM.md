# Language Arm — training runtime + composed voice

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
 tokenizer → action head → compose() voice → ActionProposal
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
| Model weights | learned general capability (action head) |
| compose() | the voice — reports the field, not genesis tokens |
| SELF | who this participant currently is |
| Memory | what happened / what it knows |
| MetaField | what is happening |

The numpy decoder will not speak English. That is not unfinished
response ability; it is the wrong job for a 32-d genesis transformer.
**Action head chooses. compose() fills the utterance from LanguageContext.**
Teacher and model share that voice.

## Protocol first

`LanguageContext` → `LanguageOutput` → `ActionProposal`

Also: `ConversationEvent`, `MemoryReference`, `ParticipantObservation`.

`LanguageOutput` carries `confidence`, `predicted_action`, `abstained`.

Any runtime that satisfies the protocol can be the arm. Today:

- `teacher` — local structured policy
- `model` — trained action head; compose() is the utterance; if softmax
  `p < 0.22` the arm WAITs instead of a bad commit

`--learn` takes one imitation step per turn using the **teacher label**.

## Tokenizer

Owned here: `agent/language/tokenizer.json`

- bytes 0–255 identity
- specials from 256: `<OBSERVE>` `<ATTEND>` `<QUERY>` `<REMEMBER>` `<PROPOSE>` `<SPEAK>` `<PROBE>` `<SET_GOAL>` …
- version `arm-tok-v1`
- `user_span()` is the current utterance (`<USER>`…`<ARM>`). Field/SELF
  prefixes are context, not the action-head features.

## What actually trains

Two local runtimes. Same protocol. Same compose() voice.

| Runtime | Command | Trains |
|---------|---------|--------|
| numpy (default) | `python -m agent.language.train` | action head on hashed n-grams. Decoder blocks stay genesis. No torch required. |
| torch | `pip install torch` then `python -m agent.language.torch_train` | **transformer blocks**, user-span pooled embeddings → action, LM on composed `<PROPOSE><ACTION>body<EOS>` |

Hold-out action accuracy ≥ 0.5 is the gate. Best checkpoint is kept.

`compose()` remains the operator utterance. Field numbers are observed, not sampled. Torch generation is for the protocol sequence and trajectories.

```
observation → LanguageContext → tokens/proposal → ABI → FieldTick → world_response
```

## Run

Torch is optional. Numpy stays the default. Install from the venv — do not
pip-install the extras name from PyPI, and quote any `[...]` or the shell
will eat it.

```bash
pip install torch
# CPU-only fallback if the default wheel fails:
#   pip install typing-extensions jinja2 filelock sympy networkx
#   pip install torch --index-url https://download.pytorch.org/whl/cpu
# from the repo root, same extra:
#   pip install -e ".[head-torch]"

python -m agent.language.harness
python -m agent.language.train --examples 64 --steps 40
python -m agent.language.torch_train --examples 64 --steps 16
python -m agent.chat --arm teacher --once "What do you perceive?"
python -m agent.chat --arm model --once "Probe the energy peak"
python -m agent.chat --arm model --backend torch --learn
```
`--backend auto` (default) prefers `/tmp/metafield/arm_gpt_v0.pt` when torch is installed.

REPL: `:snap` `:drain` `:status` `:arm` `:q`

Checkpoints:

- numpy: `/tmp/metafield/arm_dec_v0.npz` (`ARM_CHECKPOINT=`)
- torch: `/tmp/metafield/arm_gpt_v0.pt` (`ARM_TORCH_CHECKPOINT=`)

Trajectories: `ARM_TRAJECTORIES=` (default `/tmp/metafield/arm_trajectories.jsonl`).

## Milestone

1. Join the loop as a participant (capabilities, no `act.device`)
2. Receive only permitted observations
3. Maintain SELF
4. Consume conversation as perception
5. Composed utterance from the field (not an API, not genesis English)
6. Generate structured ActionProposal
7. Send actions through the ABI
8. Observe resulting FieldTicks
9. Provenance + confidence on every proposal
10. Replay the field interaction deterministically
11. Fit an action head on engine trajectories until hold-out ≥ 0.5
12. Abstain (WAIT) when the head is below threshold
13. Online imitation (`--learn`) from the teacher label
14. Torch decoder that actually trains attention (optional extra)
