"""LanguageArm: local Aurora participant.

Joins the loop as a cognition arm. Generates tokens locally. Proposals
go through the operator ABI. Teacher policy is the action head until a
trained checkpoint exists — still local, still not an API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent.language.protocol import LanguageContext, LanguageOutput
from agent.language.tokenizer import ACTION_TAGS, ArmTokenizer
from agent.language.transformer import ACTION_ORDER, MODEL_VERSION, DecoderTransformer
from agent.operator_abi import make_proposal
from agent.reason import ReasoningContext, mock_reason
from agent.schemas import ActionProposal

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


def _parse_structured(text: str, tok: ArmTokenizer, ctx: LanguageContext, ids: list[int] | None = None) -> ActionProposal | None:
    action = tok.action_from_ids(ids or []) if ids else None
    if action is None:
        upper = text
        for name, tag in ACTION_TAGS.items():
            if tag in upper:
                action = name
                break
    if action is None:
        if "<PROPOSE>" in text:
            action = "SPEAK"
    if action is None:
        return None
    body = text
    for mark in (*ACTION_TAGS.values(), "<PROPOSE>", "<ARM>", "<EOS>"):
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
    if action == "SET_GOAL":
        params = {"text": body[:400] or ctx.user_text}
    if action == "QUERY_FIELD":
        params = {"text": body[:400] or ctx.user_text}
    return make_proposal(
        action_type=action,
        parameters=params,
        target="chat" if action == "SPEAK" else "field",
        rationale="Language arm structured decode.",
        confidence=0.55,
        originating_observation=ctx.observation_id,
    )


DEFAULT_CKPT = Path("/tmp/metafield/arm_dec_v0.npz")


def _tag_for(action: str) -> str:
    return ACTION_TAGS.get(action, "<SPEAK>")


def _ground(action: str, ctx: LanguageContext, teacher: ActionProposal) -> ActionProposal:
    if action == teacher.action_type:
        return teacher
    peak = ctx.observation.energy_peak
    if action == "PROBE":
        return make_proposal(
            action_type="PROBE",
            parameters={"x": peak[0], "z": peak[1], "magnitude": 0.55},
            target=f"{peak[0]},{peak[1]}",
            rationale="Action head selected PROBE.",
            confidence=0.7,
            originating_observation=ctx.observation_id,
        )
    if action == "ATTEND":
        target = "csi" if "csi" in ctx.user_text.lower() else "field"
        return make_proposal(
            action_type="ATTEND",
            parameters={"target": target},
            target=target,
            rationale="Action head selected ATTEND.",
            confidence=0.7,
            originating_observation=ctx.observation_id,
        )
    if action == "REMEMBER":
        return make_proposal(
            action_type="REMEMBER",
            parameters={"note": f"Tick {ctx.observation.tick}: {ctx.user_text}"},
            target="memory",
            rationale="Action head selected REMEMBER.",
            confidence=0.7,
            originating_observation=ctx.observation_id,
        )
    if action == "WAIT":
        return make_proposal(
            action_type="WAIT",
            parameters={"text": "hold"},
            target="field",
            rationale="Action head selected WAIT.",
            confidence=0.7,
            originating_observation=ctx.observation_id,
        )
    if action == "SET_GOAL":
        return make_proposal(
            action_type="SET_GOAL",
            parameters={"text": ctx.user_text},
            target="goals",
            rationale="Action head selected SET_GOAL.",
            confidence=0.65,
            originating_observation=ctx.observation_id,
        )
    if action == "QUERY_FIELD":
        return make_proposal(
            action_type="QUERY_FIELD",
            parameters={"text": ctx.user_text},
            target="field",
            rationale="Action head selected QUERY_FIELD.",
            confidence=0.7,
            originating_observation=ctx.observation_id,
        )
    if action == "SPEAK":
        return teacher
    return teacher


def _find_checkpoint(explicit: Path | None = None) -> Path | None:
    import os
    candidates = [
        explicit,
        Path(os.environ["ARM_CHECKPOINT"]) if os.environ.get("ARM_CHECKPOINT") else None,
        DEFAULT_CKPT,
        Path(__file__).parent / "checkpoints" / "arm_dec_v0.npz",
    ]
    for p in candidates:
        if p is not None and p.exists():
            return p
    return None


class LanguageArm:
    def __init__(
        self,
        *,
        mode: ArmMode = "teacher",
        tokenizer: ArmTokenizer | None = None,
        model: DecoderTransformer | None = None,
        max_new: int = 32,
        trajectory_path: Path | None = None,
        checkpoint: Path | None = None,
    ) -> None:
        self.mode: ArmMode = mode
        if tokenizer is None:
            bundled = Path(__file__).parent / "tokenizer.json"
            tokenizer = ArmTokenizer.load(bundled) if bundled.exists() else ArmTokenizer()
        self.tokenizer = tokenizer
        ckpt = _find_checkpoint(checkpoint)
        if model is not None:
            self.model = model
        elif ckpt is not None:
            self.model = DecoderTransformer.load(ckpt)
            self.checkpoint = ckpt
        else:
            self.model = DecoderTransformer(self.tokenizer.vocab_size)
            self.checkpoint = None
        if ckpt is not None and model is None:
            self.checkpoint = ckpt
        elif model is not None:
            self.checkpoint = None
        self.max_new = max_new
        self.trajectory_path = trajectory_path
        self.last: LanguageOutput | None = None
        self.steps = 0

    def act(self, ctx: LanguageContext) -> LanguageOutput:
        prompt = self.tokenizer.encode_context(ctx)
        teacher = _teacher(ctx)
        if self.max_new > 0:
            seed = list(prompt)
            if self.mode == "model":
                predicted = self.model.predict_action(prompt)
                seed = seed + self.tokenizer.encode("<PROPOSE>" + _tag_for(predicted))
            gen = self.model.generate(
                seed,
                max_new=self.max_new,
                eos=self.tokenizer.special_id("<EOS>"),
            )
        else:
            gen = []
        raw = self.tokenizer.decode(gen)
        parsed = _parse_structured(raw, self.tokenizer, ctx, gen)
        if self.mode == "model":
            predicted = self.model.predict_action(prompt)
            if predicted not in ACTION_ORDER:
                predicted = teacher.action_type
            proposal = parsed if (parsed and parsed.action_type == predicted) else _ground(predicted, ctx, teacher)
            source: ArmMode = "model"
        else:
            proposal = teacher
            source = "teacher"
        out = LanguageOutput(
            tokens=gen,
            text=raw if source == "model" and parsed else str(proposal.parameters.get("text") or raw),
            proposal=proposal,
            source=source,
            tokenizer_version=self.tokenizer.version,
            model_version=MODEL_VERSION,
            prompt_tokens=prompt,
        )
        if proposal.action_type == "SPEAK":
            out.text = str(proposal.parameters.get("text") or out.text)
        self.last = out
        self.steps += 1
        return out
