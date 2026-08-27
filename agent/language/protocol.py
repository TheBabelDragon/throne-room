"""Language-arm protocol. Defined before any model.

Any local runtime that maps LanguageContext → LanguageOutput can be the arm.
The transformer is one implementation. Teacher policy is another. An API
chatbot is neither the architecture nor the default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from agent.schemas import SCHEMA_VERSION, ActionProposal

SCHEMA_LANGUAGE = "metafield.language_context"
SCHEMA_OUTPUT = "metafield.language_output"
SCHEMA_TRAJECTORY = "metafield.language_trajectory"
SCHEMA_CONVO = "metafield.conversation_event"
SCHEMA_MEMREF = "metafield.memory_reference"
SCHEMA_POBS = "metafield.participant_observation"


@dataclass
class MemoryReference:
    id: str
    tick: int
    text: str
    kind: str
    schema: str = SCHEMA_MEMREF
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "id": self.id,
            "tick": self.tick,
            "text": self.text,
            "kind": self.kind,
        }


@dataclass
class ConversationEvent:
    role: Literal["user", "arm", "system"]
    text: str
    tick: int
    tokens: list[int] | None = None
    schema: str = SCHEMA_CONVO
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "role": self.role,
            "text": self.text,
            "tick": self.tick,
            "tokens": self.tokens,
        }


@dataclass
class ParticipantObservation:
    """What this arm is allowed to see. Capabilities gate the rest."""

    tick: int
    energy_sum: float
    info_sum: float
    temp_sum: float
    energy_peak: tuple[int, int, float]
    csi_energy: float
    csi_rssi: float
    integrity: str
    body_id: str | None
    permitted: list[str] = field(default_factory=list)
    schema: str = SCHEMA_POBS
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "tick": self.tick,
            "energy_sum": round(self.energy_sum, 6),
            "info_sum": round(self.info_sum, 6),
            "temp_sum": round(self.temp_sum, 6),
            "energy_peak": {
                "x": self.energy_peak[0],
                "z": self.energy_peak[1],
                "value": round(self.energy_peak[2], 6),
            },
            "csi_energy": round(self.csi_energy, 6),
            "csi_rssi": round(self.csi_rssi, 3),
            "integrity": self.integrity,
            "body_id": self.body_id,
            "permitted": list(self.permitted),
        }


@dataclass
class LanguageContext:
    observation_id: str
    user_text: str
    observation: ParticipantObservation
    conversation: list[ConversationEvent] = field(default_factory=list)
    memories: list[MemoryReference] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    attention: str = "chat"
    capabilities: list[str] = field(default_factory=list)
    schema: str = SCHEMA_LANGUAGE
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "observation_id": self.observation_id,
            "user_text": self.user_text,
            "observation": self.observation.as_dict(),
            "conversation": [c.as_dict() for c in self.conversation],
            "memories": [m.as_dict() for m in self.memories],
            "goals": list(self.goals),
            "attention": self.attention,
            "capabilities": list(self.capabilities),
        }


@dataclass
class LanguageOutput:
    tokens: list[int]
    text: str
    proposal: ActionProposal
    source: Literal["model", "teacher"]
    tokenizer_version: str
    model_version: str
    prompt_tokens: list[int] = field(default_factory=list)
    confidence: float = 1.0
    predicted_action: str = ""
    abstained: bool = False
    schema: str = SCHEMA_OUTPUT
    version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "tokens": list(self.tokens),
            "text": self.text,
            "proposal": self.proposal.as_dict(),
            "source": self.source,
            "tokenizer_version": self.tokenizer_version,
            "model_version": self.model_version,
            "prompt_tokens": list(self.prompt_tokens),
            "confidence": round(self.confidence, 4),
            "predicted_action": self.predicted_action,
            "abstained": self.abstained,
        }


def context_from_world(
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
    body_id: str | None,
    goals: list[str],
    attention: str,
    memories: list[MemoryReference],
    capabilities: list[str],
    conversation: list[ConversationEvent],
) -> LanguageContext:
    permitted = [c for c in capabilities if c != "act.device"]
    return LanguageContext(
        observation_id=observation_id,
        user_text=user_text,
        observation=ParticipantObservation(
            tick=tick,
            energy_sum=energy_sum,
            info_sum=info_sum,
            temp_sum=temp_sum,
            energy_peak=energy_peak,
            csi_energy=csi_energy,
            csi_rssi=csi_rssi,
            integrity=integrity,
            body_id=body_id,
            permitted=permitted,
        ),
        conversation=conversation[-8:],
        memories=memories[-6:],
        goals=goals,
        attention=attention,
        capabilities=permitted,
    )
