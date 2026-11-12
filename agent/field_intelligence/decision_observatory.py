"""Decision Observatory — witness for Duck Gate / Operator ABI decisions.

Does not modify selection policy or authorize actions.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from agent.hashutil import uid
from duck_gate.candidates import CandidateExcitation
from duck_gate.scoring import DEFAULT_WEIGHTS, score
from duck_gate.selector import Mode, select


class SelectionMode(str, Enum):
    DUCK = "DUCK"
    RANDOM = "RANDOM"


@dataclass
class DecisionRecord:
    decision_id: str
    episode_id: str
    observation_id: str
    candidates: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    weights: dict[str, float]
    selected_candidate_id: str | None
    selection_mode: str
    selection_rationale: str
    proposal_id: str | None = None
    admission_status: str | None = None
    rejection_reason: str | None = None
    resulting_tick_sequence: int | None = None
    consequence_ref: str | None = None
    created_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionObservatory:
    """Record and query decision traces. Read-only w.r.t. admission."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path("/tmp/metafield/decision_observatory.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[DecisionRecord] = []
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
                if isinstance(obj, dict):
                    self.records.append(
                        DecisionRecord(
                            decision_id=str(obj.get("decision_id") or uid("dec")),
                            episode_id=str(obj.get("episode_id") or ""),
                            observation_id=str(obj.get("observation_id") or ""),
                            candidates=list(obj.get("candidates") or []),
                            scores=list(obj.get("scores") or []),
                            weights=dict(obj.get("weights") or {}),
                            selected_candidate_id=obj.get("selected_candidate_id"),
                            selection_mode=str(obj.get("selection_mode") or "DUCK"),
                            selection_rationale=str(obj.get("selection_rationale") or ""),
                            proposal_id=obj.get("proposal_id"),
                            admission_status=obj.get("admission_status"),
                            rejection_reason=obj.get("rejection_reason"),
                            resulting_tick_sequence=obj.get("resulting_tick_sequence"),
                            consequence_ref=obj.get("consequence_ref"),
                            created_at=float(obj.get("created_at") or 0),
                        )
                    )
        except OSError:
            return

    def _persist(self, rec: DecisionRecord) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.as_dict(), sort_keys=True) + "\n")
        except OSError:
            pass

    def observe_selection(
        self,
        *,
        episode_id: str,
        observation_id: str,
        candidates: list[CandidateExcitation],
        mode: SelectionMode | str = SelectionMode.DUCK,
        seed: int | None = None,
        weights: dict[str, float] | None = None,
    ) -> DecisionRecord:
        if isinstance(mode, str):
            mode = SelectionMode(mode)
        w = dict(weights or DEFAULT_WEIGHTS)
        scored = []
        for c in candidates:
            s = score(c, w)
            scored.append(
                {
                    "candidate_id": c.candidate_id,
                    "score": float(s) if not isinstance(s, dict) else float(s.get("total", 0)),
                    "detail": s if isinstance(s, dict) else {"total": float(s)},
                }
            )
        sel_mode = Mode.DUCK if mode == SelectionMode.DUCK else Mode.RANDOM
        rng = None
        if sel_mode is Mode.RANDOM:
            import random

            rng = random.Random(seed if seed is not None else 0)
        chosen = select(candidates, mode=sel_mode, weights=w, rng=rng)
        selected_id = chosen.candidate_id if chosen is not None else None
        rationale = f"mode={mode.value} selected={selected_id}"

        rec = DecisionRecord(
            decision_id=uid("dec"),
            episode_id=episode_id,
            observation_id=observation_id,
            candidates=[c.as_dict() for c in candidates],
            scores=scored,
            weights=w,
            selected_candidate_id=selected_id,
            selection_mode=mode.value,
            selection_rationale=rationale,
            created_at=time.time(),
        )
        self.records.append(rec)
        self._persist(rec)
        return rec

    def record_admission(
        self,
        decision_id: str,
        *,
        proposal_id: str | None,
        accepted: bool,
        reason: str = "",
        tick_sequence: int | None = None,
        consequence_ref: str | None = None,
    ) -> DecisionRecord | None:
        for r in self.records:
            if r.decision_id == decision_id:
                r.proposal_id = proposal_id
                r.admission_status = "ACCEPTED" if accepted else "REJECTED"
                r.rejection_reason = None if accepted else reason
                r.resulting_tick_sequence = tick_sequence
                r.consequence_ref = consequence_ref
                self._persist(r)
                return r
        return None

    def stats(self) -> dict[str, Any]:
        total = len(self.records)
        accepted = sum(1 for r in self.records if r.admission_status == "ACCEPTED")
        rejected = sum(1 for r in self.records if r.admission_status == "REJECTED")
        by_mode: dict[str, int] = {}
        for r in self.records:
            by_mode[r.selection_mode] = by_mode.get(r.selection_mode, 0) + 1
        return {
            "total": total,
            "accepted": accepted,
            "rejected": rejected,
            "pending": total - accepted - rejected,
            "by_mode": by_mode,
            "admission_rate": (accepted / total) if total else 0.0,
        }
