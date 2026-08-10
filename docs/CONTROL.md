# Intelligent control (where there was none)

`python -m observer.startup` is the conductor.

It starts and supervises the observation stack end-to-end, writes an Aurora-facing digest, and fail-closes when MetaField / Redis are absent.

## Sequence

```
1. prepare /tmp/metafield/
2. metafield_bridge   ← owns UDP :4210, writes CSI FieldObservation JSONL
3. throne live view   ← tails same JSONL (no second bind)
4. optical_serial_consumer  ← promote to FieldMemoryEntry (if MetaField found)
5. Aurora digest loop ← /tmp/metafield/obs_digest.json + optional metafield_sensing tick
```

## Launch

```bash
cd ~/projects/throne-room
git pull

# full stack (auto-discovers ../metafield)
python -m observer.startup

# explicit MetaField root
python -m observer.startup --metafield-root ~/projects/metafield

# bridge + digest only
python -m observer.startup --no-view --no-consumer
```

Environment:

| Var | Meaning |
|-----|---------|
| `METAFIELD_ROOT` | Path to MetaField checkout |

## Aurora rev (file digest)

Every few seconds control writes:

`/tmp/metafield/obs_digest.json`

```json
{
  "type": "OBS_PATH_DIGEST",
  "aurora_rev": "file-digest-v1",
  "health": "ok|degraded",
  "obs_path": { "csi_lines": …, "memory_lines": … },
  "children": { "metafield_bridge": {"alive": true}, … },
  "metafield_stats": { "health": "…", "live": false }
}
```

If MetaField is present, it also calls `aurora_mods.metafield_sensing.on_sensing_tick()` (read-only).

No Redis required. When Aurora Swarm later consumes digests, this file is the stable contract.

## Ownership rules

- **One** UDP :4210 owner → the bridge under control
- View and consumer are followers on JSONL
- Required child (bridge) auto-restarts; optional children do not tight-loop
