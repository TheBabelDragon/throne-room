# World Mirror

Persistent representation of observed environment on SHARED_BODY + BodyView.

Missing measurements are **None**, never zeroed. No invented coordinates.

```python
from agent.field_intelligence import WorldMirror
mirror = WorldMirror()
changes = mirror.ingest_body_view(view)
snap = mirror.snapshot()
```
