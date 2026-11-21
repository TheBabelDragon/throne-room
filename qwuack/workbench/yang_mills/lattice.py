"""Finite periodic four-dimensional hypercubic lattice for gauge theory.

Each oriented link carries a group element. Dimensions, boundary conditions,
coupling, group, seed, and update configuration are explicit.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from qwuack.workbench.yang_mills.groups import GaugeGroup, SU2, SU2Element, group_for


@dataclass(frozen=True)
class LatticeConfig:
    """Explicit, serializable lattice experiment configuration."""

    Lx: int = 4
    Ly: int = 4
    Lz: int = 4
    Lt: int = 4
    beta: float = 2.0
    group_name: str = "SU(2)"
    seed: int = 0
    boundary: str = "periodic"

    def __post_init__(self) -> None:
        if min(self.Lx, self.Ly, self.Lz, self.Lt) < 2:
            raise ValueError("each lattice extent must be >= 2")
        if self.boundary != "periodic":
            raise ValueError("only periodic boundaries are implemented")

    @property
    def volume(self) -> int:
        return self.Lx * self.Ly * self.Lz * self.Lt

    @property
    def dims(self) -> tuple[int, int, int, int]:
        return (self.Lx, self.Ly, self.Lz, self.Lt)

    def as_dict(self) -> dict[str, Any]:
        return {
            "Lx": self.Lx,
            "Ly": self.Ly,
            "Lz": self.Lz,
            "Lt": self.Lt,
            "beta": self.beta,
            "group_name": self.group_name,
            "seed": self.seed,
            "boundary": self.boundary,
            "volume": self.volume,
            "evidence_level": "finite_lattice",
        }


class Lattice4D:
    """Gauge links U_mu(x) on a 4D hypercubic lattice with periodic BC."""

    def __init__(self, config: LatticeConfig, group: GaugeGroup | None = None) -> None:
        self.config = config
        self.group = group or group_for(config.group_name)
        self.dims = config.dims
        self.ndir = 4
        # links[site_index][mu] = group element
        n = config.volume
        self.links: list[list[Any]] = [
            [self.group.identity() for _ in range(self.ndir)] for _ in range(n)
        ]

    def site_index(self, x: int, y: int, z: int, t: int) -> int:
        Lx, Ly, Lz, Lt = self.dims
        x = x % Lx
        y = y % Ly
        z = z % Lz
        t = t % Lt
        return ((t * Lz + z) * Ly + y) * Lx + x

    def coords(self, index: int) -> tuple[int, int, int, int]:
        Lx, Ly, Lz, Lt = self.dims
        x = index % Lx
        index //= Lx
        y = index % Ly
        index //= Ly
        z = index % Lz
        t = index // Lz
        return (x, y, z, t)

    def shift(self, index: int, mu: int, steps: int = 1) -> int:
        coords = list(self.coords(index))
        coords[mu] += steps
        return self.site_index(*coords)

    def get_link(self, index: int, mu: int) -> Any:
        return self.links[index][mu]

    def set_link(self, index: int, mu: int, value: Any) -> None:
        if not self.group.is_member(value):
            value = self.group.reunitarize(value)
        self.links[index][mu] = value

    def cold_start(self) -> None:
        ident = self.group.identity()
        for i in range(self.config.volume):
            for mu in range(self.ndir):
                self.links[i][mu] = ident

    def hot_start(self, rng: random.Random) -> None:
        for i in range(self.config.volume):
            for mu in range(self.ndir):
                self.links[i][mu] = self.group.random(rng)

    def gauge_transform(self, site_gauges: list[Any]) -> None:
        """Apply local gauge transformation g(x) to every link."""
        if len(site_gauges) != self.config.volume:
            raise ValueError("site_gauges length must equal volume")
        g = self.group
        new_links = [[None] * self.ndir for _ in range(self.config.volume)]
        for i in range(self.config.volume):
            for mu in range(self.ndir):
                j = self.shift(i, mu, 1)
                # U'_mu(x) = g(x) U_mu(x) g(x+mu)^{-1}
                new_links[i][mu] = g.multiply(
                    g.multiply(site_gauges[i], self.links[i][mu]),
                    g.inverse(site_gauges[j]),
                )
        self.links = new_links  # type: ignore[assignment]

    def random_gauge_transform(self, rng: random.Random) -> None:
        gauges = [self.group.random(rng) for _ in range(self.config.volume)]
        self.gauge_transform(gauges)

    def serialize_config(self) -> dict[str, Any]:
        """Lightweight serialization for reproducibility notes (not full binary dump)."""
        # Store a checksum of link data for replay identity checks.
        checksum = 0.0
        for i in range(self.config.volume):
            for mu in range(self.ndir):
                el = self.links[i][mu]
                if isinstance(el, SU2Element):
                    checksum += el.w + 2 * el.x + 3 * el.y + 5 * el.z
                else:
                    checksum += hash(str(el)) % 1000
        return {
            "config": self.config.as_dict(),
            "link_checksum": checksum,
            "n_links": self.config.volume * self.ndir,
        }
