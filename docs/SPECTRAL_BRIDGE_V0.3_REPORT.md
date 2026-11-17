# Spectral Bridge v0.3 — Numerical Convergence Report

**Parent:** `validate/spectral-bridge-v0.2` @ `f49396161a868b833e69907ddcf312f404d0b5e3`  
**Branch:** `validate/spectral-bridge-v0.3`  
**Reference engine:** spectral-ref.mpmath.v1 (`mpmath.siegelz` / `zetazero`)  
**Fixture set:** spectral-fixtures.v0.3

## Commands executed

```bash
PYTHONPATH=. python -m qwuack.spectral_ref.run_v03
# counts: PASS=0 FAIL=27

PYTHONPATH=. python -m unittest tests.test_spectral_ref_v03 -v
# 9 pass, 0 fail
```

## Classification counts (executed)

```json
{"PASS": 0, "FAIL": 27, "INCONCLUSIVE": 0, "NUMERICAL_INSTABILITY": 0, "REFERENCE_UNAVAILABLE": 0}
```

## Hardy Z at known zeros (production vs |Z|→0)

| fixture | t | production Z | |Z| vs 0 | class |
|---------|---|--------------|---------|-------|
| known_zero_01 | 14.134725 | -0.31434 | 0.314 | **FAIL** |
| known_zero_02 | 21.022040 | -0.25028 | 0.250 | **FAIL** |
| known_zero_03 | 25.010858 | -0.97113 | 0.971 | **FAIL** |
| known_zero_04 | 30.424876 | 0.25099 | 0.251 | **FAIL** |
| known_zero_05 | 32.935062 | 0.18038 | 0.180 | **FAIL** |

Reference |Z| at these ordinates is ~1e-15 (mpmath dps=25).

**Root cause:** production Riemann–Siegel remainder is algorithmic approximation error at low height — not float64 roundoff. Precision escalation (dps 15/25/40) stagnates at the same residual.

## Zero-finder offsets (first 5 Odlyzko)

| n | expected | detected | |offset| | class |
|---|----------|----------|---------|-------|
| 1 | 14.1347 | 14.5348 | 0.400 | **FAIL** |
| 2 | 21.0220 | 20.8194 | 0.203 | **FAIL** |
| 3 | 25.0109 | 25.1327 | 0.122 | **FAIL** |
| 4 | 30.4249 | 30.6132 | 0.188 | **FAIL** |
| 5 | 32.9351 | 32.8019 | 0.133 | **FAIL** |

Finder does not inject known zeros; offsets follow from inaccurate Z sign-changes.

## Nonzero relative residuals (rel_tol=0.05)

All six synthetic points **FAIL** (rel residual 0.09–0.64).

## Notes

- Finite numerical verification is **not** a proof of RH.
- FAIL means numerical acceptance criteria were not met.
- Cross-engine agreement ≠ correctness.
- Formal proof semantics unchanged.
