"""Duck Gate v0.1 — deterministic admission boundary.

Qwuack proposes. The gate admits. FieldTick commits.

This module is the contract. OperatorAbi is the implementation that
already sits on the World loop. Do not give Qwuack a write handle here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

GATE_ID = "duck_gate_01"
GATE_VERSION = "0.1"
GATE_POLICY = "duck_gate_v0.1"

AdmissionStatus = Literal[
    "ADMITTED",
    "REJECTED",
    "EXPIRED",
    "STALE",
    "SUPERSEDED",
    "CONFLICTED",
    "BUDGET_EXCEEDED",
    "UNAUTHORIZED",
    "INVALID",
    "INVARIANT_VIOLATION",
    "BOUNDS",
]

REASON_BY_STATUS: dict[str, str] = {
    "ADMITTED": "within_policy",
    "REJECTED": "rejected",
    "EXPIRED": "expired",
    "STALE": "stale_observation",
    "SUPERSEDED": "superseded",
    "CONFLICTED": "conflicted",
    "BUDGET_EXCEEDED": "budget_exceeded",
    "UNAUTHORIZED": "unauthorized",
    "INVALID": "invalid",
    "INVARIANT_VIOLATION": "invariant_violation",
    "BOUNDS": "bounds",
}


@dataclass(frozen=True)
class GateConfig:
    gate_id: str = GATE_ID
    version: str = GATE_VERSION
    default_authority: str = "advisory"
    max_delta_per_tick: float = 2.0
    max_single_delta: float = 1.0
    max_accepts: int = 40
    window: int = 100
    stale_after: int = 1
    conflict_policy: str = "first_admitted"
    bounds_policy: str = "reject"
    replay_mode: str = "recorded"
    invariants: tuple[str, ...] = (
        "energy_nonnegative",
        "state_finite",
        "sequence_monotonic",
        "channel_unit_interval",
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InfluenceBudget:
    source: str
    window: int = 100
    max_delta: float = 8.0
    max_single_delta: float = 1.0
    max_accepts: int = 40
    consumed_delta: float = 0.0
    accepts: int = 0
    tick_consumed: float = 0.0
    tick_at: int = -1

    def start_tick(self, tick: int) -> None:
        if self.tick_at != tick:
            self.tick_at = tick
            self.tick_consumed = 0.0
        if self.accepts >= self.window:
            self.accepts = 0
            self.consumed_delta = 0.0

    def remaining_accepts(self) -> int:
        return max(0, self.max_accepts - self.accepts)

    def would_exceed(self, magnitude: float, tick_cap: float, max_cell: float = 0.0) -> bool:
        if max_cell > self.max_single_delta + 1e-12:
            return True
        if self.consumed_delta + magnitude > self.max_delta + 1e-12:
            return True
        if self.accepts + 1 > self.max_accepts:
            return True
        if self.tick_consumed + magnitude > tick_cap + 1e-12:
            return True
        return False

    def consume(self, magnitude: float) -> None:
        self.consumed_delta += magnitude
        self.tick_consumed += magnitude
        self.accepts += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "window": self.window,
            "max_delta": self.max_delta,
            "max_single_delta": self.max_single_delta,
            "max_accepts": self.max_accepts,
            "consumed_delta": self.consumed_delta,
            "accepts": self.accepts,
            "remaining_accepts": self.remaining_accepts(),
            "tick_consumed": self.tick_consumed,
        }


@dataclass
class Provenance:
    proposal_id: str
    source_id: str
    observation_id: str
    observation_sequence: int | None
    gate_policy: str = GATE_POLICY
    admission_reason: str = "within_policy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdmissionResult:
    proposal_id: str
    status: str
    reason_code: str
    accepted: bool
    reason: str
    provenance: Provenance
    requested_magnitude: float = 0.0
    admitted_magnitude: float = 0.0
    admitted_delta: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "accepted": self.accepted,
            "reason": self.reason,
            "requested_magnitude": self.requested_magnitude,
            "admitted_magnitude": self.admitted_magnitude,
            "admitted_delta": self.admitted_delta,
            "provenance": self.provenance.as_dict(),
        }


def status_reason(status: str) -> str:
    return REASON_BY_STATUS.get(status, status.lower())


def delta_magnitude(deltas: list[Any]) -> float:
    total = 0.0
    for d in deltas:
        try:
            total += abs(float(d.new_value) - float(d.old_value))
        except (TypeError, ValueError, AttributeError):
            continue
    return total


DEFAULT_GATE = GateConfig()
