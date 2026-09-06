# Qwuack

Embodied identity / runtime inhabiting the Throne Room agent loop.

Qwuack is a tenant of Throne Room, not a new landlord.

## The lake belongs to Daddy

Qwuack has a habitat, not god-mode.
"The lake belongs to Daddy" describes jurisdiction,
not unrestricted authority.
Qwuack can inhabit a bounded field and act within
its authorized capabilities, but the field remains
owned by the substrate and its commit/authority rules.

Daddy may own the lake.

The FieldTick still owns the receipt.

## Train the duck

Qwuack does not grow its own model. It rolls the field, writes the existing
language-arm trajectory schema, then the existing trainer mixes those rolls
into the action head.

```bash
cd ~/projects/throne-room
git fetch origin qwuack-tenant && git checkout qwuack-tenant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m unittest tests.test_qwuack_identity tests.test_qwuack_policy \
    tests.test_qwuack_runtime tests.test_qwuack_boundary

python -m qwuack.runtime --once
python -m qwuack.runtime --record --roll 16 --drill --train --examples 48 --steps 24
python -m agent.chat --arm model --once "What do you perceive?"
python -m agent.chat --arm model --once "Probe the energy peak"
```

Live pond (conductor already owns UDP :4210):

```bash
python -m observer.startup --full
python -m qwuack.runtime --live --follow --record
python -m agent.language.train --trajectories /tmp/metafield/qwuack_trajectories.jsonl
```

| File | Writer | Reader |
|------|--------|--------|
| `/tmp/metafield/qwuack_trajectories.jsonl` | `qwuack.runtime --record` | `agent.language.train` |
| `/tmp/metafield/arm_dec_v0.npz` | `agent.language.train` | `agent.chat --arm model` |
| `/tmp/metafield/qwuack_status.json` | runtime | HUD / you |
