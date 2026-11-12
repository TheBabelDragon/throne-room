"""SHARED_BODY v2 — live field continuity contract.

Canonical identity + measurement layer connecting physical observations,
Throne Room, MetaField, Field Bus, Reverie, and agent perception.

One observed physical entity retains its identity across every layer.
No fabricated intensities. Missing values remain missing.
"""

from .schema import (
    SCHEMA_VERSION,
    SharedBody,
    SharedBodyError,
    SharedBodyValidationError,
    validate_shared_body,
    measurement_from_region,
)
from .registry import SharedBodyRegistry
from .adapter import (
    from_field_observation_packet,
    from_observation_rows,
    ingest_packet,
)
from .export import (
    write_snapshot,
    write_observation_jsonl,
    snapshot_to_reverie,
    DEFAULT_SNAPSHOT_PATH,
    DEFAULT_JOURNAL_PATH,
)

__all__ = [
    "SCHEMA_VERSION",
    "SharedBody",
    "SharedBodyError",
    "SharedBodyValidationError",
    "validate_shared_body",
    "measurement_from_region",
    "SharedBodyRegistry",
    "from_field_observation_packet",
    "from_observation_rows",
    "ingest_packet",
    "write_snapshot",
    "write_observation_jsonl",
    "snapshot_to_reverie",
    "DEFAULT_SNAPSHOT_PATH",
    "DEFAULT_JOURNAL_PATH",
]
