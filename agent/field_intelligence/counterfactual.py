"""Counterfactual Laboratory — isolated experiment branches.

Never mutates the live FieldTick journal.
Simulated outcomes are always labeled SIMULATION, never LIVE.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent.engine import FieldScheduler, seed_field
from agent.hashutil import uid
from agent.perception import make_synthetic_csi
from agent.schemas import Channel


@dataclass
class ExperimentInput:
    sequence: int
    observation_payload: dict[str, Any]
    action_type: str | None = None
    action_params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentOutcome:
    outcome_id: str
    branch_id: str
    kind: str  # OBSERVED | SIMULATED
    final_sequence: int
    energy_sum: float
    tick_hash: str | None
    notes: str = ""
    metrics: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentBranch:
    branch_id: str
    label: str
    inputs: list[ExperimentInput]
    outcome: ExperimentOutcome | None = None
    software_note: str = "field-intelligence/v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "label": self.label,
            "inputs": [i.as_dict() for i in self.inputs],
            "outcome": self.outcome.as_dict() if self.outcome else None,
            "software_note": self.software_note,
        }


@dataclass
class OutcomeComparison:
    comparison_id: str
    original_branch_id: str
    alternative_branch_id: str
    energy_delta: float
    sequence_delta: int
    indistinguishable: bool
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Experiment:
    experiment_id: str
    episode_id: str
    created_at: float
    baseline_branch_id: str
    branches: list[ExperimentBranch] = field(default_factory=list)
    comparisons: list[OutcomeComparison] = field(default_factory=list)
    seed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "episode_id": self.episode_id,
            "created_at": self.created_at,
            "baseline_branch_id": self.baseline_branch_id,
            "branches": [b.as_dict() for b in self.branches],
            "comparisons": [c.as_dict() for c in self.comparisons],
            "seed": self.seed,
        }


def _run_branch(
    inputs: list[ExperimentInput],
    *,
    seed: int = 0,
    label: str = "branch",
) -> tuple[ExperimentBranch, ExperimentOutcome]:
    sched = FieldScheduler(seed_field())
    last_hash: str | None = None
    for inp in inputs:
        obs_seed = inp.observation_payload.get("seed")
        if obs_seed is not None:
            try:
                sched.bind_observation(make_synthetic_csi(int(obs_seed)))
            except Exception:
                pass
        if inp.action_type == "PROBE":
            params = inp.action_params or {}
            _ = float(params.get("magnitude", 0.3))
        commit = sched.step(0.125)
        last_hash = commit.hash

    energy = float(sched.field.sum(Channel.Energy))
    branch_id = uid("xbr")
    outcome = ExperimentOutcome(
        outcome_id=uid("xout"),
        branch_id=branch_id,
        kind="SIMULATED",
        final_sequence=int(sched.sequence),
        energy_sum=energy,
        tick_hash=last_hash,
        notes=f"isolated branch label={label}",
        metrics={"energy": energy, "sequence": float(sched.sequence)},
    )
    branch = ExperimentBranch(
        branch_id=branch_id,
        label=label,
        inputs=list(inputs),
        outcome=outcome,
    )
    return branch, outcome


class CounterfactualLab:
    """Create isolated experiment branches from historical episode inputs."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else Path("/tmp/metafield/counterfactual")
        self.root.mkdir(parents=True, exist_ok=True)
        self.experiments: list[Experiment] = []

    def start_experiment(
        self,
        *,
        episode_id: str,
        baseline_inputs: list[ExperimentInput],
        seed: int = 0,
    ) -> Experiment:
        branch, _ = _run_branch(baseline_inputs, seed=seed, label="baseline")
        exp = Experiment(
            experiment_id=uid("xexp"),
            episode_id=episode_id,
            created_at=time.time(),
            baseline_branch_id=branch.branch_id,
            branches=[branch],
            seed=seed,
        )
        self.experiments.append(exp)
        self._persist(exp)
        return exp

    def branch_alternative(
        self,
        experiment_id: str,
        *,
        label: str,
        inputs: list[ExperimentInput],
    ) -> ExperimentBranch:
        exp = self._get(experiment_id)
        if exp is None:
            raise KeyError(f"unknown experiment {experiment_id}")
        branch, _ = _run_branch(inputs, seed=exp.seed, label=label)
        exp.branches.append(branch)
        self._persist(exp)
        return branch

    def compare(self, experiment_id: str, left_id: str, right_id: str) -> OutcomeComparison:
        exp = self._get(experiment_id)
        if exp is None:
            raise KeyError(f"unknown experiment {experiment_id}")
        left = next((b for b in exp.branches if b.branch_id == left_id), None)
        right = next((b for b in exp.branches if b.branch_id == right_id), None)
        if left is None or right is None or left.outcome is None or right.outcome is None:
            raise ValueError("both branches must have outcomes")
        energy_delta = right.outcome.energy_sum - left.outcome.energy_sum
        seq_delta = right.outcome.final_sequence - left.outcome.final_sequence
        indistinguishable = abs(energy_delta) < 1e-6 and seq_delta == 0
        if left.outcome.tick_hash and right.outcome.tick_hash:
            if left.outcome.tick_hash == right.outcome.tick_hash:
                indistinguishable = True
        cmp = OutcomeComparison(
            comparison_id=uid("xcmp"),
            original_branch_id=left_id,
            alternative_branch_id=right_id,
            energy_delta=energy_delta,
            sequence_delta=seq_delta,
            indistinguishable=indistinguishable,
            notes="SIMULATED outcomes only; live FieldTick untouched",
        )
        exp.comparisons.append(cmp)
        self._persist(exp)
        return cmp

    def _get(self, experiment_id: str) -> Experiment | None:
        for e in self.experiments:
            if e.experiment_id == experiment_id:
                return e
        return None

    def _persist(self, exp: Experiment) -> None:
        path = self.root / f"{exp.experiment_id}.json"
        try:
            path.write_text(json.dumps(exp.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
