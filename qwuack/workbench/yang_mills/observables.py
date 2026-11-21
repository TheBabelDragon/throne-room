"""Gauge-invariant observables and estimators.

An observable, its Monte Carlo estimator, and its uncertainty are distinct.
No statistical result is a mathematical proof.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from qwuack.workbench.yang_mills.lattice import Lattice4D
from qwuack.workbench.yang_mills.wilson import WilsonAction, plaquette


@dataclass
class Estimator:
    """Named estimator with mean, uncertainty, and provenance."""

    name: str
    value: float
    uncertainty: float
    n_samples: int
    metadata: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "uncertainty": self.uncertainty,
            "n_samples": self.n_samples,
            "metadata": dict(self.metadata),
            "limitations": list(self.limitations),
            "is_proof": False,
            "evidence_level": "finite_lattice_estimator",
        }


def _mean_var(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    if n < 2:
        return m, 0.0
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, v


def plaquette_expectation(lat: Lattice4D) -> Estimator:
    wa = WilsonAction(lat)
    val = wa.mean_plaquette()
    return Estimator(
        name="plaquette",
        value=val,
        uncertainty=0.0,  # single-config; caller aggregates over samples
        n_samples=1,
        metadata={"group": lat.config.group_name, **lat.config.as_dict()},
        limitations=["single_configuration", "finite_lattice"],
    )


def wilson_loop(lat: Lattice4D, extent_mu: int, extent_nu: int, mu: int = 0, nu: int = 1) -> float:
    """Rectangular Wilson loop of size (extent_mu x extent_nu) averaged over lattice.

    Returns the average of (1/N) Re Tr of the loop products.
    """
    if extent_mu < 1 or extent_nu < 1:
        raise ValueError("loop extents must be positive")
    g = lat.group
    total = 0.0
    count = 0
    for i in range(lat.config.volume):
        # Path: +mu * R, +nu * T, -mu * R, -nu * T
        prod = g.identity()
        pos = i
        for _ in range(extent_mu):
            prod = g.multiply(prod, lat.get_link(pos, mu))
            pos = lat.shift(pos, mu, 1)
        for _ in range(extent_nu):
            prod = g.multiply(prod, lat.get_link(pos, nu))
            pos = lat.shift(pos, nu, 1)
        for _ in range(extent_mu):
            pos = lat.shift(pos, mu, -1)
            prod = g.multiply(prod, g.inverse(lat.get_link(pos, mu)))
        for _ in range(extent_nu):
            pos = lat.shift(pos, nu, -1)
            prod = g.multiply(prod, g.inverse(lat.get_link(pos, nu)))
        total += g.trace_normalized(prod)
        count += 1
    return total / count if count else 0.0


def connected_correlation(
    samples: list[float],
    lag: int,
) -> float:
    """Simple connected autocorrelation C(lag) = <O_t O_{t+lag}> - <O>^2.

    samples is a time series of a gauge-invariant observable across MC history.
    """
    n = len(samples)
    if n <= lag or lag < 0:
        return 0.0
    mean = sum(samples) / n
    acc = 0.0
    for i in range(n - lag):
        acc += (samples[i] - mean) * (samples[i + lag] - mean)
    return acc / (n - lag)


def gauge_invariance_test(lat: Lattice4D, rng: random.Random, n_trials: int = 3) -> dict[str, Any]:
    """Check that mean plaquette is invariant under random local gauge transforms."""
    wa = WilsonAction(lat)
    before = wa.mean_plaquette()
    deltas: list[float] = []
    for _ in range(n_trials):
        lat.random_gauge_transform(rng)
        after = wa.mean_plaquette()
        deltas.append(abs(after - before))
        before = after
    max_delta = max(deltas) if deltas else 0.0
    return {
        "max_abs_delta": max_delta,
        "passed": max_delta < 1e-8,
        "n_trials": n_trials,
        "limitations": ["numerical_tolerance", "finite_precision"],
    }
