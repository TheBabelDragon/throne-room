"""Research entrypoint for GaugeGap / Yang–Mills domain.

Produces explicitly qualified experimental artifacts. Never claims solution
of the Clay problem.
"""

from __future__ import annotations

import random
from typing import Any

from qwuack.workbench.yang_mills.lattice import Lattice4D, LatticeConfig
from qwuack.workbench.yang_mills.observables import gauge_invariance_test, plaquette_expectation
from qwuack.workbench.yang_mills.sampling import MCConfig, run_monte_carlo
from qwuack.workbench.yang_mills.spectrum import estimate_effective_mass
from qwuack.workbench.yang_mills.wilson import WilsonAction
from qwuack.workbench.yang_mills.provenance import (
    ExperimentConfig, ExecutionRecord, utcnow, validate_provenance,
)
from qwuack.workbench.yang_mills.stats import summarize_series
from qwuack.workbench.yang_mills.evidence_types import EvidenceClass


def run_baseline_experiment(
    generation: int = 0,
    *,
    L: int = 4,
    beta: float = 2.0,
    seed: int | None = None,
    burn_in: int = 15,
    measurements: int = 30,
) -> dict[str, Any]:
    """SU(2) finite-lattice baseline. All results are computational evidence only."""
    seed = 2000 + generation if seed is None else seed
    config = LatticeConfig(
        Lx=L, Ly=L, Lz=L, Lt=L,
        beta=beta,
        group_name="SU(2)",
        seed=seed,
    )
    mc = MCConfig(burn_in=burn_in, measurements=measurements, seed=seed)
    result = run_monte_carlo(config, mc, cold=True)

    rng = random.Random(seed + 7)
    lat = Lattice4D(config)
    lat.hot_start(rng)
    inv = gauge_invariance_test(lat, rng, n_trials=2)

    mean_p = sum(result.plaquette_series) / len(result.plaquette_series) if result.plaquette_series else 0.0

    series = result.plaquette_series
    corr = []
    for lag in range(min(8, len(series))):
        if len(series) <= lag:
            corr.append(0.0)
            continue
        m = sum(series) / len(series)
        acc = sum((series[i] - m) * (series[i + lag] - m) for i in range(len(series) - lag))
        corr.append(acc / max(1, len(series) - lag))

    spectral = estimate_effective_mass(
        corr,
        gauge_group="SU(2)",
        lattice_dims=config.dims,
        coupling=beta,
        boundary="periodic",
        observable="plaquette_mc_autocorr_proxy",
        sample_count=measurements,
        seed=seed,
        t_min=1,
        t_max=min(4, len(corr) - 2),
    )

    exp_cfg = ExperimentConfig(
        experiment_id=f"su2-L{L}-b{beta}-s{seed}",
        group="SU(2)",
        Lx=L, Ly=L, Lz=L, Lt=L,
        beta=beta,
        seed=seed,
        thermalization_sweeps=burn_in,
        measurement_sweeps=measurements,
    )
    stats = summarize_series(result.plaquette_series)
    exec_rec = ExecutionRecord(
        config_hash=exp_cfg.config_hash(),
        experiment_id=exp_cfg.experiment_id,
        execution_id=f"{exp_cfg.experiment_id}@{utcnow()}",
        started_at=utcnow(),
        finished_at=utcnow(),
        acceptance_rate=result.acceptance_rate,
        mean_plaquette=mean_p,
        n_measurements=len(result.plaquette_series),
        evidence_class=EvidenceClass.PLAQUETTE_OBSERVABLE.value,
        limitations=list(result.limitations) + list(stats.limitations),
        notes=["sampler=metropolis_staple_su2_toy"],
    )
    provenance = {
        **exp_cfg.as_dict(),
        **exec_rec.as_dict(),
        "stats": stats.as_dict(),
        "spectral_evidence_class": EvidenceClass.EFFECTIVE_MASS_ESTIMATE.value,
        "plaquette_autocorr_class": EvidenceClass.PLAQUETTE_AUTOCORRELATION.value,
        "not_glueball_correlator": True,
    }
    missing = validate_provenance(provenance)
    if missing:
        provenance["provenance_gaps"] = missing

    return {
        "family": "su2_wilson_finite",
        "group": "SU(2)",
        "lattice": config.as_dict(),
        "mc": result.as_dict(),
        "mean_plaquette": mean_p,
        "gauge_invariance": inv,
        "spectral_estimate": spectral.as_dict(),
        "evidence_level": "finite_lattice",
        "evidence_class": EvidenceClass.FINITE_LATTICE_MC.value,
        "is_continuum": False,
        "is_proof": False,
        "limitations": [
            "finite_lattice",
            "single_volume",
            "not_a_mass_gap_proof",
            "not_continuum_construction",
            "U(1)_legacy_is_separate_baseline",
            "plaquette_autocorr_is_not_glueball_correlator",
            "metropolis_staple_su2_toy_sampler",
        ],
        "generation": generation,
        "seed": seed,
        "provenance": provenance,
        "config_hash": exp_cfg.config_hash(),
        "L": L,
        "beta": beta,
        "sampler": exp_cfg.sampler,
        "schema_version": exp_cfg.schema_version,
    }
