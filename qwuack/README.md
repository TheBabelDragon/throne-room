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

## Start the Duck

```bash
python -m qwuack --runtime
python -m qwuack --runtime --desk math
python -m qwuack.runtime --once
python -m qwuack.runtime --live --follow
python -m qwuack.runtime --desk math --cycles 3
```

`--full` does not start this process. Run it as a sibling.

```bash
python -m observer.startup --full
python -m qwuack.runtime --live --follow
```

| File | Writer | Reader |
|------|--------|--------|
| `/tmp/metafield/qwuack_status.json` | field runtime | HUD / digest |
| `/tmp/metafield/qwuack_desk.json` | math desk | you |
| `/tmp/metafield/qwuack_memory.jsonl` | math desk | next hypothesis |

Tests:

```bash
python -m unittest tests.test_qwuack_identity tests.test_qwuack_policy \
    tests.test_qwuack_runtime tests.test_qwuack_boundary tests.test_qwuack_desk
```

Longer contract: [`docs/QWUACK.md`](../docs/QWUACK.md).
