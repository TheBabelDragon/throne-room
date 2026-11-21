"""Statistical diagnostics for GaugeGap observables.

Uncertainty estimates are never mathematical proof certificates.
Insufficient sampling is reported explicitly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StatSummary:
    mean: float | None
    variance: float | None
    stderr: float | None
    n: int
    n_eff: float | None
    tau_int: float | None
    classification: str  # OK | INSUFFICIENT_EVIDENCE
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "variance": self.variance,
            "stderr": self.stderr,
            "n": self.n,
            "n_eff": self.n_eff,
            "tau_int": self.tau_int,
            "classification": self.classification,
            "limitations": list(self.limitations) + [
                "statistical_estimate_not_a_proof",
            ],
            "is_proof": False,
        }


def mean_variance(xs: list[float]) -> tuple[float | None, float | None]:
    n = len(xs)
    if n == 0:
        return None, None
    m = sum(xs) / n
    if n < 2:
        return m, None
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, v


def autocorrelation(xs: list[float], lag: int) -> float:
    n = len(xs)
    if n <= lag or lag < 0 or n < 2:
        return 0.0
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i + lag] - m) for i in range(n - lag))
    den = sum((x - m) ** 2 for x in xs)
    if den <= 0:
        return 0.0
    return num / den


def integrated_autocorr_time(xs: list[float], max_lag: int | None = None) -> float | None:
    """Naive tau_int = 1/2 + sum rho(t). Stops at first non-positive rho."""
    n = len(xs)
    if n < 4:
        return None
    if max_lag is None:
        max_lag = max(1, n // 4)
    tau = 0.5
    for lag in range(1, max_lag + 1):
        rho = autocorrelation(xs, lag)
        if rho <= 0:
            break
        tau += rho
    return max(0.5, tau)


def summarize_series(xs: list[float], min_samples: int = 8) -> StatSummary:
    n = len(xs)
    limitations = ["naive_autocorr", "no_binning"]
    if n < min_samples:
        return StatSummary(
            mean=None if n == 0 else sum(xs) / n,
            variance=None,
            stderr=None,
            n=n,
            n_eff=None,
            tau_int=None,
            classification="INSUFFICIENT_EVIDENCE",
            limitations=limitations + ["n_below_min_samples"],
        )
    m, v = mean_variance(xs)
    tau = integrated_autocorr_time(xs)
    n_eff = (n / (2 * tau)) if tau and tau > 0 else float(n)
    if v is None or m is None:
        return StatSummary(
            mean=m, variance=v, stderr=None, n=n, n_eff=n_eff, tau_int=tau,
            classification="INSUFFICIENT_EVIDENCE",
            limitations=limitations,
        )
    stderr = math.sqrt(v / max(n_eff, 1.0))
    classification = "OK" if n_eff >= min_samples / 2 else "INSUFFICIENT_EVIDENCE"
    if classification != "OK":
        limitations.append("effective_sample_size_low")
    return StatSummary(
        mean=m, variance=v, stderr=stderr, n=n, n_eff=n_eff, tau_int=tau,
        classification=classification, limitations=limitations,
    )
