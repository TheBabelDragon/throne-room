# Throne Room

**Unified live Field Observer for the MetaField stack.**

The single place to watch the whole organism:

- Every `FieldObservation` stream (optical, ultrasonic/Echo, CSI, Hall, ZVS…)
- MetaField latent geometry, attractors, prediction error
- Active probe suggestions and closed-loop decisions

One coherent view instead of a pile of separate terminals.

---

## Status

**v0.1** — skeleton + working FieldObservation simulator.

```bash
# fire synthetic bodies
python simulator/field_observation_sim.py

# or write to a JSONL file MetaField can already consume
python simulator/field_observation_sim.py --file /tmp/throne.jsonl
```

Next up: live ingest + first visual surface.

## Design Intent

- Hardware-optional (ships with a solid simulator so it feels alive immediately)
- Same `FieldObservation` schema already used by `optical-body-s3`, Echo Grid, etc.
- Fast enough to feel real-time
- Clear visual hierarchy: bodies → field state → MetaField mind

## Quick Links

- [MetaField](https://github.com/TheBabelDragon/metafield)
- [Echo Grid Ultrasonic OS](https://github.com/TheBabelDragon/echo-grid-ultrasonic-os)
- [field-bus](https://github.com/TheBabelDragon/field-bus)
- [optical-body-s3](https://github.com/TheBabelDragon/optical-body-s3)

---

*The control surface for a distributed physical-field intelligence.*
