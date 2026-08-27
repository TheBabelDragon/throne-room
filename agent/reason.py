"""ReasoningProvider. Mock is deterministic enough to test the loop.

A live LLM is optional and *outside* FieldTick. Never call a model from
inside the scheduler.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent.operator_abi import make_proposal
from agent.schemas import ACTION_TYPES, ActionProposal


class ReasoningContext:
    def __init__(
        self,
        *,
        observation_id: str,
        user_text: str,
        tick: int,
        energy_sum: float,
        info_sum: float,
        temp_sum: float,
        energy_peak: tuple[int, int, float],
        csi_energy: float,
        csi_rssi: float,
        integrity: str,
        goals: list[str],
        attention: str,
        memories: list[str],
    ) -> None:
        self.observation_id = observation_id
        self.user_text = user_text
        self.tick = tick
        self.energy_sum = energy_sum
        self.info_sum = info_sum
        self.temp_sum = temp_sum
        self.energy_peak = energy_peak
        self.csi_energy = csi_energy
        self.csi_rssi = csi_rssi
        self.integrity = integrity
        self.goals = goals
        self.attention = attention
        self.memories = memories


def mock_reason(ctx: ReasoningContext) -> ActionProposal:
    text = ctx.user_text.lower()
    peak = f"{ctx.energy_peak[0]},{ctx.energy_peak[1]}"

    if re.search(r"\b(probe|inject|nudge|excite|perturb)\b", text):
        return make_proposal(
            action_type="PROBE",
            parameters={"x": ctx.energy_peak[0], "z": ctx.energy_peak[1], "magnitude": 0.55},
            target=peak,
            rationale="Operator asked for an active probe at the current energy peak.",
            confidence=0.86,
            originating_observation=ctx.observation_id,
        )
    if re.search(r"\b(remember|memor(y|ise|ize)|note this|store)\b", text):
        note = (
            f"Tick {ctx.tick}: energy {ctx.energy_sum:.2f}, "
            f"CSI {ctx.csi_energy:.2f}. {ctx.user_text}"
        )
        return make_proposal(
            action_type="REMEMBER",
            parameters={"note": note},
            target="memory",
            rationale="Operator asked to retain the current field state.",
            confidence=0.9,
            originating_observation=ctx.observation_id,
        )
    if re.search(r"\b(goal|objective|priority)\b", text):
        cleaned = re.sub(r"^.*?(goal|objective)\s*(is|:)?\s*", "", ctx.user_text, flags=re.I).strip()
        return make_proposal(
            action_type="SET_GOAL",
            parameters={"text": cleaned or ctx.user_text},
            target="goals",
            rationale="Operator updated goals.",
            confidence=0.8,
            originating_observation=ctx.observation_id,
        )
    if re.search(r"\b(wait|hold|pause)\b", text):
        return make_proposal(
            action_type="WAIT",
            parameters={"text": "hold"},
            target="field",
            rationale="Operator asked to wait.",
            confidence=0.8,
            originating_observation=ctx.observation_id,
        )
    if re.search(r"\b(query(\s+the)?\s+field|inspect the lattice|sample the lattice)\b", text):
        return make_proposal(
            action_type="QUERY_FIELD",
            parameters={"text": ctx.user_text},
            target="field",
            rationale="Operator asked to query the field without mutating it.",
            confidence=0.82,
            originating_observation=ctx.observation_id,
        )
    if re.search(r"\b(attend|look at|focus|watch)\b", text):
        target = "csi" if "csi" in text else ("chat" if "chat" in text else "field")
        return make_proposal(
            action_type="ATTEND",
            parameters={"target": target},
            target=target,
            rationale="Shifted attention as requested.",
            confidence=0.84,
            originating_observation=ctx.observation_id,
        )

    memories = " / ".join(ctx.memories[:2]) if ctx.memories else "none yet"
    reply = (
        f"Tick {ctx.tick}. I am SELF — agency without authority. "
        f"Energy Σ {ctx.energy_sum:.2f} (peak {peak} = {ctx.energy_peak[2]:.2f}), "
        f"information Σ {ctx.info_sum:.2f}, CSI energy {ctx.csi_energy:.2f} "
        f"@ {ctx.csi_rssi:.1f} dBm. Attention on {ctx.attention}. "
        f"Integrity {ctx.integrity}. Recent memory: {memories}. "
        f"I can SPEAK, PROBE, REMEMBER, ATTEND — never mutate FieldTick directly."
    )
    return make_proposal(
        action_type="SPEAK",
        parameters={"text": reply},
        target="chat",
        rationale="Language is the first actuator. Report the observed field.",
        confidence=0.78,
        originating_observation=ctx.observation_id,
    )


def parse_proposal(raw: str, ctx: ReasoningContext) -> ActionProposal | None:
    trimmed = raw.strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(trimmed[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    action_type = str(obj.get("action_type") or "SPEAK").upper()
    if action_type not in ACTION_TYPES:
        action_type = "SPEAK"
    params = _sanitize(obj.get("parameters"))
    if "text" not in params:
        params["text"] = trimmed[:400]
    return make_proposal(
        action_type=action_type,
        parameters=params,
        target=str(obj.get("target") or "chat"),
        rationale=str(obj.get("rationale") or ""),
        confidence=float(obj.get("confidence") or 0.6),
        originating_observation=ctx.observation_id,
    )


def _sanitize(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if isinstance(v, (str, int, float, bool)):
            out[str(k)] = v
        elif v is not None:
            out[str(k)] = str(v)
    return out
