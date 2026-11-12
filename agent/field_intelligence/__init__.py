"""Field Intelligence v1 — World Mirror, Associative Memory, Counterfactual Lab,
Decision Observatory, Prediction, Research bridge, live-path pipeline.

Additive layer on Throne Room. Does not own FieldTick, Operator ABI, or act.device.
Qwuack remains a tenant. Duck Gate remains the admission boundary.
"""

from __future__ import annotations

from agent.field_intelligence.associative_memory import (
    AssociativeMemory,
    MemoryRecord,
    MemoryType,
)
from agent.field_intelligence.counterfactual import (
    CounterfactualLab,
    Experiment,
    ExperimentBranch,
    ExperimentOutcome,
    OutcomeComparison,
)
from agent.field_intelligence.decision_observatory import (
    DecisionObservatory,
    DecisionRecord,
    SelectionMode,
)
from agent.field_intelligence.pipeline import FieldIntelligenceBridge, TraceStep
from agent.field_intelligence.prediction import (
    Prediction,
    PredictionEvalStatus,
    PredictionStore,
)
from agent.field_intelligence.world_mirror import (
    EntityStatus,
    EvidenceKind,
    WorldChange,
    WorldEntity,
    WorldMirror,
    WorldRelation,
    WorldSnapshot,
)

__all__ = [
    "AssociativeMemory",
    "CounterfactualLab",
    "DecisionObservatory",
    "DecisionRecord",
    "EntityStatus",
    "EvidenceKind",
    "Experiment",
    "ExperimentBranch",
    "ExperimentOutcome",
    "FieldIntelligenceBridge",
    "MemoryRecord",
    "MemoryType",
    "OutcomeComparison",
    "Prediction",
    "PredictionEvalStatus",
    "PredictionStore",
    "SelectionMode",
    "TraceStep",
    "WorldChange",
    "WorldEntity",
    "WorldMirror",
    "WorldRelation",
    "WorldSnapshot",
]

__version__ = "0.2.0"
