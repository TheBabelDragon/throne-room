# Throne Room

**Operational live Field Observer + agent-in-a-world loop for the MetaField stack.**

Two faces, one repo:

1. **Live observer** — real measurements only. CSI snake → JSONL → MetaField → Aurora → torch HUD.
2. **Agent loop** — chat as the first human actuator. PerceptionEvent → SelfState → ActionProposal → operator ABI → FieldDelta → FieldTick.

They meet at shared schemas. They do not collapse. Aurora stays fail-closed. The agent never mutates FieldTick. `act.device` is not a default capability.

Qwuack is the embodied tenant of that loop — habitat `lake`, not god-mode.
Millennium Lab is the Duck's long-term desk: seven prize ponds plus Collatz,
progress scored, victory illegal. See [docs/MILLENNIUM.md](docs/MILLENNIUM.md).

```bash
python -m qwuack.millennium --once
python -m qwuack.startup --body millennium --once
python -m unittest tests.test_millennium_lab tests.test_qwuack_desk
```

Full operator walkthrough remains below.

---

See [docs/AGENT_LOOP.md](docs/AGENT_LOOP.md) for the contract and [qwuack/README.md](qwuack/README.md) for the tenant.

## Docs

| Doc | Content |
|-----|---------|
| [qwuack/README.md](qwuack/README.md) | Qwuack tenant — habitat, capabilities, closed loop |
| [docs/MILLENNIUM.md](docs/MILLENNIUM.md) | Duck Millennium Lab — adversarial ponds, proof-killer |
| [docs/QWUACK.md](docs/QWUACK.md) | How to start the Duck |
| [docs/LANGUAGE_ARM.md](docs/LANGUAGE_ARM.md) | Local language arm protocol · tokenizer · trajectories |
| [docs/CONTROL.md](docs/CONTROL.md) | Conductor + Aurora |
| [docs/MEASUREMENT.md](docs/MEASUREMENT.md) | Fine windows |
| [docs/SNAKE_PATH.md](docs/SNAKE_PATH.md) | CYD → host |
| [docs/METAFIELD_OBS_PATH.md](docs/METAFIELD_OBS_PATH.md) | CSI → memory |
| [docs/AURORA_ACTION.md](docs/AURORA_ACTION.md) | Action layer + escape |
| [docs/EXTRACTION_TRIBSTRUCT.md](docs/EXTRACTION_TRIBSTRUCT.md) | Cube/ensemble patterns |

The rest of the live-observer / language-arm walkthrough is unchanged on `main` history; this patch only adds the Lab to the front door so the Duck's seven ponds are findable.
