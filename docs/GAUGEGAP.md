# GaugeGap — Yang–Mills research domain

GaugeGap is the Duck's Yang–Mills research domain inside the existing
Millennium Duck Workbench. It is **not** a separate repository and does
not replace the workbench, proof-killer, object store, or Duck agent.

## Problem

Clay Millennium Problem MATH-MP-03:

> Construct a nontrivial quantum Yang–Mills theory on four-dimensional
> spacetime for a compact simple gauge group and establish a strictly
> positive mass gap.

## Evidence levels (strictly distinct)

1. Finite lattice calculations
2. Numerical spectral estimates
3. Analytical estimates
4. Uniform estimates across spacing and volume
5. Continuum construction
6. Formal mathematical proof

**No finite lattice result, numerical gap estimate, or finite-volume
correlation may be promoted to a continuum theorem.**

## Forbidden shortcuts

- `finite_lattice_as_continuum`
- `u1_toy_as_nonabelian_ym`
- `numerical_gap_proxy_as_proof`

## What is implemented

- SU(2) as unit quaternions (group laws, unitarity, gauge action)
- 4D periodic hypercubic lattice with Wilson plaquettes
- Reproducible Metropolis Monte Carlo (explicit seeds, burn-in notes)
- Gauge-invariant observables and invariance tests
- Qualified spectral / effective-mass estimates with limitations
- Scaling observation objects that refuse continuum promotion
- Integration with Millennium pond `yang_mills` and registry `Yang_Mills`

## What is deliberately not claimed

- Continuum existence
- Positive continuum mass gap
- Solution of the Clay problem
- Complete SU(3) or generic simple-group implementation

## Commands

```bash
python -m qwuack.workbench --problem Yang_Mills --once
python -m qwuack.workbench --problem MATH-MP-03 --once
python -m qwuack.millennium --pond yang_mills --once
python -m unittest tests.test_yang_mills tests.test_duck_workbench tests.test_millennium_lab
```

See also:

- [YANG_MILLS_RESEARCH_PROTOCOL.md](YANG_MILLS_RESEARCH_PROTOCOL.md)
- [YANG_MILLS_PROOF_OBLIGATIONS.md](YANG_MILLS_PROOF_OBLIGATIONS.md)
