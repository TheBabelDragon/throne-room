# What was extracted from TribStruct / YapBeast

## Kept (engineering)

| Pattern | Where it landed |
|---------|-----------------|
| 3×3×3 soft energy lattice + decay | `observer/field_cube.py` |
| Multi-cube ensemble + path propagation | `FieldCubeEnsemble` (snake path) |
| Composite intensity from mass+peak+activity | `field_pressure()` |
| Host CPU/mem watchdog → throttle advice | `observer/host_guard.py` |
| Signed/structured JSONL event ledger idea | already: `aurora_actions.jsonl`, FO memory |
| TTL cache for expensive state builds | digest interval in `startup.py` |
| Command registry style | Aurora modes + CLI flags |

## Discarded (not measurement)

- Crypto mining (stratum, ethash, DAG, pool connectors)
- Hebrew / angelic cipher, gematria, codon tables as logic
- Pantheon / personality shard / "Pimpin Prime" narrative
- Fractal string generators as output text
- Self-rewriting source / immortal evolution loops
- AVSpeech pitch theatre

## Why path propagation matters here

The CSI snake is already ordered:

```
CYD senders → ESP-NOW → bridge ESP32s → host :4210 → throne JSONL
```

Cube path transfer models **cross-body heat bleed** along that order without
claiming mystical meaning. Useful for detecting when one node lights up and
neighbors follow (shared multipath), vs isolated noise.
