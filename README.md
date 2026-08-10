# Throne Room

**Unified live Field Observer for the MetaField stack.**

The single place to watch the whole organism:

- Every `FieldObservation` stream (optical, ultrasonic/Echo, CSI, Hall, ZVS…)
- MetaField latent geometry, attractors, prediction error
- Active probe suggestions and closed-loop decisions

One coherent view instead of a pile of separate terminals.

---

## Status

**v0.2** — simulator + live Rich TUI observer.

### Quick start

```bash
pip install -r requirements.txt

# Terminal 1 – synthetic bodies
python simulator/field_observation_sim.py --file /tmp/throne.jsonl

# Terminal 2 – watch them live
python observer/live_view.py --file /tmp/throne.jsonl --from-start
```

Or pipe directly:

```bash
python simulator/field_observation_sim.py | python observer/live_view.py
```

### What you see

- Bodies grouped as panels
- Live region values + confidence
- Packet age colouring (green / yellow / red)
- Running packet count + uptime

---

## Design Intent

- Hardware-optional (ships with a solid simulator so it feels alive immediately)
- Same `FieldObservation` schema already used by `optical-body-s3`, Echo Grid, etc.
- Fast enough to feel real-time
- Clear visual hierarchy: bodies → field state → MetaField mind

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
