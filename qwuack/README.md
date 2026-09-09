# Qwuack

Embodied identity / runtime inhabiting the Throne Room agent loop.

Qwuack is a tenant of Throne Room, not a new landlord.

## The lake belongs to Daddy

Qwuack has a habitat, not god-mode.
"The lake belongs to Daddy" describes jurisdiction,
not unrestricted authority.

Daddy may own the lake.
The FieldTick still owns the receipt.

## Start the Duck

```bash
python -m qwuack --runtime
python -m qwuack --desk millennium --once --cycles 8
python -m qwuack.runtime --once
python -m qwuack.runtime --live --follow
python -m qwuack.millennium --once
python -m qwuack.startup --body millennium --once
```

`--full` does not start this process. Run it as a sibling.

| File | Writer |
|------|--------|
| `/tmp/metafield/qwuack_status.json` | field runtime |
| `/tmp/metafield/qwuack_desk.json` | math desk |
| `/tmp/metafield/millennium_status.json` | Millennium Lab |
| `/tmp/metafield/millennium_memory.jsonl` | proof-killer survivors |

Millennium Lab treats the seven Clay problems plus Collatz as
adversarial environments. Progress is scored. Victory is illegal.
See [`docs/MILLENNIUM.md`](../docs/MILLENNIUM.md).

```bash
python -m unittest tests.test_qwuack_identity tests.test_qwuack_policy \
    tests.test_qwuack_runtime tests.test_qwuack_boundary tests.test_qwuack_desk \
    tests.test_millennium_lab
```
