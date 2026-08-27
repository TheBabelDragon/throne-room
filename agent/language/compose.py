"""Operator voice. Not the transformer.

The numpy decoder will not speak English. The participant reports the
field it is allowed to see. Action head chooses; this renderer fills
the utterance from LanguageContext. Teacher and model share one voice.
"""

from __future__ import annotations

from agent.language.protocol import LanguageContext
from agent.schemas import ActionProposal


def field_line(ctx: LanguageContext) -> str:
    o = ctx.observation
    peak = o.energy_peak
    body = o.body_id or "-"
    return (
        f"t{o.tick} E={o.energy_sum:.2f} (peak {peak[0]},{peak[1]}={peak[2]:.2f}) "
        f"I={o.info_sum:.2f} CSI={o.csi_energy:.2f}@{o.csi_rssi:.1f}dBm "
        f"body={body} att={ctx.attention} integrity={o.integrity}"
    )


def _memory_line(ctx: LanguageContext) -> str:
    for mem in reversed(ctx.memories):
        text = (mem.text or "").strip()
        if text and not text.startswith("human:"):
            return text[:80]
    return "none"


def compose(
    action: str,
    ctx: LanguageContext,
    proposal: ActionProposal | None = None,
    *,
    abstained: bool = False,
    confidence: float = 1.0,
) -> str:
    """Grounded utterance for the operator. Always from the field, never genesis tokens."""
    line = field_line(ctx)
    if abstained:
        return (
            f"WAIT. action-head p={confidence:.2f} is below commit threshold — "
            f"holding instead of a bad {action}. {line}"
        )
    params = (proposal.parameters if proposal is not None else None) or {}
    if action == "SPEAK":
        goals = "; ".join(ctx.goals[-2:]) if ctx.goals else "none"
        return (
            f"SELF — agency without authority. {line}. "
            f"goals={goals}. memory={_memory_line(ctx)}. "
            f"I report; I do not mutate FieldTick."
        )
    if action == "QUERY_FIELD":
        return f"QUERY. {line}"
    if action == "PROBE":
        x = params.get("x", ctx.observation.energy_peak[0])
        z = params.get("z", ctx.observation.energy_peak[1])
        mag = params.get("magnitude", 0.55)
        return f"PROBE @ {x},{z} mag={mag}. Energy will rise. {line}"
    if action == "REMEMBER":
        note = str(params.get("note") or ctx.user_text)[:80]
        return f"REMEMBER. stored: {note}"
    if action == "ATTEND":
        target = str(params.get("target") or ctx.attention or "field")
        return f"ATTEND {target}. {line}"
    if action == "SET_GOAL":
        goal = str(params.get("text") or ctx.user_text)[:80]
        return f"SET_GOAL. {goal}"
    if action == "WAIT":
        return f"WAIT. holding. {line}"
    return f"{action}. {line}"
