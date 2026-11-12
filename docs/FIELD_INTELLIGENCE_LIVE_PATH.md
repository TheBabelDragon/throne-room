# Field Intelligence — Live Path

**Baseline main (post PR #12):** `c721e622654e18a66570e134e87a960e88278375`

## What this adds

Wires the v1 library into the real Qwuack tenant cycle:

```
FieldObservation (CSI / synthetic)
  → observation_to_perception
  → WorldMirror.ingest_body_view
  → AssociativeMemory OBSERVATION
  → Qwuack policy (ActionProposal)
  → DecisionObservatory (witness)
  → AssociativeMemory ACTION + Prediction
  → Operator ABI validate
  → FieldTick commit
  → consequence
  → AssociativeMemory CONSEQUENCE + prediction evaluate
  → episode inputs for CounterfactualLab
```

## Authority (unchanged)

- FieldTick remains the sole commit mechanism
- Operator ABI remains the sole admission gate
- Observatory does not authorize
- CounterfactualLab always labels outcomes **SIMULATED** and never mutates live FieldTick
- Bridge can be disabled: `Runtime(..., field_intelligence=False)` or `--no-field-intelligence`

## Honesty about sensing

- Synthetic path: `make_synthetic_csi` → mode **FIXTURE**
- Live path: journal follow via `Runtime.attach_feeds` / `--live` (same hooks; requires observer journals)
- Physical CSI hardware is not claimed by unit tests

## Commands

```bash
# component tests
python -m unittest tests.test_field_intelligence -v

# end-to-end live-path (synthetic observation through full stack)
python -m unittest tests.test_field_intelligence_live_path -v

# one synthetic cycle with FI journals under /tmp/metafield/field_intelligence
python -m qwuack.runtime --ticks 3 --once

# disable bridge
python -m qwuack.runtime --ticks 1 --no-field-intelligence

# custom journal root
python -m qwuack.runtime --ticks 2 --fi-root /tmp/fi-demo
```

## Inspect an episode

After a cycle, journals land under the FI root:

- `world_mirror/state.json`
- `associative_memory.jsonl`
- `decision_observatory.jsonl`
- `predictions.jsonl`
- `episode_trace.jsonl`
- `counterfactual/<experiment_id>.json`

```python
from qwuack.runtime import Runtime
from agent.loop import World
from agent.perception import make_synthetic_csi

rt = Runtime(world=World(), status_path=None)
rt.cycle(make_synthetic_csi(1))
print(rt.fi.episode_report())
exp = rt.fi.replay_episode(seed=0)
alt = rt.fi.alternative_action(exp.experiment_id, label="alt", action_type="PROBE")
```

## Known limitations

- Console shell still presentation-only until bound to these journals
- Live hardware CSI requires the observer journal path; tests use FIXTURE
- Learning improvement is not claimed without comparative measurements beyond prediction accuracy counts
- Millennium formal verification remains separate from computational evidence
