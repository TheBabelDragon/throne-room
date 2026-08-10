# Aurora action layer

Full-auto nameable action plane over real observations.

```
CSI bodies → metafield_bridge → JSONL + obs_digest
                                    │
                                    ▼
                         aurora.action_layer
                                    │
              ┌──────────┼──────────┐
              │                     │
         file journal          Redis (optional)
    aurora_actions.jsonl            │
                          ESCAPE / mode / pubsub
```

## Principles

1. **Fail-closed** — no Redis or ESCAPE set → intents may be logged, never dispatched.
2. **ESCAPE is sovereign** — `aurora:control:escape=1` freezes fire path immediately.
3. **Observation does not require action** — Throne + bridge keep running either way.
4. **Rate limits** — priority floor + per-action cooldown.

## Redis keys

| Key / channel | Role |
|---------------|------|
| `aurora:control:escape` | Kill switch (`1` = freeze) |
| `aurora:control:mode` | `observe` \| `cautious` \| `auto` |
| `aurora:control:heartbeat` | Layer liveness (TTL) |
| `aurora:action:out` | Pub/sub of fired actions |
| `aurora:swarm:commands` | Compatible with wifi-sensing command listener |
| `aurora:action:state` | Last decision snapshot |

## Run

```bash
# playground — no Redis required
python -m aurora.action_layer --file-only --mode auto

# live control plane
export REDIS_URL=redis://127.0.0.1:6379/0
redis-cli set aurora:control:mode cautious
python -m aurora.action_layer --mode cautious

# ESCAPE
redis-cli set aurora:control:escape 1
# clear
redis-cli del aurora:control:escape
```

With the full stack:

```bash
python -m observer.startup          # terminal A
python -m aurora.action_layer       # terminal B
```

## Actions emitted

| type | meaning |
|------|---------|
| `probe` | elevated CSI — request focus / more samples |
| `attention` | variance spike |
| `scale_down` | obs path degraded |
| `hold` | bridge/path failure |

Bodies never receive power or motion commands from this layer without a separate actuator bridge. This is the **decision + broadcast** surface.
