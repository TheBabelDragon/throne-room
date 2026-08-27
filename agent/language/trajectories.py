"""Trajectory format for later training. Environment first, weights later.

observation → context → action → world response → new observation → language
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.feeds import append_jsonl
from agent.hashutil import canonical, fnv1a
from agent.language.protocol import SCHEMA_TRAJECTORY, LanguageContext, LanguageOutput


def trajectory_record(
    *,
    ctx: LanguageContext,
    output: LanguageOutput,
    sequence: int,
    tick_hash: str,
    world_response: dict[str, Any],
    accepted: bool,
) -> dict[str, Any]:
    rec = {
        "schema": SCHEMA_TRAJECTORY,
        "version": 1,
        "sequence": sequence,
        "tick_hash": tick_hash,
        "accepted": accepted,
        "context": ctx.as_dict(),
        "output": output.as_dict(),
        "world_response": world_response,
    }
    rec["record_hash"] = fnv1a(canonical({
        "sequence": sequence,
        "tick_hash": tick_hash,
        "observation_id": ctx.observation_id,
        "action": output.proposal.action_type,
        "source": output.source,
    }))
    return rec


def append_trajectory(path: Path | None, rec: dict[str, Any]) -> None:
    if path is None:
        return
    append_jsonl(path, rec)
