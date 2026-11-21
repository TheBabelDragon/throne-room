# Yang–Mills research protocol

## Governing principle

The Duck may discover evidence, propose mathematics, challenge arguments,
and remember failure. It may **not** confuse computational success with
mathematical truth.

## Experimental progression

1. **Legacy U(1) baseline** — historical toy; labeled `u1_wilson_finite`.
   Never treated as non-Abelian Yang–Mills.
2. **SU(2) finite lattice** — Wilson action, Metropolis sampling,
   gauge-invariant observables. Family `su2_wilson_finite`.
3. **Spectral estimates** — effective-mass proxies from correlators,
   always tagged with lattice parameters and `not_continuum_mass_gap`.
4. **Scaling scans** — multi-volume comparisons. Result class remains
   `multi_lattice` until uniformity is established (currently open).
5. **Formal obligations** — see YANG_MILLS_PROOF_OBLIGATIONS.md.

## Reproducibility requirements

Every numerical artifact must record:

- gauge group
- lattice dimensions
- coupling β
- boundary conditions
- seed
- burn-in and measurement counts
- known limitations

Burn-in completion does **not** imply equilibration.

## Promotion rules

| From | To | Allowed? |
|------|-----|----------|
| Finite lattice | Continuum construction | No |
| Numerical m_eff > 0 | Continuum mass gap | No |
| U(1) toy | Non-Abelian YM | No |
| Single volume | Uniform bound | No |
| Statistical fit | Theorem | No |
| Formal certificate + checker PASS | FORMALLY_VERIFIED | Yes |


## Active pond path (v0.2)

1. `yang_mills_experiment` emits prize rejection, U(1) legacy, SU(2) finite evidence.
2. ProofKiller admits finite SU(2) as VERIFIED/PROGRESS computational evidence.
3. ProofKiller rejects U(1)-as-non-Abelian, finite-as-continuum, gap-proxy-as-proof.
4. Workbench `proof()` for Yang_Mills mints RESULT (computational_evidence) + REJECTED promotion claims — never proof-bearing lemmas from numerics alone.
5. Formal PASS requires a real certificate; placeholders are not certificates.
