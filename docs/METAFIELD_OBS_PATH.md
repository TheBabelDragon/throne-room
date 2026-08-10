# MetaField observation path

Real CSI measurements → MetaField memory.

```
CYD CSI ×2  ──ESP-NOW──►  bridge ESP32 ×2  ──UDP :4210──►  host
                                                      │
                    ┌──────────────────────┼────────────────────┐
                    │                                     │
                    ▼                                     ▼
             Throne Room                          metafield_bridge
             (live view)                          (schema expand)
                                                          │
                                                          ▼
                                               /tmp/metafield/csi.jsonl
                                                          │
                                                          ▼
                                      metafield/optical_serial_consumer.py
                                          --file … --follow --save …
                                                          │
                                                          ▼
                                               FieldMemoryEntry store
                                               (MetaField episodic memory)
```

## Wire formats

| Hop | Schema |
|-----|--------|
| CYD / gateway → host | `wifi_csi` `{node,rssi,csi[32],type}` |
| bridge → JSONL | **MetaField** `FieldObservation` (`body_type: wifi_csi`, `field_regions[…]`) |
| consumer → store | `FieldMemoryEntry` |

## Run

Terminal A — observe (optional):

```bash
cd ~/projects/throne-room
python run.py
```

Terminal B — MetaField path:

```bash
cd ~/projects/throne-room
python -m observer.metafield_bridge --udp --out /tmp/metafield/csi.jsonl
```

Terminal C — MetaField consumer:

```bash
cd ~/projects/metafield
source .venv/bin/activate
python optical_serial_consumer.py \
  --file /tmp/metafield/csi.jsonl --follow \
  --save /tmp/metafield/field_memory.jsonl
```

## Regions published per CSI packet

`rssi` · `csi_mean` · `csi_peak` · `csi_energy` · `csi_spread`

Raw subcarriers stay in `modality.wifi_csi.csi` for later geometry / replay.
