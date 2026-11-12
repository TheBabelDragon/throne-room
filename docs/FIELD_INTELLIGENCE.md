# Field Intelligence v1

**Baseline main:** `ccca63c361fd0702d97aebfceee65b587e96c6d0` (PR #11 SHARED_BODY perception merged)

World Mirror · Associative Memory · Counterfactual Laboratory · Decision Observatory · Prediction

Additive layer on Throne Room. Does **not** replace FieldTick, Operator ABI, Duck Gate admission, Aurora, or Millennium proof rules.

## Pipeline

```
REAL OBSERVATIONS → SHARED_BODY → WORLD MIRROR → QWUACK PERCEPTION
  → ASSOCIATIVE MEMORY → DUCK GATE (observatory witnesses)
  → OPERATOR ABI → FIELDTICK → CONSEQUENCE
  → MEMORY / PREDICTION EVAL / COUNTERFACTUAL LAB
```

## Package `agent/field_intelligence/`

| Module | Role |
|--------|------|
| world_mirror | Entities, changes, relations; no invented zeros |
| associative_memory | Typed append-only experiences |
| counterfactual | Isolated branches; never mutates live FieldTick |
| decision_observatory | Witness for DUCK/RANDOM selection + admission |
| prediction | Structured forecasts + evaluation |

## Safety invariants

1. FieldTick sole authoritative commit.
2. Operator ABI admits.
3. Qwuack is a tenant.
4. Duck Gate is the admission boundary.
5. Observatory does not authorize.
6. Counterfactuals always SIMULATED.
7. Synthetic stays FIXTURE.
8. Missing measurements stay None.
9. No default act.device.
10. No second UDP :4210.
11. No model inference on commit path.
12. Hypothesis ≠ observation; remembered action ≠ permission.

## Commands

```bash
python -m unittest tests.test_field_intelligence -v
python -m agent.test_invariants
python -m unittest discover -s tests
```

See also WORLD_MIRROR.md, ASSOCIATIVE_MEMORY.md, COUNTERFACTUAL_LAB.md, DECISION_OBSERVATORY.md, PREDICTION_AND_LEARNING.md.
