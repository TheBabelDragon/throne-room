"""Spectral analysis layer for Euclidean correlators.

Positive finite-lattice effective-mass estimates do NOT imply a continuum mass gap.
Every estimate records its full experimental context and known limitations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpectralEstimate:
    """Qualified spectral estimate — never promoted to continuum theorem."""

    gauge_group: str
    lattice_dims: tuple[int, int, int, int]
    coupling: float
    boundary: str
    observable: str
    separation_range: tuple[int, int]
    sample_count: int
    seed: int
    fit_model: str
    value: float | None
    uncertainty: float | None
    stable: bool
    limitations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "gauge_group": self.gauge_group,
            "lattice_dims": list(self.lattice_dims),
            "coupling": self.coupling,
            "boundary": self.boundary,
            "observable": self.observable,
            "separation_range": list(self.separation_range),
            "sample_count": self.sample_count,
            "seed": self.seed,
            "fit_model": self.fit_model,
            "value": self.value,
            "uncertainty": self.uncertainty,
            "stable": self.stable,
            "limitations": list(self.limitations) + [
                "finite_lattice_only",
                "not_continuum_mass_gap",
                "not_a_mathematical_proof",
            ],
            "notes": list(self.notes),
            "evidence_level": "numerical_spectral_estimate",
            "is_proof": False,
        }


def effective_mass_from_ratio(c_t: float, c_t1: float) -> float | None:
    """m_eff(t) ~ log(C(t)/C(t+1)) when both positive."""
    if c_t <= 0 or c_t1 <= 0:
        return None
    ratio = c_t / c_t1
    if ratio <= 0:
        return None
    return math.log(ratio)


def estimate_effective_mass(
    correlator: list[float],
    *,
    gauge_group: str,
    lattice_dims: tuple[int, int, int, int],
    coupling: float,
    boundary: str,
    observable: str,
    sample_count: int,
    seed: int,
    t_min: int = 1,
    t_max: int | None = None,
) -> SpectralEstimate:
    """Produce a qualified effective-mass estimate or mark fit as unstable."""
    n = len(correlator)
    if t_max is None:
        t_max = max(1, n // 2)
    t_max = min(t_max, n - 2)
    masses: list[float] = []
    for t in range(t_min, t_max + 1):
        m = effective_mass_from_ratio(correlator[t], correlator[t + 1])
        if m is not None and math.isfinite(m):
            masses.append(m)

    limitations = [
        "fit_window_sensitivity",
        "finite_volume",
        "statistical_noise",
        "positive_m_eff_is_not_continuum_gap",
    ]
    if len(masses) < 2:
        return SpectralEstimate(
            gauge_group=gauge_group,
            lattice_dims=lattice_dims,
            coupling=coupling,
            boundary=boundary,
            observable=observable,
            separation_range=(t_min, t_max),
            sample_count=sample_count,
            seed=seed,
            fit_model="log_ratio_effective_mass",
            value=None,
            uncertainty=None,
            stable=False,
            limitations=limitations + ["unstable_or_insufficient_signal"],
            notes=["failed_or_unstable_fit_is_valid_research_output"],
        )

    mean = sum(masses) / len(masses)
    var = sum((m - mean) ** 2 for m in masses) / max(1, len(masses) - 1)
    unc = math.sqrt(var / len(masses))
    # Heuristic stability: relative spread not huge
    stable = (unc / abs(mean) < 0.5) if abs(mean) > 1e-12 else False

    return SpectralEstimate(
        gauge_group=gauge_group,
        lattice_dims=lattice_dims,
        coupling=coupling,
        boundary=boundary,
        observable=observable,
        separation_range=(t_min, t_max),
        sample_count=sample_count,
        seed=seed,
        fit_model="log_ratio_effective_mass",
        value=mean,
        uncertainty=unc,
        stable=stable,
        limitations=limitations,
        notes=["single_volume", "no_continuum_extrapolation"],
    )
