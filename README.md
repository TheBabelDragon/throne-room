# Throne Room

**Operational live Field Observer for the MetaField stack.**

One place to watch every body and stream:

- Optical, ultrasonic/Echo, CSI, Hall, ZVS…
- Live values + sparklines
- Packet rate, active / stalled status
- File, stdin, and UDP (Echo Grid compatible on port 4210)

---

## Quick start

```bash
git clone https://github.com/TheBabelDragon/throne-room.git
cd throne-room
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# full demo (no install -e needed)
python run.py --demo
```

Ctrl+C exits cleanly with no traceback.

### Optional: install as a command

```bash
pip install -e .
throne --demo          # same as run.py --demo
throne --udp
throne --file /tmp/throne.jsonl --from-start
```

### Operational modes

```bash
# watch a JSONL stream (MetaField / Echo / real nodes)
python run.py --file /tmp/throne.jsonl --from-start

# listen for Echo Grid / CSI on UDP 4210
python run.py --udp

# both at once
python run.py --file /tmp/throne.jsonl --udp
```

---

## What you see

| Element          | Meaning                                      |
|------------------|----------------------------------------------|
| Body panels      | One panel per `body_id`                      |
| ● colour         | Green = fresh, yellow = aging, red = stalled |
| Sparkline        | Recent value history                         |
| Header rate      | Packets per second                           |
| Active / stalled | Bodies seen in last 5 s vs older             |

---

## Architecture note

Throne Room is the **observer**, not the runtime.

| Component              | Launch from                   |
|------------------------|-------------------------------|
| This live view         | `throne-room/`                |
| MetaField lattice      | `metafield/`                  |
| Echo Grid / ultrasonic | `echo-grid-ultrasonic-os/`    |
| Optical / Hall / ZVS   | their respective node repos   |
| field-bus              | `field-bus/` + node firmwares |

Bodies emit `FieldObservation` packets.  
Throne Room makes them visible as one organism.

---

## Status

**v0.4.1 — operational + hardened**

- Multi-source ingest (file · stdin · UDP)
- Sparklines + rate + health colouring
- Clean Ctrl+C (no traceback)
- Works without `pip install -e .`
- Robust file tail (handles rotation)

### Next

- MetaField latent + attractor surface
- Active-probe decisions in the same view
- Optional web surface

---

*The control surface for a distributed physical-field intelligence.*
