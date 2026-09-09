# Qwuack

Stay on `main`.

`python -m observer.startup --full` starts the CSI conductor.
It does **not** start the Duck.

This starts the Duck:

```bash
cd ~/throne-room || cd ~/projects/throne-room
git checkout main
git pull --ff-only origin main
source .venv/bin/activate
python -m qwuack.startup
```

You should immediately see `QWUACK STARTUP` and a pid. If you do not,
you are in the wrong repo or on `quack-tenant`.

Leave it running. Ctrl+C writes state and stops.

One batch:

```bash
python -m qwuack.startup --once
```

Sleep:

```bash
mkdir -p /tmp/metafield
nohup python -m qwuack.startup --interval 5 > /tmp/metafield/qwuack_desk.log 2>&1 &
```

Recover:

```bash
cat /tmp/metafield/qwuack_desk.pid
tail -20 /tmp/metafield/qwuack_desk.log
tail -5 /tmp/metafield/qwuack_memory.jsonl
```
