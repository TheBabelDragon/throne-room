# GaugeGap — Yang–Mills research domain

GaugeGap is the Duck's Yang–Mills research domain inside the existing
Millennium Duck Workbench. It is **not** a separate repository.

## Problem

Clay Millennium Problem MATH-MP-03:

> Construct a nontrivial quantum Yang–Mills theory on four-dimensional
> spacetime for a compact simple gauge group and establish a strictly
> positive mass gap.

## Active experiment path

```
python -m qwuack.millennium --pond yang_mills --once
  → ponds.yang_mills_experiment
    → U(1) legacy baseline (explicitly labeled, not non-Abelian)
    → qwuack.workbench.yang_mills.research.run_baseline_experiment (SU(2))
    → Artifact(s) with finite-lattice metadata
  → ProofKiller (YM category-error defenses)
  → Workbench ingestion (computational evidence only; no proof promotion)
```

## Evidence levels (strictly distinct)

1. Finite lattice calculations
2. Numerical spectral estimates
3. Analytical estimates
4. Uniform estimates across spacing and volume
5. Continuum construction
6. Formal mathematical proof

**No finite lattice result, numerical gap estimate, or finite-volume
correlation may be promoted to a continuum theorem.**

## Forbidden shortcuts (registry + killer)

- `finite_lattice_as_continuum`
- `u1_toy_as_nonabelian_ym`
- `numerical_gap_proxy_as_proof`
- `finite_scaling_as_continuum_proof`
- `missing_su2_provenance`

## What is implemented

- SU(2) unit quaternions, 4D lattice, Wilson action, Metropolis MC
- Gauge-invariant observables and invariance tests
- Qualified spectral estimates with limitations
- Pond integration: active path is **finite SU(2)**; U(1) is legacy only
- Proof-killer YM category-error rejections
- Workbench policy: numerical YM evidence never becomes a proof-bearing lemma

## Commands

```bash
python -m qwuack.workbench --problem Yang_Mills --once
python -m qwuack.workbench --problem MATH-MP-03 --once
python -m qwuack.millennium --pond yang_mills --once
python -m unittest tests.test_yang_mills tests.test_duck_workbench tests.test_millennium_lab
```
