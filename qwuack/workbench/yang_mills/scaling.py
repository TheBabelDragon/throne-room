"""Scaling and continuum research manager.

A collection of finite-lattice observations is never equated with a proven
continuum limit. Uniformity must be argued explicitly before any continuum claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from qwuack.workbench.yang_mills.lattice import LatticeConfig
from qwuack.workbench.yang_mills.sampling import MCConfig, MCResult, run_monte_carlo


class ResultClass(str, Enum):
    SINGLE_LATTICE = "single_lattice"
    MULTI_LATTICE = "multi_lattice"
    FINITE_VOLUME = "finite_volume"
    SCALING_HYPOTHESIS = "scaling_hypothesis"
    UNIFORM_ESTIMATE = "uniform_estimate"
    CONTINUUM_LIMIT_ARGUMENT = "continuum_limit_argument"


@dataclass
class ScalingObservation:
    result_class: ResultClass
    lattices: list[dict[str, Any]]
    observable: str
    values: list[float]
    notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_class": self.result_class.value,
            "lattices": list(self.lattices),
            "observable": self.observable,
            "values": list(self.values),
            "notes": list(self.notes),
            "limitations": list(self.limitations) + [
                "not_a_proven_continuum_limit",
                "uniformity_not_established",
            ],
            "evidence_level": self.result_class.value,
            "is_proof": False,
        }


def multi_volume_plaquette_scan(
    volumes: list[tuple[int, int, int, int]],
    beta: float,
    group_name: str = "SU(2)",
    base_seed: int = 42,
    mc: MCConfig | None = None,
) -> ScalingObservation:
    """Compare mean plaquette across volumes at fixed coupling."""
    mc = mc or MCConfig(burn_in=10, measurements=20, seed=base_seed)
    results: list[MCResult] = []
    values: list[float] = []
    lattice_dicts: list[dict[str, Any]] = []
    for i, (Lx, Ly, Lz, Lt) in enumerate(volumes):
        cfg = LatticeConfig(Lx=Lx, Ly=Ly, Lz=Lz, Lt=Lt, beta=beta, group_name=group_name, seed=base_seed + i)
        mcc = MCConfig(
            burn_in=mc.burn_in,
            measurements=mc.measurements,
            sweeps_per_measurement=mc.sweeps_per_measurement,
            seed=base_seed + 1000 * i,
        )
        res = run_monte_carlo(cfg, mcc, cold=True)
        results.append(res)
        mean = sum(res.plaquette_series) / len(res.plaquette_series) if res.plaquette_series else 0.0
        values.append(mean)
        lattice_dicts.append(cfg.as_dict())

    return ScalingObservation(
        result_class=ResultClass.MULTI_LATTICE,
        lattices=lattice_dicts,
        observable="mean_plaquette",
        values=values,
        notes=["finite_volume_comparison_only"],
        limitations=[
            "no_continuum_extrapolation_performed",
            "coupling_not_tuned_to_fixed_physical_scale",
            "uniform_bound_not_claimed",
        ],
    )
