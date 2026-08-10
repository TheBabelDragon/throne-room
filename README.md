# Throne Room

**Unified live Field Observer for the MetaField stack.**

The single place to *watch* the whole organism.  
(It does **not** replace MetaField, Echo, or the physical nodes — it is the control surface that looks at all of them.)

---

## Launch from here

```bash
cd throne-room
pip install -r requirements.txt

# One-command demo (simulator + live view)
python run.py --demo
```

That’s the easiest way to see everything working.

### Other useful launches

```bash
# Watch an existing JSONL stream (e.g. from MetaField / Echo / real nodes)
python run.py --file /tmp/throne.jsonl --from-start

# Or the classic two-terminal way
python simulator/field_observation_sim.py --file /tmp/throne.jsonl
python run.py --file /tmp/throne.jsonl --from-start
```

### What still launches from their own repos

| Component              | Launch from                          |
|------------------------|--------------------------------------|
| MetaField lattice      | `metafield/`                         |
| Echo Grid / ultrasonic | `echo-grid-ultrasonic-os/`           |
| Optical / Hall / ZVS   | their respective `*-s3` or node repos |
| field-bus firmware     | `field-bus/` + each node project     |
| **This view**          | **`throne-room/`** ← you are here    |

Throne Room is the conglomerated *observer*, not the conglomerated *runtime*.

---

## Status

**v0.3** — simulator + live Rich TUI + single-entry `run.py`

### What you see

- Bodies grouped as panels
- Live region values + confidence
- Packet age colouring (green / yellow / red)
- Running packet count + uptime

## Next

- UDP / serial ingest
- MetaField latent + attractor surface
- Active probe decisions visible in the same view

## Quick Links

- [MetaField](https://github.com/TheBabelDragon/metafield)
- [Echo Grid Ultrasonic OS](https://github.com/TheBabelDragon/echo-grid-ultrasonic-os)
- [field-bus](https://github.com/TheBabelDragon/field-bus)
- [optical-body-s3](https://github.com/TheBabelDragon/optical-body-s3)

---

*The control surface for a distributed physical-field intelligence.*
