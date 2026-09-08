# Duck Gate v0.1

Influence is not authority.

```
External intelligence  →  InfluenceProposal  →  Duck Gate  →  AdmittedDelta  →  FieldTick
```

Qwuack proposes. `OperatorAbi.validate` is the gate. FieldTick commits.
The protocol does not require an AI model. Replay must not query one.

## Planes

| Plane | Trust | Owners in this repo |
|-------|-------|---------------------|
| Influence | untrusted | `qwuack.policy`, language arm, Aurora intents, chat, sensors |
| Duck | authoritative | `agent.operator_abi` + `qwuack.gate` |
| State | deterministic | `agent.engine.FieldScheduler` |

## v0.1 rules

1. No external source mutates authoritative state.
2. Every proposal produces an explicit status. Silent drop is forbidden.
3. Default stale policy: reject when `observation_sequence` is present and off by more than `stale_after`.
4. Default bounds policy: reject. Do not clamp a requested magnitude into range.
5. Budgets consume on admit, not on propose.
6. Confidence and rationale are not authority.
7. Gate config is versioned (`duck_gate_v0.1`).
8. QwuackState is a tenant snapshot. It is not a write handle.

Statuses: `ADMITTED REJECTED EXPIRED STALE SUPERSEDED CONFLICTED BUDGET_EXCEEDED UNAUTHORIZED INVALID INVARIANT_VIOLATION` plus `BOUNDS` for domain errors.

## Live conductor

`python -m observer.startup --full` does **not** start Qwuack and does **not** give the duck UDP :4210.

```bash
python -m observer.startup --check --full
python -m qwuack.runtime --once
python -m qwuack.runtime --live --follow   # sibling of the conductor
```

QwuackState path: `/tmp/metafield/qwuack_state.json`.
Digest reads it when present.
