"""Canonical Clay / extra-pond registry.

The Millennium Problems are not seven cute buttons. Each entry encodes
what a legitimate solution would even be, and what shortcuts are forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProblemSpec:
    id: str
    key: str
    title: str
    domain: str
    status: str
    statement: str
    target_type: str
    objective: tuple[str, ...]
    allowed_claims: tuple[str, ...]
    forbidden_shortcuts: tuple[str, ...]
    acceptable_completion: tuple[str, ...]
    pond: str
    definitions: tuple[tuple[str, str], ...] = ()
    known_facts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "title": self.title,
            "domain": self.domain,
            "status": self.status,
            "statement": self.statement,
            "target_type": self.target_type,
            "objective": list(self.objective),
            "allowed_claims": list(self.allowed_claims),
            "forbidden_shortcuts": list(self.forbidden_shortcuts),
            "acceptable_completion": list(self.acceptable_completion),
            "pond": self.pond,
            "definitions": [{"name": n, "text": t} for n, t in self.definitions],
            "known_facts": list(self.known_facts),
        }


_COMMON_ALLOWED = (
    "proof",
    "disproof",
    "reduction",
    "lemma",
    "counterexample",
    "conditional_result",
    "computational_evidence",
)


MILLENNIUM: dict[str, ProblemSpec] = {
    "P_vs_NP": ProblemSpec(
        id="MATH-MP-01",
        key="P_vs_NP",
        title="P versus NP",
        domain="computational_complexity",
        status="open",
        statement=(
            "Is every language decidable in nondeterministic polynomial time "
            "also decidable in deterministic polynomial time?"
        ),
        target_type="theorem",
        objective=("prove_P_eq_NP", "prove_P_neq_NP"),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=(
            "finite_sat_batch_as_proof",
            "heuristic_solver_as_poly_algorithm",
            "average_case_only",
        ),
        acceptable_completion=("rigorous_proof", "rigorous_disproof"),
        pond="p_vs_np",
        definitions=(
            ("P", "languages decided by a deterministic TM in time n^O(1)"),
            ("NP", "languages decided by a nondeterministic TM in time n^O(1)"),
            ("polynomial_reduction", "many-one reduction computable in time n^O(1)"),
        ),
        known_facts=(
            "2SAT is in P via implication-graph SCCs",
            "3SAT is NP-complete",
            "P \u2286 NP is immediate from the definitions",
        ),
    ),
    "Riemann": ProblemSpec(
        id="MATH-MP-02",
        key="Riemann",
        title="Riemann Hypothesis",
        domain="analytic_number_theory",
        status="open",
        statement="Every non-trivial zero of the Riemann zeta function has real part 1/2.",
        target_type="theorem",
        objective=("prove_all_nontrivial_zeros_have_real_part_half",),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=(
            "finite_numerical_verification",
            "named_height_window_as_proof",
            "off_line_sample_as_disproof",
        ),
        acceptable_completion=("rigorous_proof", "rigorous_disproof"),
        pond="rh",
        definitions=(
            ("zeta", "analytic continuation of sum n^{-s} for Re(s)>1"),
            ("nontrivial_zero", "zero of zeta with 0 < Re(s) < 1"),
            ("critical_line", "the line Re(s) = 1/2"),
        ),
        known_facts=(
            "first zero near t=14.134725 on the critical line",
            "Hardy Z(t) changes sign at zeros on the critical line",
            "no zeros on Re(s)=1 (Hadamard–de la Vallée Poussin)",
        ),
    ),
    "Yang_Mills": ProblemSpec(
        id="MATH-MP-03",
        key="Yang_Mills",
        title="Yang–Mills Existence and Mass Gap",
        domain="mathematical_physics",
        status="open",
        statement=(
            "Prove that for any compact simple gauge group, a non-trivial quantum "
            "Yang–Mills theory exists on R^4 and has a mass gap \u0394 > 0."
        ),
        target_type="theorem",
        objective=("construct_continuum_ym", "prove_mass_gap"),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=(
            "finite_lattice_as_continuum",
            "u1_toy_as_nonabelian_ym",
            "numerical_gap_proxy_as_proof",
        ),
        acceptable_completion=("rigorous_proof",),
        pond="yang_mills",
        definitions=(
            ("wilson_action", "lattice gauge action from plaquette traces"),
            ("mass_gap", "strictly positive infimum of the spectrum above the vacuum"),
        ),
        known_facts=(
            "lattice Yang–Mills is well-defined at finite spacing",
            "continuum limit is the missing object",
        ),
    ),
    "Navier_Stokes": ProblemSpec(
        id="MATH-MP-04",
        key="Navier_Stokes",
        title="Navier–Stokes Existence and Smoothness",
        domain="PDE",
        status="open",
        statement=(
            "For the 3D incompressible Navier–Stokes equations on R^3 or T^3, "
            "do smooth finite-energy initial data remain smooth for all time?"
        ),
        target_type="theorem",
        objective=("prove_global_smoothness", "construct_blowup"),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=(
            "1d_burgers_as_3d_ns",
            "finite_time_window_as_all_time",
            "inviscid_shock_as_viscous_blowup",
        ),
        acceptable_completion=("rigorous_proof", "rigorous_disproof"),
        pond="navier_stokes",
        definitions=(
            ("incompressible_ns", "\u2202_t u + u\u00b7\u2207u = \u03bd\u0394u \u2212 \u2207p, div u = 0"),
            ("smoothness", "u(\u00b7,t) remains C^\u221e on the existence interval"),
        ),
        known_facts=(
            "local smooth existence is classical",
            "2D global regularity is known",
            "Beale–Kato–Majda: blowup requires unbounded vorticity integral",
        ),
    ),
    "Poincare": ProblemSpec(
        id="MATH-MP-05",
        key="Poincare",
        title="Poincaré Conjecture",
        domain="geometric_topology",
        status="solved",
        statement="Every simply connected closed 3-manifold is homeomorphic to S^3.",
        target_type="theorem",
        objective=("study_perelman_ricci_flow", "do_not_reclaim_prize"),
        allowed_claims=("lemma", "computational_evidence", "literature"),
        forbidden_shortcuts=("reclaim_cmi_prize", "discrete_toy_as_3manifold_proof"),
        acceptable_completion=("already_awarded_perelman_2010",),
        pond="poincare",
        definitions=(
            ("simply_connected", "\u03c0\u2081 trivial"),
            ("ricci_flow", "\u2202_t g = \u22122 Ric(g)"),
        ),
        known_facts=(
            "Perelman 2002–2003; CMI awarded 2010",
            "Duck does not re-claim this prize",
        ),
    ),
    "Hodge": ProblemSpec(
        id="MATH-MP-06",
        key="Hodge",
        title="Hodge Conjecture",
        domain="algebraic_geometry",
        status="open",
        statement=(
            "On a non-singular projective complex variety, every Hodge class "
            "is a rational linear combination of algebraic cycle classes."
        ),
        target_type="theorem",
        objective=("prove_hodge_classes_algebraic",),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=(
            "betti_of_toy_complex_as_hodge",
            "kahler_identities_as_conjecture",
        ),
        acceptable_completion=("rigorous_proof", "rigorous_disproof"),
        pond="hodge",
        definitions=(
            ("hodge_class", "rational (p,p) class in H^{2p}"),
            ("algebraic_cycle", "codimension-p subvariety class"),
        ),
        known_facts=("known for (1,1) classes (Lefschetz)",),
    ),
    "BSD": ProblemSpec(
        id="MATH-MP-07",
        key="BSD",
        title="Birch and Swinnerton-Dyer",
        domain="arithmetic_geometry",
        status="open",
        statement=(
            "For an elliptic curve E/Q, the rank of E(Q) equals the order of "
            "vanishing of L(E,s) at s=1."
        ),
        target_type="theorem",
        objective=("prove_analytic_rank_equals_algebraic_rank",),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=(
            "box_search_as_rank",
            "truncated_euler_product_as_L",
            "named_curve_as_all_curves",
        ),
        acceptable_completion=("rigorous_proof", "rigorous_disproof"),
        pond="bsd",
        definitions=(
            ("algebraic_rank", "rank of the Mordell–Weil group E(Q)"),
            ("analytic_rank", "ord_{s=1} L(E,s)"),
        ),
        known_facts=("proved for analytic rank 0 and 1 over Q (Gross–Zagier, Kolyvagin, \u2026)",),
    ),
    "Collatz": ProblemSpec(
        id="MATH-X-01",
        key="Collatz",
        title="Collatz conjecture",
        domain="elementary_number_theory",
        status="open",
        statement="Every positive integer reaches 1 under n \u21a6 n/2 (even) or 3n+1 (odd).",
        target_type="theorem",
        objective=("prove_all_orbits_reach_1", "exhibit_divergent_or_cycle"),
        allowed_claims=_COMMON_ALLOWED,
        forbidden_shortcuts=("named_window_as_all_integers",),
        acceptable_completion=("rigorous_proof", "rigorous_disproof"),
        pond="collatz",
        definitions=(
            ("T", "T(n)=n/2 if even else 3n+1"),
            ("stopping_time", "least k with T^k(n)=1"),
        ),
        known_facts=("verified computationally on large finite windows; that is not a proof",),
    ),
}


BY_ID: dict[str, ProblemSpec] = {p.id: p for p in MILLENNIUM.values()}
BY_POND: dict[str, ProblemSpec] = {p.pond: p for p in MILLENNIUM.values()}
BY_KEY: dict[str, ProblemSpec] = dict(MILLENNIUM)


def get_problem(ref: str) -> ProblemSpec:
    if ref in BY_KEY:
        return BY_KEY[ref]
    if ref in BY_ID:
        return BY_ID[ref]
    if ref in BY_POND:
        return BY_POND[ref]
    raise KeyError(f"unknown problem {ref!r}")


def shortcut_forbidden(spec: ProblemSpec, tag: str) -> bool:
    return tag in spec.forbidden_shortcuts
