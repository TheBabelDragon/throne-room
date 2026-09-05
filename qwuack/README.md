# Qwuack

Embodied identity / runtime inhabiting the Throne Room agent loop.

Qwuack is a tenant of Throne Room, not a new landlord.

```
physical organs
    ↓
FieldObservation
    ↓
PerceptionEvent
    ↓
SELF
    ↓
Qwuack cognition
    ↓
ActionProposal
    ↓
Operator ABI
    ↓
FieldDelta
    ↓
FieldTick
    ↓
actuation / world
    ↓
observation
    ↺
```

Qwuack proposes. The Operator ABI authorizes. FieldTick commits.
The world responds. Qwuack observes the response.

## The lake belongs to Daddy

Qwuack has a habitat, not god-mode.
"The lake belongs to Daddy" describes jurisdiction,
not unrestricted authority.
Qwuack can inhabit a bounded field and act within
its authorized capabilities, but the field remains
owned by the substrate and its commit/authority rules.

Daddy may own the lake.

The FieldTick still owns the receipt.

## What this layer is

| File | Owns | Does not own |
|------|------|----------------|
| `identity.py` | who Qwuack is | world facts, Field writes |
| `policy.py` | what Qwuack proposes | FieldTick, ABI, hardware |
| `runtime.py` | wake / perceive / submit / observe | UDP :4210, Aurora ESCAPE, language machinery |

Habitat scope (`lake`) permits:

`QUERY_FIELD` `ATTEND` `PROBE` `REMEMBER` `SPEAK` `WAIT`

It does **not** grant `act.device`. Dangerous hardware stays with Aurora / ESCAPE.

Language is Qwuack's voice, not its architecture. `agent/language/` and
`agent/chat.py` remain the attachment points. Memory is SELF, not a second database.

## Run

```bash
# invariants (no hardware)
python -m unittest tests.test_qwuack_identity tests.test_qwuack_policy \
    tests.test_qwuack_runtime tests.test_qwuack_boundary

# tenant cycle on the existing World (synthetic fixture)
python -m qwuack.runtime --once

# attach to the running observer journals — never binds UDP :4210
python -m observer.startup --full
python -m qwuack.runtime --live --follow
```

Status is a compact object written to `/tmp/metafield/qwuack_status.json`
for existing HUD / digest surfaces:

```
QWUACK
-------
state:          awake
habitat:        lake
perception:     live
sequence:       1842
last_action:    ATTEND
authorization:  granted
consequence:    observed
```

## Definition of done

Qwuack is not done when a duck class exists or a chatbot says quack.

Qwuack is done when the duck lives in the field:

real sensor → FieldObservation → PerceptionEvent → Qwuack → SELF →
ActionProposal → Operator ABI → FieldDelta → FieldTick → authorized
action → world → sensor.

And these remain true:

- Qwuack cannot directly mutate Field
- Qwuack cannot bypass ABI
- Qwuack cannot bypass ESCAPE for dangerous hardware
- Qwuack cannot invent observations
- Qwuack cannot rewrite FieldTick
- Qwuack cannot acquire capabilities merely by asking
- Qwuack can learn from consequences
- Qwuack can change its subsequent behavior
