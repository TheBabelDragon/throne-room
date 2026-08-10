# Throne Room

**Operational live Field Observer for the MetaField stack.**

Watches **real, taken measurements** from physical field bodies:

- Optical, ultrasonic/Echo, CSI, Hall, ZVS…
- Live values + sparklines
- Packet rate, active / stalled status
- File, stdin, and UDP (Echo Grid compatible on port 4210)

Synthetic data is not part of the operational path.

---

## Quick start

```bash
git clone https://github.com/TheBabelDragon/throne-room.git
cd throne-room
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Observe real streams

```bash
# default: listen for live UDP on 4210 (Echo Grid / CSI)
python run.py

# or explicit
python run.py --udp
python run.py --udp 4210

# tail a live JSONL feed from a real body / MetaField consumer
python run.py --file /tmp/optical.jsonl --from-start

# multiple real sources at once
python run.py --file /tmp/optical.jsonl --udp
```

Ctrl+C exits cleanly.

### Optional install

```bash
pip install -e .
throne              # same as run.py (UDP 4210 by default)
throne --file /tmp/optical.jsonl --from-start
```

---

## What you see

| Element          | Meaning                                      |
|------------------|----------------------------------------------|
| Body panels      | One panel per real `body_id`                 |
| ● colour         | Green = fresh, yellow = aging, red = stalled |
| Sparkline        | Recent value history                         |
| Header rate      | Packets per second                           |
| Active / stalled | Bodies seen in last 5 s vs older             |

---

## Architecture

Throne Room is the **observer** of taken measurements, not a simulator.

| Component              | Role / launch from            |
|------------------------|-------------------------------|
| **Throne Room**        | Live view of real streams     |
| MetaField              | Lattice + memory (`metafield/`) |
| Echo Grid              | Ultrasonic / CSI body         |
| optical / hall / zvs   | Physical field nodes          |
| field-bus              | Shared CAN-FD protocol        |

Bodies emit `FieldObservation` packets from real sensors.  
Throne Room makes the organism visible.

---

## Dev only

`dev/field_observation_sim.py` generates synthetic packets for plumbing tests.  
It is **not** an operational mode and must not be treated as measurement data.

---

## Status

**v0.5 — real-measurement only**

- No `--demo` path
- Default = live UDP 4210
- Multi-source ingest (file · stdin · UDP)
- Sparklines + rate + health colouring
- Clean Ctrl+C

### Next

- MetaField latent + attractor surface
- Active-probe decisions in the same view
- Optional web surface

---

*The control surface for a distributed physical-field intelligence.*
