# GaugeGap evidence model

Schema version: `gaugegap.experiment.v1`

## Classifications

| Class | Meaning |
|-------|---------|
| PLAQUETTE_OBSERVABLE | Finite-lattice Wilson plaquette measurement |
| PLAQUETTE_AUTOCORRELATION | MC-time autocorrelation of plaquette series |
| GLUEBALL_CORRELATOR | Spatial/temporal correlator of glueball operators (interface only; not claimed validated) |
| EFFECTIVE_MASS_ESTIMATE | Numerical m_eff from a correlator ratio |
| SPECTRAL_EVIDENCE | Broader spectral analysis product |
| FINITE_LATTICE_MC | Generic finite-lattice Monte Carlo run |

## Permitted transitions

- MC run → PLAQUETTE_OBSERVABLE
- Plaquette series → PLAQUETTE_AUTOCORRELATION (diagnostic only)
- Valid correlator → EFFECTIVE_MASS_ESTIMATE (with fit assumptions)

## Forbidden transitions

- PLAQUETTE_AUTOCORRELATION → GLUEBALL_CORRELATOR
- EFFECTIVE_MASS_ESTIMATE → continuum mass-gap theorem
- Any numerical class → FORMALLY_VERIFIED without checker certificate
- U(1) legacy → non-Abelian SU(2) claim

## Proof status

Evidence accumulation is monotonic. Proof status is never inferred from
numerical confidence. Only a valid mathematical certificate may support
formal promotion.
