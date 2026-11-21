"""Evidence classifications for GaugeGap spectral and observable results.

Plaquette autocorrelation is never a glueball correlator.
Effective-mass estimates are never continuum mass-gap theorems.
"""

from __future__ import annotations

from enum import Enum


class EvidenceClass(str, Enum):
    PLAQUETTE_OBSERVABLE = "PLAQUETTE_OBSERVABLE"
    PLAQUETTE_AUTOCORRELATION = "PLAQUETTE_AUTOCORRELATION"
    GLUEBALL_CORRELATOR = "GLUEBALL_CORRELATOR"
    EFFECTIVE_MASS_ESTIMATE = "EFFECTIVE_MASS_ESTIMATE"
    SPECTRAL_EVIDENCE = "SPECTRAL_EVIDENCE"
    FINITE_LATTICE_MC = "FINITE_LATTICE_MC"


# Backward-compatible mapping from legacy family / evidence_level strings
LEGACY_MAP = {
    "su2_wilson_finite": EvidenceClass.FINITE_LATTICE_MC,
    "u1_wilson_finite": EvidenceClass.FINITE_LATTICE_MC,
    "finite_lattice": EvidenceClass.FINITE_LATTICE_MC,
    "numerical_spectral_estimate": EvidenceClass.EFFECTIVE_MASS_ESTIMATE,
    "monte_carlo_finite_lattice": EvidenceClass.FINITE_LATTICE_MC,
}


def classify_legacy(family: str | None = None, evidence_level: str | None = None) -> EvidenceClass:
    if evidence_level and evidence_level in LEGACY_MAP:
        return LEGACY_MAP[evidence_level]
    if family and family in LEGACY_MAP:
        return LEGACY_MAP[family]
    return EvidenceClass.FINITE_LATTICE_MC


# Forbidden promotions
FORBIDDEN_PROMOTIONS = {
    (EvidenceClass.PLAQUETTE_AUTOCORRELATION, EvidenceClass.GLUEBALL_CORRELATOR),
    (EvidenceClass.PLAQUETTE_OBSERVABLE, EvidenceClass.GLUEBALL_CORRELATOR),
    (EvidenceClass.EFFECTIVE_MASS_ESTIMATE, "CONTINUUM_MASS_GAP"),
    (EvidenceClass.PLAQUETTE_AUTOCORRELATION, "CONTINUUM_MASS_GAP"),
}


def promotion_allowed(source: EvidenceClass, target: str) -> bool:
    if (source, target) in FORBIDDEN_PROMOTIONS:
        return False
    if target in {"CONTINUUM_MASS_GAP", "FORMAL_THEOREM", "CONTINUUM_CONSTRUCTION"}:
        return False
    return True
