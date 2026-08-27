"""LanguageArm: local Aurora participant.

Joins the loop as a cognition arm. The action head chooses. compose()
is the voice — the numpy decoder does not speak English. Proposals go
through the operator ABI. Teacher policy labels online `--learn`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent.language.compose import compose
from agent.language.protocol import LanguageContext, LanguageOutput
from agent.language.tokenizer import ACTION_TAGS, ArmTokenizer
from agent.language.transformer import ACTION_ORDER, MODEL_VERSION, DecoderTransformer
from agent.operator_abi import make_proposal
from agent.reason import ReasoningContext, mock_reason
from agent.schemas import ActionProposal

ArmMode = Literal["teacher", "model"]
MIN_P = 0.22


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
        return make_proposal(
            action_type="SPEAK",
            parameters={"text": "report"},
            target="chat",
            rationale="Action head selected SPEAK.",
            confidence=0.7,
            originating_observation=ctx.observation_id,
        )
    return teacher


def _stamp_voice(
    proposal: ActionProposal,
    ctx: LanguageContext,
    *,
    abstained: bool,
    confidence: float,
) -> str:
    text = compose(
        proposal.action_type,
        ctx,
        proposal,
        abstained=abstained,
        confidence=confidence,
    )
    if proposal.action_type == "SPEAK":
        proposal.parameters["text"] = text
    else:
        proposal.parameters["utterance"] = text
        if proposal.action_type == "QUERY_FIELD":
            proposal.parameters["text"] = text
    proposal.confidence = float(confidence)
    return text


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
        max_new: int = 0,
        trajectory_path: Path | None = None,
        checkpoint: Path | None = None,
        learn: bool = False,
        min_p: float = MIN_P,
        learn_lr: float = 1.0,
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
        self.learn = learn
        self.min_p = min_p
        self.learn_lr = learn_lr
        self.last: LanguageOutput | None = None
        self.steps = 0
        self.learn_steps = 0

    def act(self, ctx: LanguageContext) -> LanguageOutput:
        prompt = self.tokenizer.encode_context(ctx)
        teacher = _teacher(ctx)
        predicted = teacher.action_type
        confidence = 1.0
        abstained = False
        source: ArmMode = "teacher"
        if self.mode == "model":
            predicted, confidence = self.model.predict_action_p(prompt)
            if predicted not in ACTION_ORDER:
                predicted = teacher.action_type
            if confidence < self.min_p:
                abstained = True
                predicted = "WAIT"
            source = "model"
        proposal = teacher if source == "teacher" else _ground(predicted, ctx, teacher)
        text = _stamp_voice(proposal, ctx, abstained=abstained, confidence=confidence)
        tokens = self.tokenizer.encode_target(proposal)
        if self.max_new > 0:
            seed = list(prompt) + self.tokenizer.encode("<PROPOSE>" + _tag_for(proposal.action_type))
            genesis = self.model.generate(
                seed,
                max_new=self.max_new,
                eos=self.tokenizer.special_id("<EOS>"),
            )
            tokens = tokens + genesis
        if self.learn:
            gold = teacher.action_type
            if gold in ACTION_ORDER:
                from agent.language.train import learn_one
                learn_one(
                    self.model,
                    prompt,
                    ACTION_ORDER.index(gold),
                    lr=self.learn_lr,
                )
                self.learn_steps += 1
        out = LanguageOutput(
            tokens=tokens,
            text=text,
            proposal=proposal,
            source=source,
            tokenizer_version=self.tokenizer.version,
            model_version=MODEL_VERSION,
            prompt_tokens=prompt,
            confidence=confidence,
            predicted_action=predicted,
            abstained=abstained,
        )
        self.last = out
        self.steps += 1
        return out
