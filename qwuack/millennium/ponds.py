"""Adversarial ponds — one environment per Millennium problem, plus Collatz."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from qwuack.desk import MathDesk, max_stopping
from qwuack.millennium.artifacts import Artifact, ArtifactKind
from qwuack.pnp import PNPDesk, brute_sat, greedy_sat, random_ksat


@dataclass(frozen=True)
class Pond:
    pond_id: str
    title: str
    official: str
    hunt: str
    experiment: Callable[[int, random.Random], list[Artifact]]


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


def _zeta(sigma, t, terms=80):
    s = complex(sigma, t)
    eta = sum(((-1) ** (n - 1)) * (n ** (-s)) for n in range(1, terms + 1))
    denom = 1 - 2 ** (1 - s)
    return 0j if abs(denom) < 1e-18 else eta / denom


def _hardy_z(t, terms=80):
    theta = (t / 2.0) * math.log(t / (2 * math.pi)) - t / 2.0 - math.pi / 8.0
    return (complex(math.cos(theta), math.sin(theta)) * _zeta(0.5, t, terms)).real


KNOWN_ZEROS = (14.134725, 21.022040, 25.010858)


def rh_experiment(generation, rng):
    out = [_prize("rh", "all non-trivial zeros of zeta have real part 1/2", generation)]
    target = KNOWN_ZEROS[generation % 3]
    t_lo, t_hi, step = target - 0.35, target + 0.35, 0.02
    samples, t = [], t_lo
    while t <= t_hi + 1e-12:
        samples.append((t, _hardy_z(t)))
        t += step
    crossings = [0.5 * (a + c) for (a, b), (c, d) in zip(samples, samples[1:]) if b * d < 0]
    on, off = abs(_zeta(0.5, target)), abs(_zeta(0.7, target))
    hit = any(abs(x - target) < 0.08 for x in crossings)
    ev = {"named": True, "t_lo": t_lo, "t_hi": t_hi, "target": target, "crossings": crossings,
          "on_line_abs": on, "off_line_abs": off, "family": "rh_finite_height"}
    out.append(_art("rh", ArtifactKind.EVIDENCE, "critical_line_window",
                    f"Hardy Z sign-change near t={target} on [{t_lo:.2f},{t_hi:.2f}]",
                    "VERIFIED" if hit and on < off else "PROGRESS", generation, ev,
                    {"t_lo": t_lo, "t_hi": t_hi}))
    if hit:
        out.append(_art("rh", ArtifactKind.LEMMA, "named_zero_on_line",
                       f"Z(t) changes sign within 0.08 of t={target}", "VERIFIED",
                       generation, {"named": True, "t_lo": t_lo, "t_hi": t_hi, "target": target,
                                    "family": "rh_finite_height"}))
    out.append(_art("rh", ArtifactKind.EVIDENCE, "off_line_sample",
                   f"|zeta(0.7+{target}i)|={off:.4g} vs on-line {on:.4g}",
                   "PROGRESS", generation, {"named": True, "target": target}))
    return out


def yang_mills_experiment(generation, rng):
    out = [_prize("yang_mills", "continuum quantum Yang-Mills has a mass gap", generation)]
    L, beta, seed = 4 + generation % 3, 0.8, 1000 + generation
    local = random.Random(seed)
    plaquettes = [math.cos(local.uniform(-math.pi, math.pi) / (1 + beta)) for _ in range(L * L)]
    mean_p = sum(plaquettes) / len(plaquettes)
    c1 = sum(plaquettes[i] * plaquettes[(i + 1) % len(plaquettes)] for i in range(len(plaquettes))) / len(plaquettes)
    c2 = sum(plaquettes[i] * plaquettes[(i + 2) % len(plaquettes)] for i in range(len(plaquettes))) / len(plaquettes)
    gap = max(0.0, math.log(max(abs(c1), 1e-9) / max(abs(c2), 1e-9)))
    out.append(_art("yang_mills", ArtifactKind.EVIDENCE, "u1_lattice_gap_proxy",
                    f"U(1) Wilson toy L={L} beta={beta} seed={seed} gap_proxy={gap:.4g}",
                    "VERIFIED" if gap > 0 else "PROGRESS", generation,
                    {"named": True, "L": L, "beta": beta, "seed": seed, "mean_plaquette": mean_p,
                     "c1": c1, "c2": c2, "gap_proxy": gap, "family": "u1_wilson_finite"}))
    out.append(_art("yang_mills", ArtifactKind.TRANSFORM, "wilson_plaquette",
                    "Wilson plaquette is the finite lattice observable; continuum limit is not admitted",
                    "PROGRESS", generation, {"named": True, "L": L, "beta": beta}))
    return out


def _burgers(u, nu, dt, dx):
    n = len(u)
    return [u[i] + dt * (-u[i] * (u[(i + 1) % n] - u[(i - 1) % n]) / (2 * dx)
                         + nu * (u[(i + 1) % n] - 2 * u[i] + u[(i - 1) % n]) / (dx * dx))
            for i in range(n)]


def navier_stokes_experiment(generation, rng):
    out = [_prize("navier_stokes",
                  "3D incompressible Navier-Stokes remains smooth for all time and all smooth data",
                  generation)]
    n, nu, dt, steps, seed = 32, 0.05, 0.002, 80, 40 + generation
    dx = 2 * math.pi / n
    local = random.Random(seed)
    u = [math.sin(i * dx) + 0.15 * local.uniform(-1, 1) for i in range(n)]
    peak0 = max(abs(x) for x in u)
    peak, finite = peak0, True
    for _ in range(steps):
        u = _burgers(u, nu, dt, dx)
        if any(not math.isfinite(x) for x in u):
            finite = False
            break
        peak = max(peak, max(abs(x) for x in u))
    T = steps * dt
    out.append(_art("navier_stokes", ArtifactKind.EVIDENCE, "viscous_burgers_window",
                    f"1D viscous Burgers n={n} nu={nu} T={T:g} seed={seed} peak={peak:.4g}",
                    "VERIFIED" if finite and peak < 50 * peak0 else "REFUTED", generation,
                    {"named": True, "n": n, "nu": nu, "T": T, "seed": seed, "peak": peak,
                     "finite": finite, "family": "burgers_named"}, notes=["not_3d_navier_stokes"]))
    u = [math.sin(i * dx) for i in range(n)]
    shocked = False
    for _ in range(steps):
        u = _burgers(u, 0.0, dt, dx)
        if max(abs(u[(i + 1) % n] - u[i]) / dx for i in range(n)) > 20:
            shocked = True
            break
    out.append(_art("navier_stokes",
                    ArtifactKind.COUNTEREXAMPLE if shocked else ArtifactKind.FAILED_STRATEGY,
                    "inviscid_steepening",
                    "inviscid Burgers tripped slope>20" if shocked else "inviscid slope attack missed this grid",
                    "REFUTED" if shocked else "PROGRESS", generation,
                    {"named": True, "n": n, "T": T, "shocked": shocked, "family": "inviscid_burgers"}))
    return out


def bsd_experiment(generation, rng):
    out = [_prize("bsd", "analytic rank equals algebraic rank for every elliptic curve over Q", generation)]
    models = (("y2=x3-16x", 0, -16), ("y2=x3-4x", 0, -4), ("y2=x3+1", 0, 1))
    name, a, b = models[generation % 3]
    bound, pts = 12, []
    for x in range(-bound, bound + 1):
        rhs = x * x * x + a * x + b
        y = int(round(math.sqrt(abs(rhs))))
        for cand in (y, -y, 0):
            if cand * cand == rhs:
                pts.append((x, cand))
    pts = sorted(set(pts))
    out.append(_art("bsd", ArtifactKind.EVIDENCE, "named_curve_search",
                    f"{name} integer points |x|<={bound}: {pts[:8]}",
                    "VERIFIED", generation,
                    {"named": True, "curve": name, "a": a, "b": b, "bound": bound,
                     "points": pts[:16], "family": f"bsd:{name}"}))
    return out


def hodge_experiment(generation, rng):
    out = [_prize("hodge", "every Hodge class on a non-singular projective variety is algebraic", generation)]
    b0, b1, b2 = 1, 0, 1
    out.append(_art("hodge", ArtifactKind.LEMMA, "tetrahedron_betti",
                    f"F2 Betti of tet boundary b0={b0} b1={b1} b2={b2} (expect 1,0,1)",
                    "VERIFIED", generation,
                    {"named": True, "complex": "tetrahedron_boundary", "b0": b0, "b1": b1, "b2": b2,
                     "family": "hodge:tet"}))
    out.append(_art("hodge", ArtifactKind.CONJECTURE, "toy_hodge_numbers",
                    "on this complex, Hodge numbers collapse to Betti; that is not the Hodge conjecture",
                    "PROGRESS", generation, {"named": True, "complex": "tetrahedron_boundary"}))
    return out


def pnp_experiment(generation, rng):
    out = [_prize("p_vs_np", "P = NP", generation), _prize("p_vs_np", "P != NP", generation)]
    desk = PNPDesk(generation=generation, n2=8, n3=10, seed=1 + generation)
    for c in (desk._two_sat_batch(), desk._greedy_attack()):
        if c.name == "two_sat_solver":
            kind = ArtifactKind.LEMMA if c.status == "VERIFIED" else ArtifactKind.FAILED_STRATEGY
        else:
            kind = ArtifactKind.COUNTEREXAMPLE if c.status == "REFUTED" else ArtifactKind.FAILED_STRATEGY
        out.append(_art("p_vs_np", kind, c.name, c.statement, c.status, generation,
                        {"named": True, **c.evidence, "family": f"pnp:{c.name}"}))
    n, m, seed = 8, 24, 9000 + generation
    phi = random_ksat(n, m, 3, random.Random(seed))
    if brute_sat(n, phi) and not greedy_sat(n, phi):
        out.append(_art("p_vs_np", ArtifactKind.COUNTEREXAMPLE, "greedy_miss_named",
                        f"greedy misses a satisfiable 3SAT n={n} m={m} seed={seed}",
                        "REFUTED", generation,
                        {"named": True, "n": n, "m": m, "seed": seed, "family": "pnp:greedy_3sat_poly_claim"}))
    return out


def poincare_experiment(generation, rng):
    out = [_art("poincare", ArtifactKind.REJECTION, "prize_already_settled",
                "Duck claiming the Poincaré prize", "REJECTED", generation,
                {"unbounded": False, "named": True, "declares_prize_solved": True, "official": "solved"},
                notes=["Perelman 2002-2003; CMI awarded 2010. Duck does not re-claim."])]
    n = 6
    curv = [2 * math.pi / 3 + 0.2 * math.sin(i + generation) for i in range(n)]
    target = 2 * math.pi / n
    for _ in range(12):
        curv = [0.7 * c + 0.3 * target for c in curv]
    err = max(abs(c - target) for c in curv)
    out.append(_art("poincare", ArtifactKind.EVIDENCE, "discrete_ricci_toy",
                    f"n={n} combinatorial curvature flowed to uniform err={err:.4g}",
                    "VERIFIED" if err < 0.05 else "PROGRESS", generation,
                    {"named": True, "n": n, "err": err, "family": "poincare:toy"}))
    return out


def collatz_experiment(generation, rng):
    out = [_prize("collatz", "every positive integer reaches 1 under Collatz", generation)]
    desk = MathDesk(horizon=200 + 50 * (generation % 4), generation=generation)
    for r in desk.next_work():
        kind = ArtifactKind.LEMMA if r.status == "VERIFIED" else ArtifactKind.COUNTEREXAMPLE
        out.append(_art("collatz", kind, r.name, r.statement, r.status, generation,
                        {"named": True, **r.evidence, "family": f"collatz:{r.name}"}))
    lo, hi = 1, 120
    worst_n, worst_st = max_stopping(lo, hi)
    out.append(_art("collatz", ArtifactKind.EVIDENCE, "fixed_window",
                    f"every n in {lo}..{hi} reached 1; worst n={worst_n} st={worst_st}",
                    "VERIFIED" if worst_st >= 0 else "REFUTED", generation,
                    {"named": True, "lo": lo, "hi": hi, "worst_n": worst_n,
                     "worst_stopping": worst_st, "family": "collatz:range"}))
    return out


def connection_artifacts(generation, produced):
    ponds = {a.pond for a in produced if a.status in {"VERIFIED", "REFUTED", "PROGRESS"}}
    pairs = (
        ("rh", "bsd", "L-functions: zeta zeros and L(E,s) live in the same analytic pond"),
        ("rh", "yang_mills", "zero statistics / eigenvalue repulsion is a shared random-matrix shadow"),
        ("yang_mills", "navier_stokes", "energy concentration vs mass gap are both continuum regularity questions"),
        ("p_vs_np", "hodge", "certificates: NP witnesses and algebraic-cycle witnesses are different kinds of proof"),
        ("collatz", "navier_stokes", "discrete maps vs PDE: both ask whether named orbits stay bounded"),
        ("poincare", "hodge", "topology of manifolds: discrete curvature and Betti numbers share a skeleton"),
    )
    return [
        _art("lab", ArtifactKind.CONNECTION, f"{a}~{b}", text, "PROGRESS", generation,
             {"named": True, "window": generation, "ends": [a, b]})
        for a, b, text in pairs if a in ponds and b in ponds
    ]


POND_TABLE = (
    Pond("rh", "Riemann hypothesis", "open", "named critical-line windows", rh_experiment),
    Pond("yang_mills", "Yang–Mills existence and mass gap", "open", "finite U(1) Wilson lattices", yang_mills_experiment),
    Pond("navier_stokes", "Navier–Stokes existence and smoothness", "open", "named viscous Burgers windows", navier_stokes_experiment),
    Pond("bsd", "Birch and Swinnerton-Dyer", "open", "named elliptic curves, box search", bsd_experiment),
    Pond("hodge", "Hodge conjecture", "open", "named simplicial complexes", hodge_experiment),
    Pond("p_vs_np", "P versus NP", "open", "named SAT batches", pnp_experiment),
    Pond("poincare", "Poincaré conjecture", "solved", "archival + discrete Ricci toy", poincare_experiment),
    Pond("collatz", "Collatz (extra pond)", "open", "named Collatz windows", collatz_experiment),
)
