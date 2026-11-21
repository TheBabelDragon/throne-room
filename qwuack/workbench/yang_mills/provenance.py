"""Experiment provenance and configuration hashing for GaugeGap.

Experiment identity is distinct from execution identity. Missing configuration
is never silently filled into historical evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "gaugegap.experiment.v1"
SAMPLER_NAME = "metropolis_staple_su2_toy"
SAMPLER_VERSION = "0.2.1"
SOFTWARE_VERSION = "gaugegap-0.2.1"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ExperimentConfig:
    """Deterministic, serializable experiment configuration."""

    experiment_id: str
    group: str = "SU(2)"
    Lx: int = 4
    Ly: int = 4
    Lz: int = 4
    Lt: int = 4
    beta: float = 2.0
    boundary: str = "periodic"
    seed: int = 0
    rng_algorithm: str = "python_random_MT19937"
    sampler: str = SAMPLER_NAME
    sampler_version: str = SAMPLER_VERSION
    thermalization_sweeps: int = 15
    measurement_sweeps: int = 30
    measurement_interval: int = 1
    cold_start: bool = True
    schema_version: str = SCHEMA_VERSION
    software_version: str = SOFTWARE_VERSION

    def __post_init__(self) -> None:
        if self.group not in {"SU(2)", "SU2"}:
            raise ValueError(f"unsupported group for this sampler: {self.group}")
        if min(self.Lx, self.Ly, self.Lz, self.Lt) < 2:
            raise ValueError("lattice extents must be >= 2")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.thermalization_sweeps < 0 or self.measurement_sweeps < 1:
            raise ValueError("invalid sweep counts")

    def canonical_dict(self) -> dict[str, Any]:
        """Stable key order for hashing."""
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "group": self.group,
            "Lx": self.Lx,
            "Ly": self.Ly,
            "Lz": self.Lz,
            "Lt": self.Lt,
            "beta": self.beta,
            "boundary": self.boundary,
            "seed": self.seed,
            "rng_algorithm": self.rng_algorithm,
            "sampler": self.sampler,
            "sampler_version": self.sampler_version,
            "thermalization_sweeps": self.thermalization_sweeps,
            "measurement_sweeps": self.measurement_sweeps,
            "measurement_interval": self.measurement_interval,
            "cold_start": self.cold_start,
            "software_version": self.software_version,
        }

    def config_hash(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        d = self.canonical_dict()
        d["config_hash"] = self.config_hash()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        return cls(**payload)


@dataclass
class ExecutionRecord:
    """One run of an experiment configuration."""

    config_hash: str
    experiment_id: str
    execution_id: str
    started_at: str
    finished_at: str = ""
    acceptance_rate: float | None = None
    mean_plaquette: float | None = None
    n_measurements: int = 0
    evidence_class: str = "PLAQUETTE_OBSERVABLE"
    limitations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_hash": self.config_hash,
            "experiment_id": self.experiment_id,
            "execution_id": self.execution_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at or utcnow(),
            "acceptance_rate": self.acceptance_rate,
            "mean_plaquette": self.mean_plaquette,
            "n_measurements": self.n_measurements,
            "evidence_class": self.evidence_class,
            "limitations": list(self.limitations),
            "notes": list(self.notes),
            "is_proof": False,
            "is_continuum": False,
        }


def validate_provenance(data: dict[str, Any]) -> list[str]:
    """Return list of missing required provenance fields."""
    required = [
        "group",
        "seed",
        "beta",
        "config_hash",
        "sampler",
        "schema_version",
    ]
    missing = [k for k in required if k not in data or data[k] in (None, "")]
    if not any(k in data for k in ("Lx", "L", "lattice_dims", "lattice")):
        missing.append("lattice")
    return missing


def config_hash_matches(data: dict[str, Any]) -> bool:
    """True if stored hash matches recomputed hash from known fields."""
    try:
        cfg = ExperimentConfig.from_dict(data)
    except (TypeError, ValueError, KeyError):
        return False
    expected = data.get("config_hash")
    if not expected:
        return False
    return cfg.config_hash() == expected
