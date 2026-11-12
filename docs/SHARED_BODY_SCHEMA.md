# SHARED_BODY schema 2.0

## Required identity fields

| Field | Type | Notes |
|-------|------|-------|
| `body_id` | string | Stable. Alnum + `_` `.` `-`. Max 128. |
| `schema_version` | string | `"2.0"` (major 2 accepted) |
| `source_system` | string | e.g. `throne-room.metafield_bridge` |
| `source_node_id` | string | Original node / device id |
| `observation_id` | string | Deterministic; never array index |

## Required measurement fields

| Field | Type | Notes |
|-------|------|-------|
| `observed_at` | string | Source timestamp (ISO preferred) |
| `ingested_at` | string | Host ingestion time (ISO) |
| `regions` | string[] | Region names present |
| `measurements` | Measurement[] | Value may be null |
| `provenance` | object | Origin metadata |

## Measurement

```json
{
  "region": "csi_energy",
  "value": 0.58,
  "confidence": 0.9,
  "unit": null,
  "source_key": "csi_energy"
}
```

`value` omitted or null = missing. Never invent.

## Optional typed fields

| Field | When present |
|-------|----------------|
| `body_type` | optical / lattice / wifi_csi / ultrasonic / zvs / hall / sim / other |
| `bus_node_id` | Field Bus uint8 when known |
| `energy` | **Only** when a genuine `*energy` region supplied a value |
| `heat` | From FieldCubeEnsemble when available |
| `hot_cell` | `[z,y,x]` |
| `health` | ok / … |
| `geometry_state` | calibrated / unknown / … |
| `residual` | head residual |
| `surprise` | head surprise flag |
| `deposits` | cube deposits |
| `last_seen` | unix float for status |
| `status` | ALIVE / STALE / TIMEOUT / MISSING |

## Provenance

```json
{
  "packet_type": "FieldObservation",
  "raw_node": "esp32_cyd_01",
  "device_timestamp": 123456,
  "synthetic": false,
  "notes": null,
  "extra": { "rssi_dbm": -52 }
}
```

Unknown keys land in `extra` so they are not dropped.

## Envelope types

| type | Meaning |
|------|---------|
| `SHARED_BODY` | single record |
| `SHARED_BODY_SNAPSHOT` | registry snapshot |
| `SHARED_BODY_SET` | legacy multi-body list (v1 compat) |
| `REVERIE_BODY_SET` | Reverie projection |

## Compatibility

- **v1 → v2**: intensity/heat may exist; `energy` only when genuine; `observed_at`/`ingested_at` split; `observation_id` required; provenance explicit.
- Unknown major versions are rejected with an actionable error.
- Optional fields may be absent; consumers must tolerate absence.

## Example (synthetic fixture)

See `observer.shared_body.export.example_fixture_record()` — always marked `provenance.synthetic: true`.
