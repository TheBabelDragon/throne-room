# Qwuack

Tenant of Throne Room. Not a landlord. Not a Millennium solver.

```
Qwuack proposes → Duck Gate admits → FieldTick commits → world answers
```

`--full` does **not** start Qwuack and does **not** give it UDP :4210.

## Start the Duck

Field tenant (CSI / Aurora journals):

```bash
python -m qwuack --runtime
python -m qwuack.runtime --once
python -m qwuack.runtime --live --follow
```

Theorem desk (finite claims only):

```bash
python -m qwuack --runtime --desk math
python -m qwuack.runtime --desk math --cycles 3
```

## Desks

| `--desk` | World | Surviving claim |
|----------|--------|-----------------|
| `field`  | CSI / Aurora tenant | an admitted field action |
| `math`   | Collatz bound       | `every n in 1..N reaches 1` — N named |

Unbounded sentences (`every integer reaches 1`, `RH is true`) are killed
at the experiment gate. That is the point.

## CLI that actually exists

```
--runtime
--desk field|math
--cycles N
--live
--follow
--once
--ticks N
--csi PATH
--aurora PATH
--journal PATH
--interval SEC
```

There is no `--record`. There is no `--drill`. There is no `qwuack-tenant` branch required.

## Files

| Path | Writer |
|------|--------|
| `/tmp/metafield/qwuack_status.json` | field runtime |
| `/tmp/metafield/qwuack_desk.json` | math desk |
| `/tmp/metafield/qwuack_memory.jsonl` | admitted/killed claims |

See also [`DUCK_GATE.md`](DUCK_GATE.md).
