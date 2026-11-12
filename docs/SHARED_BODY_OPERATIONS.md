# SHARED_BODY operations

## Startup

No separate process is required. The registry is process-local and
persists under `/tmp/metafield/shared_body/`.

If you wire the adapter into `observer.startup` digest loop, it starts
with the conductor. Otherwise:

```bash
python -c "
from observer.shared_body import SharedBodyRegistry
r = SharedBodyRegistry()
print(r.counts())
"
```

## Failure behaviour

| Failure | Behaviour |
|---------|-----------|
| Malformed FO packet | adapter returns `(None, reason)`; conductor continues |
| Duplicate observation_id | rejected; registry unchanged |
| Journal write error | body still registered in memory; reason notes failure |
| Snapshot write error | same |
| Missing `/tmp/metafield` | directories created on demand |
| Agent import of shared_body fails | perception returns `[]` |

## Inspection

```bash
# current snapshot
python -m json.tool /tmp/metafield/shared_body/snapshot.json | head

# journal tail
tail -n 5 /tmp/metafield/shared_body/observations.jsonl

# Reverie projection
python -m json.tool /tmp/metafield/shared_bodies_reverie.json | head
```

## Tests

```bash
PYTHONPATH=. python -m unittest tests.test_shared_body -v
```

## Hardware note

This layer is complete when a **real** observer record becomes a
canonical SHARED_BODY, identity survives restart, and consumers agree
on the same `body_id`. Hardware integration is **not** claimed complete
until exercised against live CSI / optical observations on device.

## Cleanup

```bash
rm -rf /tmp/metafield/shared_body
rm -f /tmp/metafield/shared_bodies_reverie.json
```
