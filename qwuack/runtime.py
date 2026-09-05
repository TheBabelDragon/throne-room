"""Adapter between Qwuack and the existing Throne Room agent loop.

Wake → PerceptionEvent → SELF → policy → ActionProposal → ABI →
observe FieldTick → repeat.

Does not own FieldTick, FieldDelta, the scheduler, replay, UDP :4210,
the language protocol, or Aurora / ESCAPE.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent.feeds import DEFAULT_AURORA, DEFAULT_CSI, DEFAULT_MEMORY, DEFAULT_TICKS
from agent.loop import Turn, World
from agent.operator_abi import AbiDecision
from agent.perception import make_synthetic_csi, observation_to_perception
from agent.schemas import ActionProposal, FieldObservation, PerceptionEvent
from qwuack.identity import QWUACK, QwuackIdentity
from qwuack.policy import decide, perception_view

STATUS_PATH = Path("/tmp/metafield/qwuack_status.json")
DT_PAUSE = 0.25


@dataclass
class Status:
    state: str = "asleep"
    habitat: str = QWUACK.habitat
    perception: str = "idle"
    sequence: int = 0
    last_action: str = "WAIT"
    authorization: str = "none"
    consequence: str = "none"
    observation_id: str | None = None
    proposal_id: str | None = None
    tick_hash: str | None = None
    live: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        return (
            "QWUACK\n"
            "-------\n"
            f"state:          {self.state}\n"
            f"habitat:        {self.habitat}\n"
            f"perception:     {self.perception}\n"
            f"sequence:       {self.sequence}\n"
            f"last_action:    {self.last_action}\n"
            f"authorization:  {self.authorization}\n"
            f"consequence:    {self.consequence}\n"
        )


class Runtime:
    """Qwuack as a tenant of an existing World. Not a second landlord."""

    def __init__(
        self,
        world: World | None = None,
        identity: QwuackIdentity = QWUACK,
        status_path: Path | None = STATUS_PATH,
    ) -> None:
        self.world = world or World()
        self.identity = identity
        self.status_path = status_path
        self.status = Status(habitat=identity.habitat)
        self.last_turn: Turn | None = None
        self.awake = False

    def wake(self) -> Status:
        """Stamp identity into SELF. Does not touch the Field."""
        self.world.self.SET("identity.name", self.identity.name)
        self.world.self.SET("identity.species", self.identity.species)
        self.world.self.SET("identity.habitat", self.identity.habitat)
        self.world.self.SET("identity.role", self.identity.role)
        self.world.self.SET("identity.agent_id", self.identity.agent_id)
        self.world.self.SET("beliefs.loop", "observe\u2192propose\u2192validate\u2192commit")
        self.awake = True
        self.status.state = "awake"
        self._emit_status()
        return self.status

    def perceive(self, event: PerceptionEvent) -> ActionProposal:
        if not self.awake:
            self.wake()
        view = perception_view(event)
        snapshot = self.world.self.snapshot()
        caps = frozenset(self.world.abi.capabilities)
        return decide(
            view,
            snapshot,
            caps,
            last_tick=self.world.scheduler.last,
            identity=self.identity,
        )

    def submit(self, proposal: ActionProposal) -> AbiDecision:
        tick = self.world.scheduler.sequence + 1
        return self.world.abi.validate(proposal, self.world.scheduler.field, tick)

    def apply_decision(self, decision: AbiDecision, observation_id: str) -> None:
        """Queue authorized deltas. Update SELF / memory. Never write Field."""
        if decision.accepted and decision.deltas:
            self.world.scheduler.queue_agent_deltas(decision.deltas)
        if decision.accepted and decision.memory_note:
            self.world.memory.append(
                tick=self.world.scheduler.sequence,
                text=decision.memory_note,
                kind="episodic",
                tags=["qwuack", "remember"],
                observation_id=observation_id,
            )
        if decision.accepted and decision.attend:
            self.world.self.SET("attention.target", decision.attend)
        if decision.accepted and decision.goal:
            goals = list(self.world.self.GET("goals") or [])
            goals.append({"id": f"g{len(goals)}", "text": decision.goal, "priority": 1})
            self.world.self.SET("goals", goals)
        if decision.accepted and decision.utterance:
            self.world.messages.append({
                "role": "agent",
                "text": decision.utterance,
                "tick": self.world.scheduler.sequence,
                "proposal_id": decision.proposal.proposal_id,
            })

    def observe_tick(self, proposal: ActionProposal, decision: AbiDecision, energy_before: float) -> str:
        energy_after = _csi_energy(self.world)
        delta = energy_after - energy_before
        agent_deltas = 0
        last = self.world.scheduler.last
        if last is not None:
            agent_deltas = sum(1 for d in last.deltas if d.system_id == 6)
        if not decision.accepted:
            consequence = "rejected"
        elif agent_deltas > 0:
            consequence = "observed"
        elif proposal.action_type in {"REMEMBER", "ATTEND", "WAIT", "QUERY_FIELD", "SET_GOAL", "SPEAK"}:
            consequence = "observed"
        else:
            consequence = "pending"
        self.world.self.SET("working.qwuack", {
            "last_action": proposal.action_type,
            "last_accepted": decision.accepted,
            "last_reason": decision.reason,
            "last_energy": energy_after,
            "energy_before": energy_before,
            "energy_delta": delta,
            "last_sequence": self.world.scheduler.sequence,
            "agent_deltas": agent_deltas,
            "consequence": consequence,
        })
        return consequence

    def cycle(self, obs: FieldObservation | None = None, *, force_synthetic: bool = False) -> Turn:
        """One closed tenant cycle against the existing World."""
        if not self.awake:
            self.wake()
        if obs is None and (force_synthetic or not self.world.live):
            obs = make_synthetic_csi(self.world.scheduler.sequence + 1)
        if obs is not None:
            self.world.last_obs = obs
        event = observation_to_perception(
            obs if obs is not None else _empty_obs(),
            self.world.scheduler.sequence + 1,
        )
        self.world.last_perception = event
        energy_before = _csi_energy(self.world)
        if obs is not None:
            energy_before = _obs_energy(obs)

        proposal = self.perceive(event)
        self.world.last_proposal = proposal
        decision = self.submit(proposal)
        self.world.last_decision = decision
        self.apply_decision(decision, event.id)

        self.world.step(obs)
        consequence = self.observe_tick(proposal, decision, energy_before)

        turn = Turn(
            perception=event,
            proposal=proposal,
            decision=decision,
            utterance=decision.utterance,
            tick=self.world.scheduler.sequence,
            tick_hash=self.world.last_hash,
        )
        self.last_turn = turn
        self.status = Status(
            state="awake",
            habitat=self.identity.habitat,
            perception="live" if self.world.live and obs is not None and not obs.synthetic else (
                "fixture" if obs is not None and obs.synthetic else "idle"
            ),
            sequence=self.world.scheduler.sequence,
            last_action=proposal.action_type,
            authorization="granted" if decision.accepted else "denied",
            consequence=consequence,
            observation_id=event.id,
            proposal_id=proposal.proposal_id,
            tick_hash=self.world.last_hash,
            live=self.world.live,
        )
        self._emit_status()
        return turn

    def attach_feeds(
        self,
        *,
        csi: Path | None = DEFAULT_CSI,
        aurora: Path | None = DEFAULT_AURORA,
        ticks: Path | None = DEFAULT_TICKS,
        warmup: int = 32,
    ) -> dict[str, int]:
        counts = self.world.attach_feeds(csi=csi, aurora=aurora, ticks=ticks, warmup=warmup)
        self.status.live = True
        self.status.perception = "live"
        self._emit_status()
        return counts

    def follow_once(self) -> Turn | None:
        """Drain existing journals. Never bind UDP."""
        drained = self.world.drain_feeds(max_records=32)
        obs = self.world.last_obs
        if obs is None and drained.get("csi", 0) == 0:
            return None
        return self.cycle(obs)

    def _emit_status(self) -> None:
        if self.status_path is None:
            return
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": "throne.qwuack.status",
                "version": 1,
                **self.status.as_dict(),
                "identity": {
                    "name": self.identity.name,
                    "species": self.identity.species,
                    "habitat": self.identity.habitat,
                    "role": self.identity.role,
                    "agent_id": self.identity.agent_id,
                },
                "capabilities": sorted(self.identity.permitted_capabilities()),
            }
            self.status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            return


def _obs_energy(obs: FieldObservation) -> float:
    return next((r.observed for r in obs.regions if r.name == "csi_energy"), 0.0)


def _csi_energy(world: World) -> float:
    if world.last_obs is None:
        return 0.0
    return _obs_energy(world.last_obs)


def _empty_obs() -> FieldObservation:
    from agent.schemas import FieldObservation as FO

    return FO(
        body_id="qwuack-empty",
        body_type="none",
        timestamp="0",
        regions=[],
        synthetic=True,
        valid=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Qwuack runtime — tenant of the Throne Room World. Does not bind UDP :4210.",
    )
    parser.add_argument("--live", action="store_true", help="Follow CSI/Aurora journals; no UDP bind")
    parser.add_argument("--follow", action="store_true", help="Keep following after warmup")
    parser.add_argument("--once", action="store_true", help="One cycle then exit")
    parser.add_argument("--ticks", type=int, default=1, help="Synthetic warmup cycles when not --live")
    parser.add_argument("--csi", type=Path, default=None)
    parser.add_argument("--aurora", type=Path, default=None)
    parser.add_argument("--journal", type=Path, default=None)
    parser.add_argument("--interval", type=float, default=DT_PAUSE)
    args = parser.parse_args(argv)

    world = World(memory_path=DEFAULT_MEMORY if args.live else None)
    runtime = Runtime(world=world)
    runtime.wake()
    print(runtime.status.render(), flush=True)

    if args.live:
        counts = runtime.attach_feeds(
            csi=args.csi or DEFAULT_CSI,
            aurora=args.aurora or DEFAULT_AURORA,
            ticks=args.journal or DEFAULT_TICKS,
        )
        print(
            f"[qwuack] attached to observer journals  "
            f"csi={counts['csi']} aurora={counts['aurora']}  (no UDP bind)",
            flush=True,
        )
        turn = runtime.follow_once()
        if turn is not None:
            print(runtime.status.render(), flush=True)
        if args.once or not args.follow:
            return 0
        try:
            while True:
                runtime.follow_once()
                print(runtime.status.render(), flush=True)
                time.sleep(max(0.05, args.interval))
        except KeyboardInterrupt:
            print("[qwuack] halt", flush=True)
            return 0

    for _ in range(max(1, args.ticks)):
        runtime.cycle(force_synthetic=True)
        print(runtime.status.render(), flush=True)
        if args.once:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
