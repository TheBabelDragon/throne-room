"""Local language arm — an Aurora participant, not an API client.

Weights = learned capability. SELF = who this arm is. Memory = what
happened. MetaField = what is happening. The model does not define the
architecture; it satisfies a protocol.
"""

from agent.language.arm import LanguageArm
from agent.language.compose import compose, field_line
from agent.language.protocol import (
    ConversationEvent,
    LanguageContext,
    LanguageOutput,
    MemoryReference,
    ParticipantObservation,
    context_from_world,
)

__all__ = [
    "LanguageArm",
    "LanguageContext",
    "LanguageOutput",
    "ConversationEvent",
    "MemoryReference",
    "ParticipantObservation",
    "context_from_world",
    "compose",
    "field_line",
]
