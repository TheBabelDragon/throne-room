"""SU(2) GaugeGap pond experiment (active path) + U(1) legacy baseline.

Imported by qwuack.millennium.ponds. Neither path is a continuum mass-gap proof.
"""

from __future__ import annotations

import math
import random

from qwuack.millennium.artifacts import Artifact, ArtifactKind


def _art(pond, kind, name, statement, status, generation, evidence, recipe=None, notes=None):
    return Artifact(
        pond=pond, kind=kind, name=name, statement=statement, status=status,
        generation=generation, evidence=evidence, recipe=recipe or {}, notes=notes or [],
    )


def _prize(pond, sentence, generation):
    return _art(
        pond, ArtifactKind.REJECTION, "prize_sentence", sentence, "REJECTED", generation,
        {"unbounded": True, "named": False, "declares_prize_solved": False},
        notes=["unbounded_not_an_experiment"],
    )


def _u1_legacy_baseline(generation, seed):
    """Historical U(1) toy — preserved as legacy baseline, never as non-Abelian YM."""
    L, beta = 4 + generation % 3, 0.8
    local = random.Random(seed)
    plaquettes = [math.cos(local.uniform(-math.pi, math.pi) / (1 + beta)) for _ in range(L * L)]
    mean_p = sum(plaquettes) / len(plaquettes)
    c1 = sum(plaquettes[i] * plaquettes[(i + 1) % len(plaquettes)] for i in range(len(plaquettes))) / len(plaquettes)
    c2 = sum(plaquettes[i] * plaquettes[(i + 2) % len(plaquettes)] for i in range(len(plaquettes))) / len(plaquettes)
    gap = max(0.0, math.log(max(abs(c1), 1e-9) / max(abs(c2), 1e-9)))
    return L, beta, mean_p, c1, c2, gap


def yang_mills_experiment(generation, rng):
    """Yang–Mills research path: U(1) legacy + SU(2) finite lattice.

    Neither is continuum Yang–Mills. Neither is a mass-gap proof.
    """
    out = [_prize("yang_mills", "continuum quantum Yang-Mills has a mass gap", generation)]

    seed_u1 = 1000 + generation
    L, beta, mean_p, c1, c2, gap = _u1_legacy_baseline(generation, seed_u1)
    out.append(_art(
        "yang_mills", ArtifactKind.EVIDENCE, "u1_lattice_gap_proxy",
        f"U(1) Wilson toy L={L} beta={beta} seed={seed_u1} gap_proxy={gap:.4g} [LEGACY BASELINE]",
        "VERIFIED" if gap > 0 else "PROGRESS", generation,
        {
            "named": True, "L": L, "beta": beta, "seed": seed_u1,
            "mean_plaquette": mean_p, "c1": c1, "c2": c2, "gap_proxy": gap,
            "family": "u1_wilson_finite", "group": "U(1)",
            "is_nonabelian": False, "is_continuum": False,
            "evidence_level": "finite_lattice", "legacy_baseline": True,
        },
        notes=["u1_toy_not_nonabelian_ym", "not_a_mass_gap_proof"],
    ))

    try:
        from qwuack.workbench.yang_mills.research import run_baseline_experiment

        su2 = run_baseline_experiment(
            generation, L=4, beta=2.0, seed=3000 + generation, burn_in=8, measurements=12,
        )
        mean_plaq = su2["mean_plaquette"]
        inv = su2.get("gauge_invariance", {})
        spectral = su2.get("spectral_estimate", {})
        out.append(_art(
            "yang_mills", ArtifactKind.EVIDENCE, "su2_wilson_finite_lattice",
            (
                f"SU(2) Wilson L=4 beta=2.0 seed={su2['seed']} "
                f"mean_plaquette={mean_plaq:.4g} "
                f"gauge_inv_ok={inv.get('passed')} "
                f"[FINITE LATTICE ONLY]"
            ),
            "VERIFIED" if inv.get("passed") else "PROGRESS",
            generation,
            {
                "named": True, "L": 4, "beta": 2.0, "seed": su2["seed"],
                "group": "SU(2)", "mean_plaquette": mean_plaq,
                "gauge_invariance": inv, "spectral_estimate": spectral,
                "family": "su2_wilson_finite", "is_nonabelian": True,
                "is_continuum": False, "evidence_level": "finite_lattice",
                "is_proof": False,
            },
            recipe={"experiment": "run_baseline_experiment", "L": 4, "beta": 2.0},
            notes=[
                "finite_lattice_not_continuum",
                "numerical_gap_proxy_not_proof",
                "not_a_clay_solution",
            ],
        ))
        out.append(_art(
            "yang_mills", ArtifactKind.TRANSFORM, "wilson_plaquette_su2",
            "SU(2) Wilson plaquette is a finite-lattice observable; continuum limit is not admitted",
            "PROGRESS", generation,
            {"named": True, "L": 4, "beta": 2.0, "group": "SU(2)", "family": "su2_wilson_finite"},
            notes=["continuum_construction_open"],
        ))
        out.append(_art(
            "yang_mills", ArtifactKind.REJECTION, "reject_finite_as_continuum",
            "promote SU(2) L=4 mean plaquette to continuum Yang–Mills existence",
            "REJECTED", generation,
            {
                "named": True, "L": 4, "group": "SU(2)",
                "forbidden_shortcut": "finite_lattice_as_continuum",
                "family": "su2_wilson_finite",
            },
            notes=["forbidden_shortcut:finite_lattice_as_continuum"],
        ))
        out.append(_art(
            "yang_mills", ArtifactKind.REJECTION, "reject_numerical_gap_as_proof",
            "promote finite-lattice effective-mass proxy to continuum mass-gap theorem",
            "REJECTED", generation,
            {
                "named": True, "L": 4, "group": "SU(2)",
                "forbidden_shortcut": "numerical_gap_proxy_as_proof",
                "spectral": spectral, "family": "su2_wilson_finite",
            },
            notes=["forbidden_shortcut:numerical_gap_proxy_as_proof"],
        ))
    except Exception as exc:  # pragma: no cover
        out.append(_art(
            "yang_mills", ArtifactKind.FAILED_STRATEGY, "su2_domain_unavailable",
            f"SU(2) GaugeGap domain raised: {type(exc).__name__}: {exc}",
            "PROGRESS", generation,
            {"named": True, "error": str(exc), "family": "su2_wilson_finite"},
            notes=["domain_import_or_runtime_failure"],
        ))

    out.append(_art(
        "yang_mills", ArtifactKind.TRANSFORM, "wilson_plaquette",
        "Wilson plaquette is the finite lattice observable; continuum limit is not admitted",
        "PROGRESS", generation, {"named": True, "L": L, "beta": beta},
    ))
    return out
