"""SHARED_BODY v2 — live field continuity contract.

Canonical identity + measurement layer connecting physical observations,
Throne Room, MetaField, Field Bus, Reverie, and agent perception.

One observed physical entity retains its identity across every layer.
No fabricated intensities. Missing values remain missing.

Imports are soft: incomplete landings must not break observer/agent imports.
"""

from __future__ import annotations

SCHEMA_VERSION = "2.0"

try:
    from .schema import (
        SharedBody,
        SharedBodyError,
        SharedBodyValidationError,
        validate_shared_body,
        measurement_from_region,
        make_observation_id,
        bus_node_to_body_id,
        body_id_to_bus_node,
    )
except ImportError:  # pragma: no cover
    SharedBody = None  # type: ignore
    SharedBodyError = Exception  # type: ignore
    SharedBodyValidationError = Exception  # type: ignore
    validate_shared_body = None  # type: ignore
    measurement_from_region = None  # type: ignore
    make_observation_id = None  # type: ignore
    bus_node_to_body_id = None  # type: ignore
    body_id_to_bus_node = None  # type: ignore

try:
    from .registry import SharedBodyRegistry
except ImportError:  # pragma: no cover
    SharedBodyRegistry = None  # type: ignore

try:
    from .adapter import (
        from_field_observation_packet,
        from_observation_rows,
        ingest_packet,
    )
except ImportError:  # pragma: no cover
    from_field_observation_packet = None  # type: ignore
    from_observation_rows = None  # type: ignore
    ingest_packet = None  # type: ignore

try:
    from .export import (
        write_snapshot,
        write_observation_jsonl,
        snapshot_to_reverie,
        DEFAULT_SNAPSHOT_PATH,
        DEFAULT_JOURNAL_PATH,
    )
except ImportError:  # pragma: no cover
    write_snapshot = None  # type: ignore
    write_observation_jsonl = None  # type: ignore
    snapshot_to_reverie = None  # type: ignore
    DEFAULT_SNAPSHOT_PATH = None  # type: ignore
    DEFAULT_JOURNAL_PATH = None  # type: ignore

__all__ = [
    "SCHEMA_VERSION",
    "SharedBody",
    "SharedBodyError",
    "SharedBodyValidationError",
    "validate_shared_body",
    "measurement_from_region",
    "make_observation_id",
    "bus_node_to_body_id",
    "body_id_to_bus_node",
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
