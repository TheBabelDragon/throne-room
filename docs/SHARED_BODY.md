# SHARED_BODY v2 — Live Field Continuity

Canonical identity and measurement layer so the entire MetaField ecosystem
observes the **same physical world** without losing track of what was
actually measured.

```
Physical sensor / CSI
        ↓
FieldObservation (metafield_bridge — sole UDP :4210 owner)
        ↓
SHARED_BODY adapter  (observer/shared_body)
        ↓
Registry (snapshot + append-only journal)
        ↓
┌───────────────┬────────────────┬──────────────┬────────────────┐
│ MetaField     │ Field Bus      │ Reverie      │ Agent / Qwuack │
│ field-memory  │ node identity  │ visualization│ read-only perc.│
└───────────────┴────────────────┴──────────────┴────────────────┘
```

This is an **integration layer**, not another independent simulation.

## Paths

| Path | Role |
|------|------|
| `/tmp/metafield/csi.jsonl` | FO stream (existing) |
| `/tmp/metafield/obs_digest.json` | conductor digest (existing) |
| `/tmp/metafield/shared_body/snapshot.json` | current SHARED_BODY snapshot |
| `/tmp/metafield/shared_body/observations.jsonl` | append-only history |
| `/tmp/metafield/shared_bodies_reverie.json` | Reverie projection |

## Invariants

1. **Stable identity** — `body_id` never derived from array position.
2. **No fabrication** — energy / intensity / temperature only when a genuine source supplied them. Missing stays missing.
3. **Timestamp split** — `observed_at` (source) ≠ `ingested_at` (host).
4. **Provenance preserved** — original node, device timestamp, synthetic flag.
5. **Duplicate `observation_id` rejected** — deterministic id from body + time + source + region fingerprint.
6. **Persistence outside FieldTick** — registry does not participate in the deterministic commit path.
7. **Agent is read-only** — perception adapter never writes FieldTick or grants capabilities.
8. **No second UDP :4210** — adapter consumes existing FO packets only.

## Quick use

```python
from observer.shared_body import (
    SharedBodyRegistry,
    from_field_observation_packet,
    ingest_packet,
    snapshot_to_reverie,
)

reg = SharedBodyRegistry()  # /tmp/metafield/shared_body/
body, reason = ingest_packet(fo_packet, reg, field_snap=cube_snapshot)
print(reason, body.body_id if body else None)

# Reverie export
snapshot_to_reverie(registry=reg)

# Agent perception (read-only)
from agent.shared_body_perception import perceive_shared_bodies
events = perceive_shared_bodies(tick=42, registry=reg)
```

## Status

| Status | Meaning |
|--------|---------|
| ALIVE | last_seen ≤ 8 s |
| STALE | 8 s < last_seen ≤ 30 s |
| TIMEOUT | last_seen > 30 s |
| MISSING | no last_seen |

## Docs

- [SHARED_BODY_SCHEMA.md](SHARED_BODY_SCHEMA.md) — record shape
- [SHARED_BODY_INTEGRATION.md](SHARED_BODY_INTEGRATION.md) — wiring
- [SHARED_BODY_OPERATIONS.md](SHARED_BODY_OPERATIONS.md) — ops / failure modes

## Acceptance

A real observer record becomes a canonical SHARED_BODY; identity survives
restart; the same body is recognized by separate consumers; provenance
stays intact; history can be replayed; Reverie export contains actual
observations; agent perception remains read-only; existing observer /
Aurora / Qwuack paths stay intact.
