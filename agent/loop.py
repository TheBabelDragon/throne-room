"""World loop: perceive → self → reason → propose → validate → commit → tick."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.bridge import packet_to_observation
from agent.engine import FieldScheduler, seed_field, tick_summary
from agent.memory import MemoryStore
from agent.operator_abi import AbiDecision, OperatorAbi
from agent.perception import chat_perception, make_synthetic_csi, observation_to_perception
from agent.reason import ReasoningContext, mock_reason
from agent.schemas import ActionProposal, Channel, FieldObservation, PerceptionEvent
from agent.self_state import SelfStateKernel, create_self_state

DT = 0.125


@dataclass
class Turn:
    perception: PerceptionEvent
    proposal: ActionProposal
    decision: AbiDecision
    utterance: str | None
    tick: int
    tick_hash: str


class World:
    def __init__(self, memory_path: Path | None = None) -> None:
        self.scheduler = FieldScheduler(seed_field())
        self.self = create_self_state()
        self.abi = OperatorAbi()
        self.memory = MemoryStore(memory_path)
        self.last_obs: FieldObservation | None = None
        self.last_hash = "00000000"
        self.last_decision: AbiDecision | None = None
        self.last_proposal: ActionProposal | None = None
        self.last_perception: PerceptionEvent | None = None
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "text": "Loop locked. You speak. SELF perceives. ABI validates. Engine commits.",
                "tick": 0,
            }
        ]

    def step(self, obs: FieldObservation | None = None) -> None:
        if obs is None:
            obs = make_synthetic_csi(self.scheduler.sequence + 1)
        self.last_obs = obs
        self.scheduler.bind_observation(obs)
        commit = self.scheduler.step(DT)
        self.last_hash = commit.hash
        if commit.tick.sequence % 8 == 0:
            perc = observation_to_perception(obs, commit.tick.sequence)
            self.self.SET("working.last_csi", {
                "energy": perc.features.get("energy"),
                "rssi": perc.features.get("rssi_dbm"),
                "tick": commit.tick.sequence,
            })

    def ingest_packet(self, packet: dict[str, Any]) -> None:
        obs = packet_to_observation(packet)
        self.step(obs)

    def handle_human(self, text: str) -> Turn | None:
        trimmed = text.strip()
        if not trimmed:
            return None
        tick = self.scheduler.sequence
        perception = chat_perception(trimmed, tick)
        self.last_perception = perception
        self.messages.append({
            "role": "human",
            "text": trimmed,
            "tick": tick,
            "observation_id": perception.id,
        })
        self.self.SET("working.last_utterance", trimmed)
        self.self.SET("attention.target", "chat")
        self.memory.append(
            tick=tick,
            text=f"human: {trimmed}",
            kind="episodic",
            tags=["chat", "human"],
            observation_id=perception.id,
        )

        ctx = self._reasoning_context(perception.id, trimmed)
        proposal = mock_reason(ctx)
        self.last_proposal = proposal

        decision = self.abi.validate(proposal, self.scheduler.field, self.scheduler.sequence + 1)
        self.last_decision = decision

        if decision.accepted and decision.deltas:
            self.scheduler.queue_agent_deltas(decision.deltas)
        if decision.accepted and decision.memory_note:
            self.memory.append(
                tick=self.scheduler.sequence,
                text=decision.memory_note,
                kind="episodic",
                tags=["remember", "agent"],
                observation_id=perception.id,
            )
        if decision.accepted and decision.attend:
            self.self.SET("attention.target", decision.attend)
        if decision.accepted and decision.goal:
            goals = list(self.self.GET("goals") or [])
            goals.append({"id": f"g{len(goals)}", "text": decision.goal, "priority": 1})
            self.self.SET("goals", goals)

        utterance = None
        if decision.accepted and decision.utterance:
            utterance = decision.utterance
            self.messages.append({
                "role": "agent",
                "text": utterance,
                "tick": self.scheduler.sequence,
                "proposal_id": proposal.proposal_id,
            })
        elif not decision.accepted:
            self.messages.append({
                "role": "system",
                "text": f"ABI rejected {proposal.action_type}: {decision.reason}",
                "tick": self.scheduler.sequence,
                "proposal_id": proposal.proposal_id,
            })
        elif decision.accepted:
            utterance = f"{proposal.action_type} committed. {decision.reason}"
            self.messages.append({
                "role": "agent",
                "text": utterance,
                "tick": self.scheduler.sequence,
                "proposal_id": proposal.proposal_id,
            })

        self.self.SET("working.last_action", {
            "type": proposal.action_type,
            "accepted": decision.accepted,
            "provider": "mock",
        })
        self.step()
        return Turn(
            perception=perception,
            proposal=proposal,
            decision=decision,
            utterance=utterance,
            tick=self.scheduler.sequence,
            tick_hash=self.last_hash,
        )

    def snapshot(self) -> dict[str, Any]:
        field = self.scheduler.field
        peak, pval = field.peak(Channel.Energy)
        tick = self.scheduler.last
        summary = tick_summary(tick) if tick else {"delta_count": 0, "by_system": {}}
        return {
            "sequence": self.scheduler.sequence,
            "time": self.scheduler.time,
            "energy_sum": field.sum(Channel.Energy),
            "info_sum": field.sum(Channel.Information),
            "temp_sum": field.sum(Channel.Temperature),
            "energy_peak": {"x": peak.x, "z": peak.z, "value": pval},
            "integrity": self.self.integrity(),
            "attention": self.self.peek("attention.target"),
            "goals": self.self.peek("goals"),
            "capabilities": sorted(self.abi.capabilities),
            "tick_hash": self.last_hash,
            "delta_count": summary.get("delta_count", 0),
            "by_system": summary.get("by_system", {}),
            "last_proposal": self.last_proposal.as_dict() if self.last_proposal else None,
            "last_accepted": None if self.last_decision is None else self.last_decision.accepted,
        }

    def _reasoning_context(self, observation_id: str, user_text: str) -> ReasoningContext:
        field = self.scheduler.field
        peak, pval = field.peak(Channel.Energy)
        goals = self.self.peek("goals") or []
        energy = 0.0
        if self.last_obs:
            energy = next((r.observed for r in self.last_obs.regions if r.name == "csi_energy"), 0.0)
        return ReasoningContext(
            observation_id=observation_id,
            user_text=user_text,
            tick=self.scheduler.sequence,
            energy_sum=field.sum(Channel.Energy),
            info_sum=field.sum(Channel.Information),
            temp_sum=field.sum(Channel.Temperature),
            energy_peak=(peak.x, peak.z, pval),
            csi_energy=energy,
            csi_rssi=self.last_obs.rssi_dbm if self.last_obs else -90.0,
            integrity=self.self.integrity(),
            goals=[g.get("text", "") for g in goals if isinstance(g, dict)],
            attention=str(self.self.peek("attention.target") or "chat"),
            memories=[m.text for m in self.memory.recent(4)],
        )
