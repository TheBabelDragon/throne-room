"""Compact simple gauge groups — explicit mathematical representations.

SU(2) is the first computational implementation (unit quaternions).
SU(3) and generic compact simple groups are architectural targets;
this module does not claim they are fully implemented.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Numerical tolerance for membership / unitarity checks.
EPS = 1e-9


@runtime_checkable
class GaugeGroup(Protocol):
    name: str

    def identity(self) -> object: ...
    def multiply(self, a: object, b: object) -> object: ...
    def inverse(self, a: object) -> object: ...
    def conjugate(self, g: object, u: object) -> object: ...
    def is_member(self, a: object, tol: float = EPS) -> bool: ...
    def random(self, rng: random.Random) -> object: ...
    def reunitarize(self, a: object) -> object: ...
    def trace_normalized(self, a: object) -> float: ...
    def dim(self) -> int: ...


@dataclass(frozen=True)
class SU2Element:
    """Unit quaternion representing an SU(2) matrix.

    (w, x, y, z) with w^2 + x^2 + y^2 + z^2 = 1 corresponds to
    [[w+ix, y+iz], [-y+iz, w-ix]] (up to conventional ordering).
    """
    w: float
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.w, self.x, self.y, self.z)

    def norm_sq(self) -> float:
        return self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z


class SU2:
    """SU(2) as unit quaternions. Determinant one and unitarity are enforced."""

    name = "SU(2)"

    def identity(self) -> SU2Element:
        return SU2Element(1.0, 0.0, 0.0, 0.0)

    def multiply(self, a: SU2Element, b: SU2Element) -> SU2Element:
        # Quaternion product a * b
        w = a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z
        x = a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y
        y = a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x
        z = a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w
        return self.reunitarize(SU2Element(w, x, y, z))

    def inverse(self, a: SU2Element) -> SU2Element:
        # Unit quaternion inverse is conjugate
        return SU2Element(a.w, -a.x, -a.y, -a.z)

    def conjugate(self, g: SU2Element, u: SU2Element) -> SU2Element:
        """Gauge transform: u * g * u^{-1}."""
        return self.multiply(self.multiply(u, g), self.inverse(u))

    def is_member(self, a: SU2Element, tol: float = EPS) -> bool:
        if not isinstance(a, SU2Element):
            return False
        return abs(a.norm_sq() - 1.0) <= tol

    def random(self, rng: random.Random) -> SU2Element:
        """Haar-uniform sample via 4D Gaussian projection onto S^3."""
        coords = [rng.gauss(0.0, 1.0) for _ in range(4)]
        n = math.sqrt(sum(c * c for c in coords))
        if n < 1e-18:
            return self.identity()
        return SU2Element(coords[0] / n, coords[1] / n, coords[2] / n, coords[3] / n)

    def reunitarize(self, a: SU2Element) -> SU2Element:
        n = math.sqrt(a.norm_sq())
        if n < 1e-18:
            return self.identity()
        return SU2Element(a.w / n, a.x / n, a.y / n, a.z / n)

    def trace_normalized(self, a: SU2Element) -> float:
        """(1/2) Re Tr(U) for SU(2). For unit quaternion this is w."""
        return float(a.w)

    def dim(self) -> int:
        return 2

    def check_invariants(self, a: SU2Element, tol: float = EPS) -> list[str]:
        errs: list[str] = []
        if abs(a.norm_sq() - 1.0) > tol:
            errs.append(f"norm_sq={a.norm_sq():.6g} != 1")
        return errs


def group_for(name: str) -> GaugeGroup:
    key = name.strip().upper().replace("(", "").replace(")", "")
    if key in {"SU2", "SU(2)"}:
        return SU2()
    if key in {"SU3", "SU(3)"}:
        raise NotImplementedError(
            "SU(3) is an architectural target, not a completed capability in this module."
        )
    raise ValueError(f"unsupported or incomplete gauge group: {name!r}")
