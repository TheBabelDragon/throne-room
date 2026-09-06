# SHARED_BODY — cross-feed contract

Canonical body record so Throne Room, MetaField, Reverie, and Field Bus
speak the same identifiers.

**File:** `/tmp/metafield/shared_bodies.json`  
**Producer:** `observer.shared_body` (wired from conductor digest loop)  
**Type:** `SHARED_BODY_SET` containing `SHARED_BODY` records

---

## Record shape

```json
{
  "schema_version": 1,
  "type": "SHARED_BODY",
  "body_id": "esp32_cyd_01",
  "body_type": "wifi_csi",
  "bus_node_id": null,
  "regions": {
    "csi_energy": 0.62,
    "csi_mean": 0.41,
    "head_fused_energy": 0.58,
    "head_entropy": 0.33
  },
  "heat": 0.71,
  "hot_cell": [1, 2, 0],
  "intensity": 0.71,
  "direction": { "x": 1.0, "y": 0.0, "z": -1.0 },
  "is_verified": true,
  "health": "ok",
  "geometry_state": "calibrated",
  "last_seen": 1723400000.1,
  "deposits": 142,
  "residual": 0.09,
  "surprise": false
}
```

| Field | Source |
|-------|--------|
| `body_id` | FO `body_id` / CSI `node` |
| `body_type` | FO or inferred from regions / id |
| `bus_node_id` | Field Bus 0x01–0x06 when known |
| `regions.*` | FO `field_regions[].observed` |
| `heat` / `hot_cell` | FieldCubeEnsemble snapshot |
| `intensity` | `head_fused_energy` → `csi_energy` → heat |
| `direction` | hot_cell mapped to [-1,1]³ (gyro later) |
| `is_verified` | health ok + non-trivial intensity (ZK later) |
| `residual` / `surprise` | `head_state.json` |

No invented sine-wave intensities. Missing data stays absent or zero.

---

## Identifier registry

### Body identity

| System | Field | Notes |
|--------|-------|-------|
| MetaField FO | `body_id` (string) | Canonical |
| CSI wire | `node` | Bridge expands → `body_id` |
| Field Bus | uint8 node id | See map below |
| Reverie | `id` / `body_id` | Must equal FO `body_id` |

### Field Bus ↔ string

| ID | Role string |
|----|-------------|
| 0x01 | `host` |
| 0x02 | `optical` |
| 0x03 | `hall-sensor` |
| 0x04 | `actuator` |
| 0x05 | `compute` |
| 0x06 | `expansion` |

Instance form: `optical-01`, `hall-sensor-03`. Helpers: `bus_node_to_body_id`, `body_id_to_bus_node`.

### body_type

`optical` · `lattice` · `wifi_csi` · `ultrasonic` · `zvs` · `hall` · `sim` · `other`

(`hall` is additive to MetaField’s original list for the Hall array.)

### CSI regions (live)

`rssi` · `csi_mean` · `csi_peak` · `csi_energy` · `csi_spread`  
`head_fused_mean` · `head_fused_energy` · `head_fused_spread` · `head_entropy` · `head_dominant`

### Suggested Hall regions (when wired)

`hall_00` … `hall_09`

### Optical regions (stub)

`detector_00` … `detector_19`

---

## Envelope

```json
{
  "schema_version": 1,
  "type": "SHARED_BODY_SET",
  "timestamp": "…",
  "source": "throne-room.shared_body",
  "pressure": 0.42,
  "n_bodies": 2,
  "bodies": [ /* SHARED_BODY… */ ]
}
```

---

## Reverie mapping

| Reverie field | SHARED_BODY field |
|---------------|-------------------|
| `id` | `body_id` |
| `intensity` | `intensity` |
| `direction` | `direction` |
| `isVerified` | `is_verified` |
| `position` | hash-anchor or future calibrated pose |
| `lastUpdated` | `last_seen` |

Replace synthetic `disturbance_north` ids with real `body_id`s from this file.

---

## Paths already in the stack

| Path | Role |
|------|------|
| `/tmp/metafield/csi.jsonl` | FO stream |
| `/tmp/metafield/obs_digest.json` | conductor health |
| `/tmp/metafield/head_state.json` | residual / surprise |
| `/tmp/metafield/shared_bodies.json` | **this contract** |
| `/tmp/metafield/aurora_actions.jsonl` | action journal |

---

## Python

```python
from observer.shared_body import export_from_digest_inputs, bodies_from_fo_packets

envelope = export_from_digest_inputs(
    packets=recent_fo_packets,
    field_snap=ensemble.snapshot(),
    head_snap=head_state,
)
```
