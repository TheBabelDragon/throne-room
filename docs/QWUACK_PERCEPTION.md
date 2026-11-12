# Qwuack SHARED_BODY perception

Read-only path from physical observations to Qwuack understanding.

```
FieldObservation (UDP :4210 → metafield_bridge)
        ↓
SHARED_BODY v2 registry (conductor_hook on digest tick)
        ↓
agent/shared_body_perception.py  (read-only)
        ↓
Qwuack policy (recognition / attention / restraint)
        ↓
ActionProposal → Operator ABI → FieldTick
```

## Invariants

- Qwuack identity is immutable and separate from perception.
- No fabricated energy or zero-filled missing values.
- Synthetic fixtures cannot authorize physical PROBE.
- STALE / TIMEOUT / MISSING observations force WAIT.
- Unchanged returning bodies do not re-trigger attention.
- Perception never writes FieldTick or opens UDP.

## Status modes

| Mode | Meaning |
|------|---------|
| LIVE | ≥1 non-synthetic ALIVE body |
| FIXTURE | only synthetic bodies alive |
| STALE | bodies present but not ALIVE |
| OFFLINE | empty registry |
| ERROR | read failure |
