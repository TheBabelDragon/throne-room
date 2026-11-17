"""mpmath-backed reference for zeta / Hardy Z / known zeros.

Provenance:
  - Odlyzko tables / well-known first ordinates (validated against mpmath.zetazero)
  - Hardy Z via mpmath.siegelz
  - zeta via mpmath.zeta

Finite numerical checks are not a proof of RH.
"""

from __future__ import annotations

from typing import Any

import mpmath as mp

REFERENCE_ENGINE_VERSION = "spectral-ref.mpmath.v1"
FIXTURE_SET_VERSION = "spectral-fixtures.v0.3"

ODLYZKO_ZEROS: list[float] = [
    14.134725141734693,
    21.022039638771556,
    25.01085758014569,
    30.424876125859513,
    32.93506158773919,
    37.586178158825675,
    40.918719012147495,
    43.327073280915,
    48.00515088116716,
    49.7738324776723,
    52.97032147771446,
    56.44624769706339,
    59.34704400260235,
    60.83177852436781,
    65.1125440480816,
    67.07981052949417,
    69.54640171117398,
    72.0671576744819,
    75.70469069908393,
    77.1448400688748,
]


def set_precision(dps: int = 25) -> int:
    prev = int(mp.mp.dps)
    mp.mp.dps = int(dps)
    return prev


def hardy_z_reference(t: float, *, dps: int = 25) -> dict[str, Any]:
    set_precision(dps)
    tt = mp.mpf(t)
    Z = mp.siegelz(tt)
    return {
        "t": float(t),
        "Z": float(Z),
        "Z_str": mp.nstr(Z, min(dps, 20)),
        "abs_Z": float(abs(Z)),
        "dps": dps,
        "method": "mpmath.siegelz",
        "engine": REFERENCE_ENGINE_VERSION,
        "finite": mp.isfinite(Z),
    }


def zeta_reference(sigma: float, t: float, *, dps: int = 25) -> dict[str, Any]:
    set_precision(dps)
    s = mp.mpc(sigma, t)
    z = mp.zeta(s)
    return {
        "sigma": float(sigma),
        "t": float(t),
        "re": float(z.real),
        "im": float(z.imag),
        "abs": float(abs(z)),
        "dps": dps,
        "method": "mpmath.zeta",
        "engine": REFERENCE_ENGINE_VERSION,
        "finite": mp.isfinite(z),
    }


def zero_ordinate_reference(index: int, *, dps: int = 30) -> dict[str, Any]:
    set_precision(dps)
    if index < 1:
        raise ValueError("index must be >= 1")
    z = mp.zetazero(index)
    return {
        "index": index,
        "t": float(z.imag),
        "t_str": mp.nstr(z.imag, min(dps, 20)),
        "sigma": float(z.real),
        "dps": dps,
        "method": "mpmath.zetazero",
        "engine": REFERENCE_ENGINE_VERSION,
        "provenance": "mpmath.zetazero; consistent with Odlyzko tables for small n",
    }


def evaluate_fixture_point(fixture: dict[str, Any]) -> dict[str, Any]:
    kind = fixture.get("kind") or fixture.get("classification")
    dps = int(fixture.get("precision_dps") or fixture.get("dps") or 25)
    t = float(fixture["t"])
    out: dict[str, Any] = {
        "fixture_id": fixture.get("fixture_id"),
        "kind": kind,
        "t": t,
        "dps": dps,
    }
    if kind in ("hardy_z", "nonzero_point", "near_zero", "known_zero", "zero_ordinate"):
        out["reference"] = hardy_z_reference(t, dps=dps)
    elif kind == "zeta_critical":
        out["reference"] = zeta_reference(0.5, t, dps=dps)
    else:
        out["reference"] = hardy_z_reference(t, dps=dps)
    return out
