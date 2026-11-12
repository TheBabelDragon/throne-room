# SHARED_BODY integration

## Observer path (additive)

`metafield_bridge` remains the sole UDP :4210 owner. The SHARED_BODY
adapter consumes the same FO packets the digest loop already tails.

Recommended wiring (in the conductor digest loop or a thin side-car):

```python
from observer.shared_body import SharedBodyRegistry, ingest_packet
from observer.shared_body.export import snapshot_to_reverie

registry = SharedBodyRegistry()  # once at startup

# inside digest tick, after tailing FO packets:
for pkt in recent_packets:
    body, reason = ingest_packet(
        pkt,
        registry,
        field_snap=field_snap,
        head_snap=head_snap,
    )
    # reason is informational; never raise into the control loop

snapshot_to_reverie(registry=registry)  # optional Reverie export
```

Optional exports must not stop the observer if they fail.

## Agent path (read-only)

```python
from agent.shared_body_perception import perceive_shared_bodies

events = perceive_shared_bodies(tick=world.tick, registry=registry)
# feed into existing perception → SelfState path
# never into Operator ABI / FieldTick directly
```

## Consumer contracts

### MetaField

Ingest `measurements` + `body_id` into FieldMemory. Honour `synthetic`.
Do not invent energy when `energy` is absent.

### Field Bus

Use `bus_node_id` / `source_node_id` for reconciliation.
Helpers: `bus_node_to_body_id`, `body_id_to_bus_node`.

### Reverie

Prefer `/tmp/metafield/shared_bodies_reverie.json` (`REVERIE_BODY_SET`).
`intensity` may be null. `isVerified` is false for synthetic fixtures.

### Throne Room UI

Read registry snapshot. Show ALIVE / STALE / TIMEOUT from `status`.
Do not invent a parallel dataset.

## What this package does **not** do

- Open a second UDP socket
- Write FieldTick
- Grant `act.device`
- Patch Aurora fail-closed policy
- Modify Qwuack identity
- Mutate sibling repositories
