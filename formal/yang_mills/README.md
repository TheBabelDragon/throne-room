# Formal interface — Yang–Mills / GaugeGap

Lean is **not** a mandatory runtime dependency of the Duck workbench.

This directory records:

- Formalization scope
- Definitions suitable for independent formalization
- Proof-obligation mapping
- Certificate format expectations
- Verification status

## Scope (initial)

Elementary identities only:

- SU(2) group laws (associativity, inverse, identity) as unit quaternions
- Lattice indexing / periodic boundary statements

## Forbidden

- Fake mass-gap theorems whose axioms assume Δ > 0
- Marking FORMALLY_VERIFIED without a real checker certificate

## Status

No formal certificates are issued by this branch.
