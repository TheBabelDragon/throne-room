"""Typed schemas and evidence-level tags for GaugeGap research objects."""

from __future__ import annotations

from enum import Enum


class EvidenceLevel(str, Enum):
    FINITE_LATTICE = "finite_lattice"
    NUMERICAL_SPECTRAL = "numerical_spectral_estimate"
    ANALYTICAL_ESTIMATE = "analytical_estimate"
    UNIFORM_ESTIMATE = "uniform_estimate"
    CONTINUUM_CONSTRUCTION = "continuum_construction"
    FORMAL_PROOF = "formal_proof"


class ObligationState(str, Enum):
    OPEN = "OPEN"
    EXPLORING = "EXPLORING"
    CONJECTURED = "CONJECTURED"
    EXPERIMENTAL = "EXPERIMENTAL"
    CONDITIONALLY_ESTABLISHED = "CONDITIONALLY_ESTABLISHED"
    FORMALLY_VERIFIED = "FORMALLY_VERIFIED"
    BLOCKED = "BLOCKED"


FORBIDDEN_SHORTCUTS = (
    "finite_lattice_as_continuum",
    "u1_toy_as_nonabelian_ym",
    "numerical_gap_proxy_as_proof",
    "single_volume_as_uniform_bound",
    "statistical_fit_as_theorem",
    "unsupported_group_generalization",
)
