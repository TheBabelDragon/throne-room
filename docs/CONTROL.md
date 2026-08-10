# Intelligent control

`python -m observer.startup` is the conductor.

It starts and supervises the observation stack end-to-end, writes an Aurora-facing digest, and fail-closes when MetaField / Redis are absent.

## Sequence

```
1. prepare /tmp/metafield/
2. metafield_bridge   ← owns UDP :4210, writes CSI FieldObservation JSONL
3. throne live view   ← tails same JSONL (no second bind)
4. torch_display      ← closed-loop HUD (optional, --torch / --full)
5. optical_serial_consumer  ← promote to FieldMemoryEntry (if MetaField found)
6. aurora_action      ← policies + Redis escape (optional, --action / --full)
7. Aurora digest loop ← /tmp/metafield/obs_digest.json + optional metafield_sensing tick
```

## Launch

```bash
cd ~/projects/throne-room
git pull

# full throne-up (bridge + view + torch + Aurora)
python -m observer.startup --full

# explicit MetaField root
python -m observer.startup --full --metafield-root ~/projects/metafield

# bridge + digest only
python -m observer.startup --no-view --no-consumer --no-torch
```

Environment:

| Var | Meaning |
|-----|---------|
| `METAFIELD_ROOT` | Path to MetaField checkout |
| `THRONE_TORCH=1` | Enable torch HUD without `--torch` |

## Aurora digest

Every 2.5 s control writes `/tmp/metafield/obs_digest.json`:

```json
{
  "type": "OBS_PATH_DIGEST",
  "aurora_rev": "file-digest-v2+pressure+host",
  "health": "ok|degraded",
  "obs_path": { "csi_lines": …, "memory_lines": … },
  "children": { "metafield_bridge": {"alive": true}, … },
  "field": { "pressure": 0.0, "n_bodies": 0 },
  "host": { "cpu_pct": …, "advice": "ok|scale_down|hold" },
  "measurement": { "sample_hz": 8, "fine_len": 720 }
}
```

`memory_lines` is a **live count**, not a placeholder cap. History rings use `FINE_LEN` / `DISPLAY_LEN` only.

## Ownership rules

- **One** UDP :4210 owner → the bridge under control
- View / torch / consumer are followers on JSONL
- Required child (bridge) auto-restarts; optional children do not tight-loop
- Ctrl+C kills the whole tree cleanly

## Escape

```bash
redis-cli set aurora:control:escape 1   # fail-closed hold
redis-cli del aurora:control:escape     # clear
```
