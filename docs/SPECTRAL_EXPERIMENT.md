# Spectral Experiment Ingestion

## Contract

Signal Processor exports `spectral_experiment.v1` JSON records.

Throne Room imports them via:

```python
from qwuack.workbench.spectral_pond import SpectralPond
pond = SpectralPond()
pond.ingest_path("path/to/experiment.json")
print(pond.render_desk())
```

## Flow

```
Signal Processor
    → QuantumWaveEngine / RiemannSpectralEngine
    → spectral_experiment.v1
    → offline JSON file
    → Throne Room SpectralPond.ingest
    → MathObject (EXPERIMENT / RESULT / HYPOTHESIS / COUNTEREXAMPLE)
    → append-only /tmp/metafield/ journals
```

No mandatory network service. Offline JSON first.

## Boundaries

- Finite numerical verification is **not** a proof of RH.
- `verification.formal` is never set to `PASS` from numerical evidence alone.
- `MathObject.is_proof` remains false for all imported spectral objects.
- Existing Riemann pond in `qwuack.millennium.ponds` is unchanged.
- Duck does not receive `act.device` or unrestricted execution.

## Tests

```bash
python -m unittest tests.test_spectral_import
```
