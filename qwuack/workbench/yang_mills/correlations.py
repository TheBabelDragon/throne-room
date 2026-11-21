"""Gauge-invariant correlation measurements at explicit separations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qwuack.workbench.yang_mills.observables import Estimator, connected_correlation


@dataclass
class CorrelationRecord:
    observable: str
    separations: list[int]
    values: list[float]
    uncertainties: list[float]
    n_samples: int
    metadata: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "observable": self.observable,
            "separations": list(self.separations),
            "values": list(self.values),
            "uncertainties": list(self.uncertainties),
            "n_samples": self.n_samples,
            "metadata": dict(self.metadata),
            "limitations": list(self.limitations) + [
                "finite_lattice",
                "not_a_continuum_result",
                "not_a_proof",
            ],
            "evidence_level": "finite_volume_correlation",
        }


def autocorrelation_function(series: list[float], max_lag: int) -> CorrelationRecord:
    lags = list(range(max_lag + 1))
    vals = [connected_correlation(series, lag) for lag in lags]
    return CorrelationRecord(
        observable="mc_autocorrelation",
        separations=lags,
        values=vals,
        uncertainties=[0.0] * len(lags),
        n_samples=len(series),
        limitations=["naive_estimator", "no_binning"],
    )
