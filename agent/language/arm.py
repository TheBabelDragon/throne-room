"""LanguageArm: local Aurora participant.

Joins the loop as a cognition arm. Generates tokens locally. Proposals
go through the operator ABI. Teacher policy is the action head until a
trained checkpoint exists — still local, still not an API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent.language.protocol import LanguageContext, LanguageOutput
from agent.language.tokenizer import ArmTokenizer
from agent.language.transformer import MODEL_VERSION, DecoderTransformer
from agent.operator_abi import make_proposal
from agent.reason import ReasoningContext, mock_reason
from agent.schemas import ACTION_TYPES, ActionProposal

ArmMode = Literal["teacher", "model"]


def _teacher(ctx: LanguageContext) -> ActionProposal:
    peak = ctx.observation.energy_peak
    rc = ReasoningContext(
        observation_id=ctx.observation_id,
        user_text=ctx.user_text,
        tick=ctx.observation.tick,
        energy_sum=ctx.observation.energy_sum,
        info_sum=ctx.observation.info_sum,
        temp_sum=ctx.observation.temp_sum,
        energy_peak=peak,
        csi_energy=ctx.observation.csi_energy,
        csi_rssi=ctx.observation.csi_rssi,
        integrity=ctx.observation.integrity,
        goals=list(ctx.goals),
        attention=ctx.attention,
        memories=[m.text for m in ctx.memories],
    )
    return mock_reason(rc)


def _parse_structured(text: str, tok: ArmTokenizer, ctx: LanguageContext) -> ActionProposal | None:
    upper = text
    action = None
    for name in ACTION_TYPES:
        tag = f"<{name}>" if f"<{name}>" in tok.specials else None
        if tag and tag in upper:
            action = name
            break
        if name in upper:
            action = name
            break
    if action is None:
        if "<SPEAK>" in upper:
            action = "SPEAK"
        elif "<PROPOSE>" in upper:
            action = "SPEAK"
    if action is None:
        return None
    body = text
    for mark in ("<SPEAK>", "<PROPOSE>", "<ARM>", "<EOS>"):
        if mark in body:
            body = body.split(mark)[-1]
    body = body.replace("<EOS>", "").strip()
    if action == "SPEAK" and not body:
        return None
    params: dict = {"text": body[:400]} if action == "SPEAK" else {}
    if action == "PROBE":
        peak = ctx.observation.energy_peak
        params = {"x": peak[0], "z": peak[1], "magnitude": 0.55}
    if action == "ATTEND":
        params = {"target": ctx.attention or "field"}
    if action == "REMEMBER":
        params = {"note": body[:400] or ctx.user_text}
    return make_proposal(
        action_type=action,
        parameters=params,
        target="chat" if action == "SPEAK" else "field",
        rationale="Language arm structured decode.",
        confidence=0.55,
        originating_observation=ctx.observation_id,
    )


class LanguageArm:
    def __init__(
        self,
        *,
        mode: ArmMode = "teacher",
        tokenizer: ArmTokenizer | None = None,
        model: DecoderTransformer | None = None,
        max_new: int = 32,
        trajectory_path: Path | None = None,
    ) -> None:
        self.mode: ArmMode = mode
        if tokenizer is None:
            bundled = Path(__file__).parent / "tokenizer.json"
            tokenizer = ArmTokenizer.load(bundled) if bundled.exists() else ArmTokenizer()
        self.tokenizer = tokenizer
        self.model = model or DecoderTransformer(self.tokenizer.vocab_size)
        self.max_new = max_new
        self.trajectory_path = trajectory_path
        self.last: LanguageOutput | None = None
        self.steps = 0

    def act(self, ctx: LanguageContext) -> LanguageOutput:
        prompt = self.tokenizer.encode_context(ctx)
        gen = self.model.generate(
            prompt,
            max_new=self.max_new,
            eos=self.tokenizer.special_id("<EOS>"),
        )
        raw = self.tokenizer.decode(gen)
        parsed = _parse_structured(raw, self.tokenizer, ctx)
        source: ArmMode
        if self.mode == "model" and parsed is not None:
            proposal = parsed
            source = "model"
        else:
            proposal = _teacher(ctx)
            source = "teacher"
        out = LanguageOutput(
            tokens=gen,
            text=raw if source == "model" else str(proposal.parameters.get("text") or raw),
            proposal=proposal,
            source=source,
            tokenizer_version=self.tokenizer.version,
            model_version=MODEL_VERSION,
            prompt_tokens=prompt,
        )
        if source == "teacher" and proposal.action_type == "SPEAK":
            out.text = str(proposal.parameters.get("text") or out.text)
        self.last = out
        self.steps += 1
        return out
