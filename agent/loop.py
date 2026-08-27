"""World loop: perceive → self → reason → propose → validate → commit → tick."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.bridge import aurora_intent_to_proposal, packet_to_observation
from agent.engine import FieldScheduler, seed_field, tick_summary
from agent.feeds import JsonlCursor, append_jsonl
from agent.language.arm import LanguageArm
from agent.language.protocol import ConversationEvent, MemoryReference, context_from_world
from agent.language.trajectories import append_trajectory, trajectory_record
from agent.memory import MemoryStore
from agent.operator_abi import AbiDecision, OperatorAbi
from agent.perception import chat_perception, make_synthetic_csi, observation_to_perception
from agent.schemas import ActionProposal, Channel, FieldObservation, PerceptionEvent
from agent.self_state import create_self_state

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
        self.live = False
        self.csi_cursor: JsonlCursor | None = None
        self.aurora_cursor: JsonlCursor | None = None
        self.ticks_path: Path | None = None
        self.packets_ingested = 0
        self.aurora_seen = 0
        self.arm = LanguageArm()
        self.last_language_context = None
        self.trajectory_path: Path | None = None
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "text": "Loop locked. You speak. SELF perceives. ABI validates. Engine commits.",
                "tick": 0,
            }
        ]

    def attach_feeds(
        self,
        *,
        csi: Path | None = None,
        aurora: Path | None = None,
        ticks: Path | None = None,
        warmup: int = 32,
    ) -> dict[str, int]:
        """Follow live JSONL. Does not bind UDP. Returns warmup ingest counts."""
        if csi is not None or aurora is not None:
            self.live = True
        if ticks is not None and not isinstance(ticks, Path):
            raise TypeError(f"ticks journal must be a Path, got {type(ticks).__name__}")
        self.ticks_path = ticks
        counts = {"csi": 0, "aurora": 0}
        if csi is not None:
            self.csi_cursor = JsonlCursor(csi, keep=max(1, warmup))
            for pkt in self.csi_cursor.catch_up_keep(warmup):
                if self.ingest_packet(pkt):
                    counts["csi"] += 1
        if aurora is not None:
            self.aurora_cursor = JsonlCursor(aurora, keep=max(1, warmup))
            for pkt in self.aurora_cursor.catch_up_keep(warmup):
                if self.observe_aurora(pkt):
                    counts["aurora"] += 1
        return counts

    def drain_feeds(self, max_records: int = 64) -> dict[str, int]:
        counts = {"csi": 0, "aurora": 0, "backlog": 0}
        if self.csi_cursor is not None:
            for pkt in self.csi_cursor.poll(max_records=max_records):
                try:
                    if self.ingest_packet(pkt):
                        counts["csi"] += 1
                except Exception:
                    continue
            counts["backlog"] = self.csi_cursor.backlog_bytes()
        if self.aurora_cursor is not None:
            for pkt in self.aurora_cursor.poll(max_records=max_records):
                try:
                    if self.observe_aurora(pkt):
                        counts["aurora"] += 1
                except Exception:
                    continue
        return counts

    def step(self, obs: FieldObservation | None = None, *, force_synthetic: bool = False) -> None:
        if obs is None and (force_synthetic or not self.live):
            obs = make_synthetic_csi(self.scheduler.sequence + 1)
        if obs is not None:
            self.last_obs = obs
        self.scheduler.bind_observation(obs)
        commit = self.scheduler.step(DT)
        self.last_hash = commit.hash
        if obs is not None and commit.tick.sequence % 8 == 0:
            perc = observation_to_perception(obs, commit.tick.sequence)
            self.self.SET("working.last_csi", {
                "energy": perc.features.get("energy"),
                "rssi": perc.features.get("rssi_dbm"),
                "tick": commit.tick.sequence,
                "body": obs.body_id,
                "synthetic": obs.synthetic,
            })
        self._journal_tick(commit.tick.sequence)

    def ingest_packet(self, packet: dict[str, Any]) -> bool:
        obs = packet_to_observation(packet)
        if obs is None:
            return False
        self.step(obs)
        self.packets_ingested += 1
        return True

    def observe_aurora(self, intent: dict[str, Any]) -> bool:
        """See an Aurora journal line. Local FieldDelta only. Not a hardware fire."""
        if not isinstance(intent, dict):
            return False
        if not (intent.get("action") or intent.get("type")):
            return False
        proposal = aurora_intent_to_proposal(intent, observation_id=f"aurora_{self.scheduler.sequence}")
        decision = self.abi.validate(proposal, self.scheduler.field, self.scheduler.sequence + 1)
        self.self.SET("working.last_aurora", {
            "action": proposal.action_type,
            "accepted": decision.accepted,
            "reason": proposal.rationale,
            "tick": self.scheduler.sequence,
        })
        if decision.accepted and decision.deltas:
            self.scheduler.queue_agent_deltas(decision.deltas)
            self.step(None)
        if decision.accepted and decision.attend:
            self.self.SET("attention.target", decision.attend)
        self.memory.append(
            tick=self.scheduler.sequence,
            text=f"aurora: {proposal.action_type} {proposal.rationale}",
            kind="episodic",
            tags=["aurora", proposal.action_type.lower()],
        )
        self.aurora_seen += 1
        return True

    def handle_human(self, text: str) -> Turn | None:
        trimmed = text.strip()
        if not trimmed:
            return None
        self.drain_feeds(max_records=24)
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

        ctx = self._language_context(perception.id, trimmed)
        self.last_language_context = ctx
        output = self.arm.act(ctx)
        proposal = output.proposal
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
            utterance = (
                decision.utterance
                or output.text
                or f"{proposal.action_type} committed. {decision.reason}"
            )
            self.messages.append({
                "role": "agent",
                "text": utterance,
                "tick": self.scheduler.sequence,
                "proposal_id": proposal.proposal_id,
            })

        self.self.SET("working.last_action", {
            "type": proposal.action_type,
            "accepted": decision.accepted,
            "provider": output.source,
            "tokenizer": output.tokenizer_version,
            "confidence": output.confidence,
            "predicted": output.predicted_action,
            "abstained": output.abstained,
        })
        self.step(None)
        if self.trajectory_path is not None:
            append_trajectory(
                self.trajectory_path,
                trajectory_record(
                    ctx=ctx,
                    output=output,
                    sequence=self.scheduler.sequence,
                    tick_hash=self.last_hash,
                    world_response={
                        "energy_sum": self.scheduler.field.sum(Channel.Energy),
                        "info_sum": self.scheduler.field.sum(Channel.Information),
                    },
                    accepted=bool(decision.accepted),
                ),
            )
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
            "live": self.live,
            "packets_ingested": self.packets_ingested,
            "aurora_seen": self.aurora_seen,
            "csi_body": None if self.last_obs is None else self.last_obs.body_id,
            "csi_synthetic": None if self.last_obs is None else self.last_obs.synthetic,
            "csi_rssi": None if self.last_obs is None else self.last_obs.rssi_dbm,
            "arm_mode": self.arm.mode,
            "arm_source": None if self.arm.last is None else self.arm.last.source,
            "arm_tokens": 0 if self.arm.last is None else len(self.arm.last.tokens),
            "arm_confidence": None if self.arm.last is None else self.arm.last.confidence,
            "arm_predicted": None if self.arm.last is None else self.arm.last.predicted_action,
            "arm_learn_steps": getattr(self.arm, "learn_steps", 0),
            "tokenizer": self.arm.tokenizer.version,
        }

    def _journal_tick(self, sequence: int) -> None:
        if not isinstance(self.ticks_path, Path):
            return
        tick = self.scheduler.last
        summary = tick_summary(tick) if tick else {}
        append_jsonl(self.ticks_path, {
            "schema": "metafield.tick",
            "sequence": sequence,
            "time": self.scheduler.time,
            "hash": self.last_hash,
            "delta_count": summary.get("delta_count", 0),
            "by_system": summary.get("by_system", {}),
            "csi_body": None if self.last_obs is None else self.last_obs.body_id,
            "synthetic": None if self.last_obs is None else self.last_obs.synthetic,
        })

    def _language_context(self, observation_id: str, user_text: str):
        field = self.scheduler.field
        peak, pval = field.peak(Channel.Energy)
        goals = self.self.peek("goals") or []
        energy = 0.0
        if self.last_obs:
            energy = next((r.observed for r in self.last_obs.regions if r.name == "csi_energy"), 0.0)
        convo: list[ConversationEvent] = []
        for m in self.messages[-8:]:
            role = m.get("role")
            mapped = "user" if role == "human" else ("arm" if role == "agent" else "system")
            convo.append(ConversationEvent(role=mapped, text=str(m.get("text") or ""), tick=int(m.get("tick") or 0)))
        mems = [
            MemoryReference(id=e.id, tick=e.tick, text=e.text, kind=e.kind)
            for e in self.memory.recent(4)
        ]
        return context_from_world(
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
            body_id=None if self.last_obs is None else self.last_obs.body_id,
            goals=[g.get("text", "") for g in goals if isinstance(g, dict)],
            attention=str(self.self.peek("attention.target") or "chat"),
            memories=mems,
            capabilities=sorted(self.abi.capabilities),
            conversation=convo,
        )
