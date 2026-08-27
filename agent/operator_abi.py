"""Capability-based operator ABI.

The agent proposes. This validates. The engine commits.
act.device is never granted by default — Aurora's Redis ESCAPE
remains the only path onto real swarm actuators.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from agent.engine import N, VoxelField
from agent.hashutil import uid
from agent.schemas import (
    ACTION_CAPABILITY,
    ACTION_TYPES,
    DEFAULT_CAPABILITIES,
    SYS,
    ActionProposal,
    Capability,
    CellCoord,
    Channel,
    CommittedAction,
    FieldDelta,
)


@dataclass
class AbiDecision:
    accepted: bool
    reason: str
    proposal: ActionProposal
    action: CommittedAction
    deltas: list[FieldDelta]
    utterance: str | None = None
    memory_note: str | None = None
    attend: str | None = None
    goal: str | None = None
    query: str | None = None


class OperatorAbi:
    def __init__(
        self,
        agent_id: str = "self-0",
        capabilities: tuple[Capability, ...] | list[Capability] = DEFAULT_CAPABILITIES,
    ) -> None:
        self.agent_id = agent_id
        self.capabilities: set[str] = set(capabilities)

    def has(self, cap: str) -> bool:
        return cap in self.capabilities

    def grant(self, cap: Capability) -> None:
        self.capabilities.add(cap)

    def revoke(self, cap: str) -> None:
        self.capabilities.discard(cap)

    def validate(self, proposal: ActionProposal, field: VoxelField, tick: int) -> AbiDecision:
        capability = ACTION_CAPABILITY.get(proposal.action_type, "observe.field")

        def base(accepted: bool, reason: str, deltas: list[FieldDelta] | None = None) -> CommittedAction:
            deltas = deltas or []
            return CommittedAction(
                agent_id=self.agent_id,
                capability=capability,
                observation_id=proposal.originating_observation,
                proposal_id=proposal.proposal_id,
                tick=tick,
                action_type=proposal.action_type,
                accepted=accepted,
                reason=reason,
                resulting_delta_count=len(deltas),
            )

        if proposal.action_type not in ACTION_TYPES:
            action = base(False, f"Unknown action_type: {proposal.action_type}")
            return AbiDecision(False, action.reason, proposal, action, [])

        if not self.has(capability):
            action = base(False, f"Missing capability: {capability}")
            return AbiDecision(False, action.reason, proposal, action, [])

        kind = proposal.action_type
        if kind == "SPEAK":
            text = str(proposal.parameters.get("text") or "").strip()
            if not text:
                action = base(False, "SPEAK requires parameters.text")
                return AbiDecision(False, action.reason, proposal, action, [])
            cell = _clamp_cell(proposal.target, field)
            old = field.sample(cell, Channel.Information)
            nxt = min(1.0, old + 0.35 * (1 - old))
            deltas = [FieldDelta(cell, Channel.Information, old, nxt, tick, SYS.AGENT)]
            action = base(True, "committed SPEAK", deltas)
            return AbiDecision(True, action.reason, proposal, action, deltas, utterance=text[:2000])

        if kind == "PROBE":
            magnitude = _clamp01(float(proposal.parameters.get("magnitude", 0.45)))
            cell = _clamp_cell(proposal.target, field, proposal.parameters)
            deltas: list[FieldDelta] = []
            for dz in range(-1, 2):
                for dx in range(-1, 2):
                    c = CellCoord(cell.x + dx, 0, cell.z + dz)
                    if not (0 <= c.x < N and 0 <= c.z < N):
                        continue
                    old = field.sample(c, Channel.Energy)
                    w = magnitude * math.exp(-0.7 * (dx * dx + dz * dz))
                    nxt = min(1.0, old + w * (1 - old))
                    deltas.append(FieldDelta(c, Channel.Energy, old, nxt, tick, SYS.AGENT))
            action = base(True, f"committed PROBE @ {cell.x},{cell.z}", deltas)
            return AbiDecision(True, action.reason, proposal, action, deltas, utterance=_voice(proposal, action.reason))

        if kind == "REMEMBER":
            note = str(proposal.parameters.get("note") or proposal.rationale or "").strip()
            if not note:
                action = base(False, "REMEMBER requires parameters.note")
                return AbiDecision(False, action.reason, proposal, action, [])
            action = base(True, "committed REMEMBER")
            return AbiDecision(True, action.reason, proposal, action, [], memory_note=note, utterance=_voice(proposal, f"REMEMBER. {note}"))

        if kind == "ATTEND":
            target = str(proposal.parameters.get("target") or proposal.target or "field").strip()
            action = base(True, f"committed ATTEND {target}")
            return AbiDecision(True, action.reason, proposal, action, [], attend=target, utterance=_voice(proposal, action.reason))

        if kind == "SET_GOAL":
            text = str(proposal.parameters.get("text") or "").strip()
            if not text:
                action = base(False, "SET_GOAL requires parameters.text")
                return AbiDecision(False, action.reason, proposal, action, [])
            action = base(True, "committed SET_GOAL")
            return AbiDecision(True, action.reason, proposal, action, [], goal=text, utterance=_voice(proposal, f"SET_GOAL. {text}"))

        if kind == "QUERY_FIELD":
            action = base(True, "committed QUERY_FIELD")
            return AbiDecision(True, action.reason, proposal, action, [], query="field", utterance=_voice(proposal, "QUERY_FIELD"))

        action = base(True, "committed WAIT")
        return AbiDecision(True, action.reason, proposal, action, [], utterance=_voice(proposal, "WAIT"))


def _voice(proposal: ActionProposal, fallback: str) -> str:
    params = proposal.parameters or {}
    for key in ("utterance", "text"):
        s = str(params.get(key) or "").strip()
        if s:
            return s[:2000]
    return fallback[:2000]


def _clamp01(n: float) -> float:
    if n != n:  # NaN
        return 0.4
    return max(0.05, min(0.95, n))


def _clamp_cell(
    target: str,
    field: VoxelField,
    params: dict | None = None,
) -> CellCoord:
    params = params or {}
    try:
        px = float(params.get("x"))  # type: ignore[arg-type]
        pz = float(params.get("z", params.get("y")))  # type: ignore[arg-type]
        if px == px and pz == pz:
            return CellCoord(
                max(0, min(N - 1, round(px))),
                0,
                max(0, min(N - 1, round(pz))),
            )
    except (TypeError, ValueError):
        pass
    m = re.match(r"^(\d+)\s*,\s*(\d+)", str(target or ""))
    if m:
        return CellCoord(
            max(0, min(N - 1, int(m.group(1)))),
            0,
            max(0, min(N - 1, int(m.group(2)))),
        )
    peak, _ = field.peak(Channel.Energy)
    return peak


def make_proposal(
    *,
    action_type: str,
    parameters: dict,
    target: str,
    rationale: str,
    confidence: float,
    originating_observation: str,
    agent_id: str = "self-0",
) -> ActionProposal:
    return ActionProposal(
        proposal_id=uid("prp"),
        action_type=action_type,
        parameters=parameters,
        target=target,
        rationale=rationale,
        confidence=confidence,
        originating_observation=originating_observation,
        agent_id=agent_id,
        capability=ACTION_CAPABILITY.get(action_type, "observe.field"),
    )
