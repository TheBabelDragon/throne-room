# Qwuack

Tenant of Throne Room. Not a landlord. Not a Millennium solver.

`--runtime` means stay up. `--once` is the only polite exit.
`--full` does **not** start Qwuack and does **not** give it UDP :4210.

Stay on `main`.

## Start the Duck

Overnight math desk:

```bash
git checkout main
git pull --ff-only origin main
python -m qwuack --runtime --desk math
```

One batch, then exit:

```bash
python -m qwuack --runtime --desk math --once
```

Field tenant:

```bash
python -m qwuack --runtime
python -m qwuack.runtime --live --follow
```

Leave the math desk running while you sleep. It grows the named Collatz
horizon when a range claim survives, loosens a killed bound, and keeps
killing the unbounded prize sentence. Ctrl+C writes state and stops.

State:

- `/tmp/metafield/qwuack_desk.json`
- `/tmp/metafield/qwuack_desk_state.json`
- `/tmp/metafield/qwuack_memory.jsonl`
