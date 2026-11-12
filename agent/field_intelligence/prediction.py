"""Bounded prediction layer — structured forecasts with evaluation.

A prediction is not a fact. Evaluation requires subsequent real observations.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from agent.hashutil import uid


class PredictionEvalStatus(str, Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    MISMATCHED = "MISMATCHED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class Prediction:
    prediction_id: str
    episode_id: str
    source_observation_ids: list[str]
    target_event: str
    expected_outcome: str
    confidence: float
    prediction_sequence: int
    evaluation_status: PredictionEvalStatus = PredictionEvalStatus.PENDING
    actual_outcome: str | None = None
    evaluated_at: float | None = None
    created_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evaluation_status"] = self.evaluation_status.value
        return d


class PredictionStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path("/tmp/metafield/predictions.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.predictions: list[Prediction] = []
        self._seq = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                try:
                    status = PredictionEvalStatus(str(obj.get("evaluation_status") or "PENDING"))
                except ValueError:
                    status = PredictionEvalStatus.PENDING
                p = Prediction(
                    prediction_id=str(obj.get("prediction_id") or uid("pred")),
                    episode_id=str(obj.get("episode_id") or ""),
                    source_observation_ids=list(obj.get("source_observation_ids") or []),
                    target_event=str(obj.get("target_event") or ""),
                    expected_outcome=str(obj.get("expected_outcome") or ""),
                    confidence=float(obj.get("confidence") if obj.get("confidence") is not None else 0.5),
                    prediction_sequence=int(obj.get("prediction_sequence") or 0),
                    evaluation_status=status,
                    actual_outcome=obj.get("actual_outcome"),
                    evaluated_at=obj.get("evaluated_at"),
                    created_at=float(obj.get("created_at") or 0),
                )
                self.predictions.append(p)
                self._seq = max(self._seq, p.prediction_sequence)
        except OSError:
            return

    def _persist(self, p: Prediction) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(p.as_dict(), sort_keys=True) + "\n")
        except OSError:
            pass

    def predict(
        self,
        *,
        episode_id: str,
        source_observation_ids: list[str],
        target_event: str,
        expected_outcome: str,
        confidence: float = 0.5,
    ) -> Prediction:
        self._seq += 1
        p = Prediction(
            prediction_id=uid("pred"),
            episode_id=episode_id,
            source_observation_ids=list(source_observation_ids),
            target_event=target_event,
            expected_outcome=expected_outcome,
            confidence=float(confidence),
            prediction_sequence=self._seq,
            evaluation_status=PredictionEvalStatus.PENDING,
            created_at=time.time(),
        )
        self.predictions.append(p)
        self._persist(p)
        return p

    def evaluate(self, prediction_id: str, actual_outcome: str) -> Prediction:
        for p in self.predictions:
            if p.prediction_id != prediction_id:
                continue
            p.actual_outcome = actual_outcome
            p.evaluated_at = time.time()
            exp = p.expected_outcome.strip().lower()
            act = actual_outcome.strip().lower()
            if exp == act:
                p.evaluation_status = PredictionEvalStatus.MATCHED
            elif exp and act and (exp in act or act in exp):
                p.evaluation_status = PredictionEvalStatus.PARTIAL
            elif not act:
                p.evaluation_status = PredictionEvalStatus.UNRESOLVED
            else:
                p.evaluation_status = PredictionEvalStatus.MISMATCHED
            self._persist(p)
            return p
        raise KeyError(f"unknown prediction {prediction_id}")

    def pending(self) -> list[Prediction]:
        return [p for p in self.predictions if p.evaluation_status == PredictionEvalStatus.PENDING]

    def accuracy(self) -> dict[str, Any]:
        evaluated = [
            p
            for p in self.predictions
            if p.evaluation_status
            in (
                PredictionEvalStatus.MATCHED,
                PredictionEvalStatus.PARTIAL,
                PredictionEvalStatus.MISMATCHED,
            )
        ]
        if not evaluated:
            return {"n": 0, "matched": 0, "partial": 0, "mismatched": 0, "match_rate": 0.0}
        matched = sum(1 for p in evaluated if p.evaluation_status == PredictionEvalStatus.MATCHED)
        partial = sum(1 for p in evaluated if p.evaluation_status == PredictionEvalStatus.PARTIAL)
        mismatched = sum(1 for p in evaluated if p.evaluation_status == PredictionEvalStatus.MISMATCHED)
        return {
            "n": len(evaluated),
            "matched": matched,
            "partial": partial,
            "mismatched": mismatched,
            "match_rate": matched / len(evaluated),
        }
