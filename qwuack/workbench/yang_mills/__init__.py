"""GaugeGap — Yang–Mills research domain for the Duck workbench.

Finite lattice calculations, numerical spectral estimates, analytical
estimates, scaling studies, and formal-proof obligations are distinct
levels of evidence. No finite lattice result is a continuum theorem.
"""

from __future__ import annotations

from qwuack.workbench.yang_mills.groups import SU2, GaugeGroup, group_for
from qwuack.workbench.yang_mills.lattice import Lattice4D, LatticeConfig
from qwuack.workbench.yang_mills.wilson import WilsonAction, plaquette
from qwuack.workbench.yang_mills.observables import (
    plaquette_expectation,
    wilson_loop,
    connected_correlation,
)
from qwuack.workbench.yang_mills.research import run_baseline_experiment

__all__ = [
    "SU2",
    "GaugeGroup",
    "group_for",
    "Lattice4D",
    "LatticeConfig",
    "WilsonAction",
    "plaquette",
    "plaquette_expectation",
    "wilson_loop",
    "connected_correlation",
    "run_baseline_experiment",
]
