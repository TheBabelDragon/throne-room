"""Reproducible baseline Monte Carlo for lattice gauge theory.

Burn-in completion does not imply equilibration. Thermalization and
sampling limitations are recorded explicitly.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from qwuack.workbench.yang_mills.lattice import Lattice4D, LatticeConfig
from qwuack.workbench.yang_mills.wilson import WilsonAction, plaquette


@dataclass
class MCConfig:
    burn_in: int = 20
    measurements: int = 40
    sweeps_per_measurement: int = 1
    heatbath_hits: int = 1
    seed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "burn_in": self.burn_in,
            "measurements": self.measurements,
            "sweeps_per_measurement": self.sweeps_per_measurement,
            "heatbath_hits": self.heatbath_hits,
            "seed": self.seed,
        }


@dataclass
class MCResult:
    plaquette_series: list[float]
    acceptance_rate: float
    config: LatticeConfig
    mc: MCConfig
    thermalization_notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        mean = sum(self.plaquette_series) / len(self.plaquette_series) if self.plaquette_series else 0.0
        return {
            "mean_plaquette": mean,
            "n_measurements": len(self.plaquette_series),
            "acceptance_rate": self.acceptance_rate,
            "lattice": self.config.as_dict(),
            "mc": self.mc.as_dict(),
            "thermalization_notes": list(self.thermalization_notes),
            "limitations": list(self.limitations) + [
                "burn_in_is_not_equilibration_proof",
                "finite_lattice",
                "not_continuum",
            ],
            "evidence_level": "monte_carlo_finite_lattice",
            "is_proof": False,
        }


def _staple_sum_su2(lat: Lattice4D, index: int, mu: int):
    """Sum of staples for link (index, mu). Returns a non-unit 'force' quaternion-like."""
    from qwuack.workbench.yang_mills.groups import SU2Element

    g = lat.group
    # Accumulate staples as un-normalized quaternion (w,x,y,z)
    sw = sx = sy = sz = 0.0
    for nu in range(4):
        if nu == mu:
            continue
        # Forward staple: U_nu(x+mu) U_mu(x+nu)^{-1} U_nu(x)^{-1}
        x_mu = lat.shift(index, mu, 1)
        unu_fwd = lat.get_link(x_mu, nu)
        x_nu = lat.shift(index, nu, 1)
        umu_inv = g.inverse(lat.get_link(x_nu, mu))
        unu_inv = g.inverse(lat.get_link(index, nu))
        # product of three links
        p = g.multiply(unu_fwd, umu_inv)
        p = g.multiply(p, unu_inv)
        if isinstance(p, SU2Element):
            sw += p.w
            sx += p.x
            sy += p.y
            sz += p.z
        # Backward staple: U_nu(x+mu-nu)^{-1} U_mu(x-nu)^{-1} U_nu(x-nu)
        x_mu_mnu = lat.shift(x_mu, nu, -1)
        unu_bwd_inv = g.inverse(lat.get_link(x_mu_mnu, nu))
        x_mnu = lat.shift(index, nu, -1)
        umu_bwd_inv = g.inverse(lat.get_link(x_mnu, mu))
        unu_bwd = lat.get_link(x_mnu, nu)
        q = g.multiply(unu_bwd_inv, umu_bwd_inv)
        q = g.multiply(q, unu_bwd)
        if isinstance(q, SU2Element):
            sw += q.w
            sx += q.x
            sy += q.y
            sz += q.z
    return SU2Element(sw, sx, sy, sz)


def _metropolis_link_update(lat: Lattice4D, index: int, mu: int, rng: random.Random) -> bool:
    """Single-link Metropolis update for SU(2)."""
    from qwuack.workbench.yang_mills.groups import SU2Element

    g = lat.group
    beta = lat.config.beta
    old = lat.get_link(index, mu)
    # Propose a small random rotation
    prop = g.multiply(old, g.random(rng))
    # Delta S from plaquettes involving this link ≈ -beta * (Tr_new - Tr_old) staples
    staple = _staple_sum_su2(lat, index, mu)
    # Re Tr(U * staple) for SU(2) unit quaternion: 2 * (U · staple) in quaternion sense
    # Using normalized trace of product
    def re_tr_prod(u: SU2Element, s: SU2Element) -> float:
        # product u*s, then w component (normalized trace is w for unit, but staple not unit)
        w = u.w * s.w - u.x * s.x - u.y * s.y - u.z * s.z
        return w  # proportional to Re Tr

    old_dot = re_tr_prod(old, staple)
    new_dot = re_tr_prod(prop, staple)
    # Delta action ~ -beta * (new_dot - old_dot) with conventional factor 1 for SU(2) toy
    delta_s = -beta * (new_dot - old_dot)
    if delta_s <= 0 or rng.random() < math.exp(-delta_s):
        lat.set_link(index, mu, prop)
        return True
    return False


def sweep(lat: Lattice4D, rng: random.Random) -> float:
    """One full lattice sweep; returns acceptance fraction."""
    accepted = 0
    total = 0
    for i in range(lat.config.volume):
        for mu in range(4):
            if _metropolis_link_update(lat, i, mu, rng):
                accepted += 1
            total += 1
    return accepted / total if total else 0.0


def run_monte_carlo(config: LatticeConfig, mc: MCConfig, cold: bool = True) -> MCResult:
    """Reproducible MC run. Does not claim equilibration."""
    rng = random.Random(mc.seed)
    lat = Lattice4D(config)
    if cold:
        lat.cold_start()
    else:
        lat.hot_start(rng)

    accept_acc = 0.0
    n_sweeps = 0
    for _ in range(mc.burn_in):
        accept_acc += sweep(lat, rng)
        n_sweeps += 1

    series: list[float] = []
    wa = WilsonAction(lat)
    for _ in range(mc.measurements):
        for _ in range(mc.sweeps_per_measurement):
            accept_acc += sweep(lat, rng)
            n_sweeps += 1
        series.append(wa.mean_plaquette())

    acceptance = accept_acc / n_sweeps if n_sweeps else 0.0
    notes = [
        f"burn_in={mc.burn_in} sweeps completed; equilibration not proven",
        "acceptance rate is diagnostic only",
    ]
    limitations = [
        "single_chain",
        "no_independent_thermalization_test",
        "Metropolis_toy_update",
        "finite_volume",
    ]
    return MCResult(
        plaquette_series=series,
        acceptance_rate=acceptance,
        config=config,
        mc=mc,
        thermalization_notes=notes,
        limitations=limitations,
    )
