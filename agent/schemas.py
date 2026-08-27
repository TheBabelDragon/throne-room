"""Shared contracts: FieldTick, FieldDelta, ActionProposal, PerceptionEvent.

Mirrors the TypeScript HUD kernel in web/src/. Schema names are stable
so Python observer packets, Aurora intents, and the web HUD can meet here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA = {
    "tick": "metafield.tick",
    "delta": "metafield.delta",
    "observation": "metafield.observation",
    "perception": "metafield.perception",
    "proposal": "metafield.action_proposal",
    "action": "metafield.action",
    "memory": "metafield.memory",
}
SCHEMA_VERSION = 1


class Channel:
    Matter = 0
    Energy = 1
    Temperature = 2
    Pressure = 3
    Charge = 4
    MomentumX = 5
    MomentumY = 6
    MomentumZ = 7
    Entropy = 8
    Information = 9


CHANNEL_COUNT = 10
CHANNEL_NAMES = (
    "matter",
    "energy",
    "temperature",
    "pressure",
    "charge",
    "momentum_x",
    "momentum_y",
    "momentum_z",
    "entropy",
    "information",
)


class SYS:
    DIFFUSION = 1
    INFO_DECAY = 2
    ADVECTION = 3
    CSI_INPUT = 4
    DECAY = 5
    AGENT = 6


SYSTEM_NAMES = {
    1: "diffusion",
    2: "information_decay",
    3: "advection",
    4: "csi",
    5: "decay",
    6: "agent",
}

ACTION_TYPES = ("SPEAK", "PROBE", "REMEMBER", "ATTEND", "SET_GOAL", "QUERY_FIELD", "WAIT")
ActionType = Literal["SPEAK", "PROBE", "REMEMBER", "ATTEND", "SET_GOAL", "QUERY_FIELD", "WAIT"]

Capability = Literal[
    "observe.field",
    "observe.history",
    "act.field",
    "act.device",
    "communicate",
    "remember",
]

DEFAULT_CAPABILITIES: tuple[Capability, ...] = (
    "observe.field",
    "observe.history",
    "act.field",
    "communicate",
    "remember",
)

ACTION_CAPABILITY: dict[str, Capability] = {
    "SPEAK": "communicate",
    "PROBE": "act.field",
    "REMEMBER": "remember",
    "ATTEND": "observe.field",
    "SET_GOAL": "remember",
    "QUERY_FIELD": "observe.field",
    "WAIT": "observe.field",
}

AURORA_TO_ACTION: dict[str, ActionType] = {
    "probe": "PROBE",
    "attention": "ATTEND",
    "hold": "WAIT",
    "scale_down": "WAIT",
}


@dataclass
class CellCoord:
    x: int
    y: int
    z: int

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass
class FieldDelta:
    cell: CellCoord
    channel: int
    old_value: float
    new_value: float
    tick: int
    system_id: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell": self.cell.as_dict(),
            "channel": self.channel,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "tick": self.tick,
            "system_id": self.system_id,
        }


@dataclass
class FieldTick:
    sequence: int
    time: float
    dt: float
    deltas: list[FieldDelta]
    schema: str = SCHEMA["tick"]
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "sequence": self.sequence,
            "time": self.time,
            "dt": self.dt,
            "deltas": [d.as_dict() for d in self.deltas],
        }


@dataclass
class FieldRegion:
    name: str
    observed: float
    confidence: float = 1.0


@dataclass
class FieldObservation:
    body_id: str
    body_type: str
    timestamp: str
    regions: list[FieldRegion]
    csi: list[float] = field(default_factory=list)
    rssi_dbm: float = -90.0
    synthetic: bool = False
    valid: bool = True


@dataclass
class PerceptionEvent:
    id: str
    source: str
    timestamp: str
    tick: int
    modality: str
    features: dict[str, Any]
    confidence: float
    schema: str = SCHEMA["perception"]
    version: int = SCHEMA_VERSION
    coordinates: CellCoord | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("coordinates") is None:
            d.pop("coordinates", None)
        return d


@dataclass
class ActionProposal:
    proposal_id: str
    action_type: str
    parameters: dict[str, Any]
    target: str
    rationale: str
    confidence: float
    originating_observation: str
    agent_id: str
    capability: str
    schema: str = SCHEMA["proposal"]
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommittedAction:
    agent_id: str
    capability: str
    observation_id: str
    proposal_id: str
    tick: int
    action_type: str
    accepted: bool
    reason: str
    resulting_delta_count: int
    schema: str = SCHEMA["action"]
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryEntry:
    id: str
    tick: int
    kind: str
    text: str
    tags: list[str]
    created_at: float
    observation_id: str | None = None
    schema: str = SCHEMA["memory"]
    version: int = SCHEMA_VERSION
