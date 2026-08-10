# Snake path — CSI bodies → Throne Room

How real measurements reach the observer, and where the loop can bite itself.

```
  CYD CSI ×2 (ESP-NOW senders)
        │  ESP-NOW (link-local, no IP)
        ▼
  Bridge ESP32 ×2  (old flash / standard)
  espnow_gateway.ino
        │  WiFi STA + UDP forward
        │  raw JSON bytes unchanged
        ▼
  Host LAN / switch
        │  UDP :4210
        ▼
  Throne Room  (python run.py)
        │  wifi_csi → FieldObservation
        ▼
  body panels:  <node>
    regions: rssi · csi_mean · csi_peak · csi_energy · csi_spread
```

Alternate path (no ESP-NOW):

```
  CYD / standard CSI node
        │  WiFi STA, UDP direct
        ▼
  Host :4210  →  Throne Room
```

---

## Packet contracts

### On the wire (UDP 4210) — wifi_csi

```json
{
  "node": "esp32_cyd_01",
  "timestamp": 123456,
  "rssi": -54,
  "type": "wifi_csi",
  "csi": [0.12, 0.18, … 32 floats]
}
```

### Inside Throne Room — FieldObservation (expanded)

| region       | meaning                         |
|--------------|---------------------------------|
| `rssi`       | RSSI normalised −90..−30 → 0..1 |
| `csi_mean`   | mean subcarrier amplitude       |
| `csi_peak`   | max subcarrier amplitude        |
| `csi_energy` | RMS energy                      |
| `csi_spread` | amplitude variance (motion-ish) |

`body_id` = `node` from the packet.  
If you still see `unknown`, the JSON never had `node` / `type` / `csi`.

---

## Feedback paths (the bite)

| Direction            | Port / channel | Who                          |
|----------------------|----------------|------------------------------|
| CSI → host           | UDP **4210**   | CYD / standard / gateway     |
| host → node commands | UDP **4211**   | Echo `echo_cmd` (optional)   |
| Throne Room          | view only      | does **not** command nodes yet |

Ouroboros risk:
- Two bridges both forwarding the same ESP-NOW sender → duplicate bodies / double rate.
- Gateway `TARGET_IP` pointing at a machine that re-broadcasts onto the same LAN → packet storms.
- CYD set to both ESP-NOW **and** direct UDP to host while a gateway also forwards → double ingest.

Keep **one** uplink per sensing node into `:4210`.

---

## Your described fleet

| Role                         | Count | Firmware-ish                    |
|------------------------------|-------|---------------------------------|
| ESP-NOW CYD CSI senders      | 2     | `esp32_csi_cyd.ino` / unified   |
| Bridge (old flash standard)  | 2     | `espnow_gateway.ino`            |
| Host                         | 1     | Throne Room `python run.py`     |

Checklist:
1. Each CYD has a unique `NODE_ID` (`esp32_cyd_01`, `esp32_cyd_02`).
2. Bridges: `TARGET_IP` = host IP, `TARGET_PORT` = 4210.
3. Only one bridge should peer a given CYD (or accept duplicates and filter later).
4. Host: `python run.py` (binds 0.0.0.0:4210).
5. Firewall allows UDP 4210 from bridge subnet.

---

## Why "region unknown" happened

Throne Room used to only parse FieldObservation.  
CSI nodes speak `wifi_csi`. Missing keys defaulted to `unknown` / `0.0`.

Ingest now expands `wifi_csi` automatically. After `git pull`, real node names and CSI regions should appear.
