# SU(2) numerical method (GaugeGap)

## Group representation

SU(2) elements are unit quaternions `(w,x,y,z)` with `w²+x²+y²+z²=1`.
Multiplication is quaternion product; inverse is conjugate; Haar sampling
is 4D Gaussian projection onto S³.

## Lattice

4D periodic hypercubic lattice. Links store group elements. Plaquettes
are oriented products of four links.

## Sampler

`metropolis_staple_su2_toy` v0.2.1

- Single-link Metropolis updates driven by a staple sum.
- **Simplification:** staple force and ΔS use a proportional Re Tr product
  suitable for diagnostics, not production lattice QCD quality.
- Burn-in completion does **not** prove equilibration.
- Acceptance rate is diagnostic only.

## Observables

- Mean plaquette (gauge-invariant)
- Rectangular Wilson loops
- MC plaquette autocorrelation (diagnostic; **not** a glueball correlator)

## Validation

Unit tests cover group laws, unitarity, gauge invariance of the mean
plaquette, seed reproducibility, and Wilson-loop cold-start identity.
Passing unit tests does **not** constitute physical validation of the sampler.
