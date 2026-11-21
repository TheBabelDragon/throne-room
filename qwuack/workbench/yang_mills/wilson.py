"""Wilson action and plaquette observables.

U_{mu nu}(x) is the oriented product of four links around a plaquette.
The Wilson action uses the group-normalized real part of the trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qwuack.workbench.yang_mills.lattice import Lattice4D


def plaquette(lat: Lattice4D, index: int, mu: int, nu: int) -> Any:
    """Oriented plaquette product U_mu(x) U_nu(x+mu) U_mu(x+nu)^{-1} U_nu(x)^{-1}."""
    g = lat.group
    umu = lat.get_link(index, mu)
    x_mu = lat.shift(index, mu, 1)
    unu_at_mu = lat.get_link(x_mu, nu)
    x_nu = lat.shift(index, nu, 1)
    umu_at_nu_inv = g.inverse(lat.get_link(x_nu, mu))
    unu_inv = g.inverse(lat.get_link(index, nu))
    # Product of the four oriented links
    p = g.multiply(umu, unu_at_mu)
    p = g.multiply(p, umu_at_nu_inv)
    p = g.multiply(p, unu_inv)
    return p


@dataclass
class WilsonAction:
    """Wilson gauge action S = beta * sum_P (1 - (1/N) Re Tr U_P)."""

    lattice: Lattice4D

    def plaquette_value(self, index: int, mu: int, nu: int) -> float:
        """Normalized (1/N) Re Tr U_P in [typically -1, 1]."""
        p = plaquette(self.lattice, index, mu, nu)
        return self.lattice.group.trace_normalized(p)

    def mean_plaquette(self) -> float:
        lat = self.lattice
        total = 0.0
        count = 0
        for i in range(lat.config.volume):
            for mu in range(4):
                for nu in range(mu + 1, 4):
                    total += self.plaquette_value(i, mu, nu)
                    count += 1
        return total / count if count else 0.0

    def action(self) -> float:
        """Total Wilson action (extensive)."""
        lat = self.lattice
        beta = lat.config.beta
        s = 0.0
        for i in range(lat.config.volume):
            for mu in range(4):
                for nu in range(mu + 1, 4):
                    s += 1.0 - self.plaquette_value(i, mu, nu)
        return beta * s

    def action_density(self) -> float:
        vol = self.lattice.config.volume
        return self.action() / vol if vol else 0.0
