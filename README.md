# Throne Room

**Operational live Field Observer + agent-in-a-world loop for the MetaField stack.**

Two faces, one repo:

1. **Live observer** — real measurements only. CSI snake → JSONL → MetaField → Aurora → torch HUD.
2. **Agent loop** — chat as the first human actuator. PerceptionEvent → SelfState → ActionProposal → operator ABI → FieldDelta → FieldTick.

They meet at shared schemas. They do not collapse. Aurora stays fail-closed. The agent never mutates FieldTick. `act.device` is not a default capability.

See [docs/AGENT_LOOP.md](docs/AGENT_LOOP.md) for the contract.

Qwuack is the embodied tenant of that loop — habitat `lake`, not god-mode.
`python -m qwuack.runtime` attaches to the existing World / observer journals
and never binds UDP :4210. See [qwuack/README.md](qwuack/README.md).

Millennium Lab is the Duck's long-term desk. Each Clay problem is an
adversarial pond. Progress is scored. Victory is illegal.

```bash
python -m qwuack.millennium --once
python -m qwuack.startup --body millennium
python -m unittest tests.test_millennium_lab
```

Contract: [docs/MILLENNIUM.md](docs/MILLENNIUM.md).

The live-observer walkthrough, language-arm desk, measurement defaults,
and sibling-repo table are unchanged from `main`. Keep using
`python -m observer.startup --full` for the CSI conductor.
