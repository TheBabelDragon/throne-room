"""Field Intelligence live-path bridge.

Wires World Mirror, Associative Memory, Decision Observatory, Prediction,
and Counterfactual capture into the existing Qwuack tenant cycle.

Does not own FieldTick. Does not admit actions. Does not bind UDP.
Observatory is witness-only. Counterfactual inputs are recorded for
isolated SIMULATED replay; live history is never mutated by the lab.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent.field_intelligence.associative_memory import AssociativeMemory, MemoryType
from agent.field_intelligence.counterfactual import (
    CounterfactualLab,
    ExperimentInput,
)
from agent.field_intelligence.decision_observatory import DecisionObservatory, SelectionMode
from agent.field_intelligence.prediction import PredictionStore
from agent.field_intelligence.world_mirror import WorldMirror
from agent.hashutil import uid
from agent.shared_body_perception import BodyView
from duck_gate.candidates import CandidateExcitation


@dataclass
class TraceStep:
    """One closed step on the live path."""

    sequence: int
    episode_id: str
    observation_id: str
    body_id: str | None
    synthetic: bool
    action_type: str
    accepted: bool
    admission_reason: str
    tick_sequence: int
    tick_hash: str | None
    consequence: str
    energy_before: float | None
    energy_after: float | None
    memory_ids: list[str] = field(default_factory=list)
    decision_id: str | None = None
    prediction_id: str | None = None
    mirror_changes: list[str] = field(default_factory=list)
    mode: str = "FIXTURE"  # LIVE | FIXTURE | REPLAY | SIMULATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FieldIntelligenceBridge:
    """Additive observer of the observation → FieldTick path."""

    def __init__(self, root: Path | str | None = None, *, episode_id: str | None = None) -> None:
        self.root = Path(root) if root else Path("/tmp/metafield/field_intelligence")
        self.root.mkdir(parents=True, exist_ok=True)
        self.episode_id = episode_id or uid("ep")
        self.mirror = WorldMirror(root=self.root / "world_mirror", mode="LIVE")
        self.memory = AssociativeMemory(path=self.root / "associative_memory.jsonl")
        self.observatory = DecisionObservatory(path=self.root / "decision_observatory.jsonl")
        self.predictions = PredictionStore(path=self.root / "predictions.jsonl")
        self.lab = CounterfactualLab(root=self.root / "counterfactual")
        self.episode_inputs: list[ExperimentInput] = []
        self.trace: list[TraceStep] = []
        self._pending_prediction_id: str | None = None
        self._last_obs_id: str | None = None
        self._last_decision_id: str | None = None
        self._last_action: str | None = None
        self._last_memory_ids: list[str] = []

    # ── perception ────────────────────────────────────────────────────

    def on_observation(
        self,
        *,
        observation_id: str,
        body_id: str | None,
        synthetic: bool,
        status: str = "ALIVE",
        energy: float | None = None,
        measurements: dict[str, float | None] | None = None,
        source_system: str = "csi",
        source_node_id: str | None = None,
        observed_at: str = "",
        sequence: int = 0,
        modality: str = "csi",
    ) -> list[str]:
        """SHARED_BODY / CSI observation → World Mirror + OBSERVATION memory."""
        meas = dict(measurements or {})
        if energy is not None and "csi_energy" not in meas:
            meas["csi_energy"] = energy
        view = BodyView(
            body_id=body_id or "unknown",
            observation_id=observation_id,
            source_system=source_system,
            source_node_id=source_node_id or body_id or "unknown",
            observed_at=observed_at or str(sequence),
            ingested_at=str(time.time()),
            status=status,
            synthetic=synthetic,
            body_type="wifi_csi" if modality == "csi" else modality,
            regions=list(meas.keys()),
            measurements=meas,
            energy=energy,
        )
        changes = self.mirror.ingest_body_view(view)
        change_kinds = [c.kind for c in changes]

        content = (
            f"obs body={view.body_id} status={view.status} "
            f"synthetic={view.synthetic} energy={view.energy} "
            f"changes={change_kinds}"
        )
        rec = self.memory.append(
            episode_id=self.episode_id,
            memory_type=MemoryType.OBSERVATION,
            content=content,
            evidence_refs=[observation_id],
            confidence=0.35 if synthetic else 0.9,
            source_provenance=f"{source_system}:{view.source_node_id}",
            body_id=view.body_id,
            observation_id=observation_id,
            originating_tick=sequence,
        )
        self._last_obs_id = observation_id
        self._last_memory_ids = [rec.memory_id]
        return change_kinds

    def retrieve_for_body(self, body_id: str | None, query: str = "") -> list[Any]:
        return self.memory.retrieve_relevant(body_id=body_id, query=query, limit=6)

    # ── decision ──────────────────────────────────────────────────────

    def on_proposal(
        self,
        *,
        observation_id: str,
        proposal_id: str,
        action_type: str,
        rationale: str = "",
        sequence: int = 0,
    ) -> str:
        """Witness candidate selection. Does not authorize."""
        cand = CandidateExcitation(
            candidate_id=proposal_id or uid("cand"),
            stimulus=f"{action_type}:{observation_id}",
            predicted_response=rationale or action_type,
            novelty=0.5,
            information_gain=0.4 if action_type in {"PROBE", "ATTEND", "QUERY_FIELD"} else 0.1,
            cost=0.2 if action_type == "PROBE" else 0.05,
        )
        rec = self.observatory.observe_selection(
            episode_id=self.episode_id,
            observation_id=observation_id,
            candidates=[cand],
            mode=SelectionMode.DUCK,
        )
        action_mem = self.memory.append(
            episode_id=self.episode_id,
            memory_type=MemoryType.ACTION,
            content=f"propose {action_type} rationale={rationale[:80]}",
            evidence_refs=[observation_id, proposal_id],
            confidence=0.6,
            source_provenance="qwuack.policy",
            observation_id=observation_id,
            originating_tick=sequence,
            related_memory_ids=list(self._last_memory_ids),
        )
        # Structured prediction of consequence class (not a fact).
        pred = self.predictions.predict(
            episode_id=self.episode_id,
            source_observation_ids=[observation_id],
            target_event="consequence",
            expected_outcome=self._predict_consequence(action_type),
            confidence=0.55,
        )
        self._pending_prediction_id = pred.prediction_id
        self._last_decision_id = rec.decision_id
        self._last_action = action_type
        self._last_memory_ids.append(action_mem.memory_id)
        return rec.decision_id

    def on_admission(
        self,
        *,
        decision_id: str | None,
        proposal_id: str | None,
        accepted: bool,
        reason: str = "",
        tick_sequence: int | None = None,
    ) -> None:
        if decision_id:
            self.observatory.record_admission(
                decision_id,
                proposal_id=proposal_id,
                accepted=accepted,
                reason=reason,
                tick_sequence=tick_sequence,
            )

    # ── consequence ───────────────────────────────────────────────────

    def on_consequence(
        self,
        *,
        observation_id: str,
        body_id: str | None,
        synthetic: bool,
        action_type: str,
        accepted: bool,
        admission_reason: str,
        tick_sequence: int,
        tick_hash: str | None,
        consequence: str,
        energy_before: float | None,
        energy_after: float | None,
        sequence: int,
        observation_seed: int | None = None,
        action_params: dict[str, Any] | None = None,
    ) -> TraceStep:
        """Close the loop: CONSEQUENCE memory, prediction eval, episode input."""
        cons_mem = self.memory.append(
            episode_id=self.episode_id,
            memory_type=MemoryType.CONSEQUENCE,
            content=(
                f"consequence={consequence} accepted={accepted} "
                f"action={action_type} energy_before={energy_before} "
                f"energy_after={energy_after} tick={tick_sequence}"
            ),
            evidence_refs=[observation_id, tick_hash or ""],
            confidence=0.8 if accepted else 0.5,
            source_provenance="fieldtick",
            body_id=body_id,
            observation_id=observation_id,
            originating_tick=tick_sequence,
            related_memory_ids=list(self._last_memory_ids),
        )
        self._last_memory_ids.append(cons_mem.memory_id)

        pred_id = self._pending_prediction_id
        if pred_id:
            try:
                self.predictions.evaluate(pred_id, consequence)
            except KeyError:
                pass
            self._pending_prediction_id = None

        # Capture deterministic inputs for counterfactual isolation.
        payload: dict[str, Any] = {"observation_id": observation_id, "body_id": body_id}
        if observation_seed is not None:
            payload["seed"] = int(observation_seed)
        elif synthetic and body_id:
            # synthetic path uses tick as seed when not explicit
            payload["seed"] = int(sequence)
        self.episode_inputs.append(
            ExperimentInput(
                sequence=sequence,
                observation_payload=payload,
                action_type=action_type if accepted else None,
                action_params=dict(action_params or {}),
            )
        )

        step = TraceStep(
            sequence=sequence,
            episode_id=self.episode_id,
            observation_id=observation_id,
            body_id=body_id,
            synthetic=synthetic,
            action_type=action_type,
            accepted=accepted,
            admission_reason=admission_reason,
            tick_sequence=tick_sequence,
            tick_hash=tick_hash,
            consequence=consequence,
            energy_before=energy_before,
            energy_after=energy_after,
            memory_ids=list(self._last_memory_ids),
            decision_id=self._last_decision_id,
            prediction_id=pred_id,
            mode="FIXTURE" if synthetic else "LIVE",
        )
        self.trace.append(step)
        self._persist_trace(step)
        return step

    # ── counterfactual ────────────────────────────────────────────────

    def replay_episode(self, *, seed: int = 0) -> Any:
        """Replay captured episode inputs in an isolated SIMULATED branch."""
        if not self.episode_inputs:
            raise RuntimeError("no episode inputs recorded")
        return self.lab.start_experiment(
            episode_id=self.episode_id,
            baseline_inputs=list(self.episode_inputs),
            seed=seed,
        )

    def alternative_action(
        self,
        experiment_id: str,
        *,
        label: str,
        action_type: str,
        action_params: dict[str, Any] | None = None,
        sequence_index: int = -1,
    ) -> Any:
        """Branch one step with an alternate action; never touches live FieldTick."""
        inputs = [ExperimentInput(
            sequence=inp.sequence,
            observation_payload=dict(inp.observation_payload),
            action_type=inp.action_type,
            action_params=dict(inp.action_params),
        ) for inp in self.episode_inputs]
        if not inputs:
            raise RuntimeError("no episode inputs")
        idx = sequence_index if sequence_index >= 0 else len(inputs) - 1
        inputs[idx] = ExperimentInput(
            sequence=inputs[idx].sequence,
            observation_payload=dict(inputs[idx].observation_payload),
            action_type=action_type,
            action_params=dict(action_params or {}),
        )
        return self.lab.branch_alternative(experiment_id, label=label, inputs=inputs)

    # ── inspect ───────────────────────────────────────────────────────

    def episode_report(self) -> dict[str, Any]:
        ep = self.memory.reconstruct_episode(self.episode_id)
        return {
            "episode_id": self.episode_id,
            "steps": len(self.trace),
            "trace": [t.as_dict() for t in self.trace],
            "memory": [r.as_dict() for r in ep],
            "mirror": self.mirror.snapshot().as_dict(),
            "decisions": self.observatory.stats(),
            "predictions": self.predictions.accuracy(),
            "inputs_captured": len(self.episode_inputs),
        }

    def _predict_consequence(self, action_type: str) -> str:
        if action_type in {"REMEMBER", "ATTEND", "WAIT", "QUERY_FIELD", "SET_GOAL", "SPEAK"}:
            return "observed"
        if action_type in {"PROBE", "ACTUATE"}:
            return "observed"
        return "pending"

    def _persist_trace(self, step: TraceStep) -> None:
        path = self.root / "episode_trace.jsonl"
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(step.as_dict(), sort_keys=True) + "\n")
        except OSError:
            pass
