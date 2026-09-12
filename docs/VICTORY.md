# Victory admission

The Duck proposes. The workbench admits.

`victory_legal` is not a Qwuack mood, not a lab generation flag,
and not a desk-wide banner. It is a field on one object:

`VictoryCertificate` (`ObjectKind.CERTIFICATE`, id prefix `VC`).

## Fail-closed pipeline

```
proposal
    → schema / checker blob
    → problem identity (registry id)
    → prize rules (Poincaré never)
    → MathProof.is_proof
    → dependency closure
    → checker token
    → per-problem acceptable_completion
    → VictoryCertificate
```

Rejected proposals are still stored. They carry `victory_legal: false`
and `status: rejected`. Silent drop is forbidden.

## What is never enough

- A Duck sentence that says the prize is solved
- `verification.formal: PASS` typed by the agent
- A finite named experiment
- A lemma that does not cover the problem statement
- A checker blob with a broken token
- Poincaré / CMI reclaim

## Surfaces

| Surface | `victory_legal` |
|---------|-----------------|
| `millennium_status.json` / lab state | always `false` |
| `duck_desk.json` environment field | always `false` |
| admitted `VC-####` object | `true` only after the pipeline |

Desk text: `Victory is legal only by certificate.`

## Code

- `qwuack/workbench/checker.py` — stub checker + HMAC token
- `qwuack/workbench/victory.py` — `evaluate_victory` / `admit_victory`
- `qwuack/workbench/objects.py` — `ObjectKind.CERTIFICATE`, `MathObject.victory_legal`
- `tests/test_victory_certificate.py`
