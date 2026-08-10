# Throne Room

**Operational live Field Observer + intelligent control for the MetaField stack.**

Watches **real, taken measurements** from physical field bodies and can start the full observation path through MetaField digest / Aurora.

---

## Full stack (recommended)

```bash
cd ~/projects/throne-room
git pull
source .venv/bin/activate   # or: python -m venv .venv && pip install -r requirements.txt

# conductor: CSI bridge → view → MetaField memory → Aurora digest
python -m observer.startup
```

Auto-discovers `../metafield` or `METAFIELD_ROOT`.  
Bridge owns UDP **:4210**. View tails the JSONL. Digest → `/tmp/metafield/obs_digest.json`.

See [docs/CONTROL.md](docs/CONTROL.md).

---

## View only

```bash
python run.py --file /tmp/metafield/csi.jsonl --from-start
# or raw UDP (only if nothing else binds 4210)
python run.py --udp
```

---

## What you see

| Element          | Meaning                                      |
|------------------|----------------------------------------------|
| Body panels      | One panel per real `body_id`                 |
| ● colour         | Green = fresh, yellow = aging, red = stalled |
| Battleship spark | Measurement intensity over time              |
| Header rate      | Packets per second                           |

CSI nodes expand to: `rssi` · `csi_mean` · `csi_peak` · `csi_energy` · `csi_spread`.

---

## Paths

| Doc | Content |
|-----|---------|
| [docs/CONTROL.md](docs/CONTROL.md) | Startup sequence + Aurora digest |
| [docs/SNAKE_PATH.md](docs/SNAKE_PATH.md) | CYD → bridge → host |
| [docs/METAFIELD_OBS_PATH.md](docs/METAFIELD_OBS_PATH.md) | CSI → FieldMemory |

Synthetic generators live under `dev/` only — not operational.

---

*The control surface for a distributed physical-field intelligence.*
