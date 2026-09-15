"""Torch decoder for the language arm. Optional. Local. No API.

Import this module only when torch is installed. The numpy runtime stays
the default so the loop does not require torch.

    pip install torch
    python -m agent.language.torch_train

Action pathways (explicit, ablatable):

  contextual (default):
      tokens → embed+pos → Transformer blocks → final LN
        → pool <USER> span on *hidden* → action / confidence / value heads

  pre_attention (ablation):
      tokens → embed+pos → pool <USER> span → action head
      (legacy: skip attention so field/SELF prefix cannot drown the utterance)

LM head remains teacher-forced on composed <PROPOSE><ACTION>body<EOS>.
compose() remains the operator voice — field numbers are not sampled.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import torch
import torch.nn as nn
import torch.nn.functional as F

from agent.language.tokenizer import BYTE_SIZE, SPECIALS
from agent.language.transformer import ACTION_ORDER

TORCH_VERSION = "arm-gpt-v1"
DEFAULT_TORCH_CKPT = Path("/tmp/metafield/arm_gpt_v1.pt")
USER_ID = BYTE_SIZE + SPECIALS.index("<USER>")
ARM_ID = BYTE_SIZE + SPECIALS.index("<ARM>")
PAD_ID = BYTE_SIZE + SPECIALS.index("<PAD>")

ActionPath = Literal["contextual", "pre_attention"]
DEFAULT_ACTION_PATH: ActionPath = "contextual"


def has_torch() -> bool:
    return True


class Block(nn.Module):
    def __init__(self, d_model: int, n_head: int) -> None:
        super().__init__()
        self.ln1 = nn.LayerNorm(d_model)
        self.attn = nn.MultiheadAttention(d_model, n_head, batch_first=True)
        self.ln2 = nn.LayerNorm(d_model)
        self.mlp = nn.Sequential(
            nn.Linear(d_model, 4 * d_model),
            nn.GELU(),
            nn.Linear(4 * d_model, d_model),
        )

    def forward(self, x, attn_mask, key_padding_mask=None):
        h = self.ln1(x)
        a, _ = self.attn(
            h, h, h,
            attn_mask=attn_mask,
            key_padding_mask=key_padding_mask,
            need_weights=False,
        )
        x = x + a
        return x + self.mlp(self.ln2(x))


class ArmGPT(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        *,
        d_model: int = 64,
        n_layer: int = 2,
        n_head: int = 4,
        max_seq: int = 160,
        action_path: ActionPath = DEFAULT_ACTION_PATH,
    ) -> None:
        super().__init__()
        if d_model % n_head != 0:
            raise ValueError("d_model must divide n_head")
        if action_path not in ("contextual", "pre_attention"):
            raise ValueError(f"unknown action_path: {action_path}")
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.n_layer = n_layer
        self.n_head = n_head
        self.max_seq = max_seq
        self.action_path: ActionPath = action_path
        self.version = TORCH_VERSION
        self.tok = nn.Embedding(vocab_size, d_model, padding_idx=PAD_ID)
        self.pos = nn.Embedding(max_seq, d_model)
        self.blocks = nn.ModuleList([Block(d_model, n_head) for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(d_model)
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)
        self.w_act = nn.Linear(d_model, len(ACTION_ORDER))
        self.w_conf = nn.Linear(d_model, 1)
        self.w_val = nn.Linear(d_model, 1)
        nn.init.normal_(self.tok.weight, std=0.02)
        nn.init.normal_(self.pos.weight, std=0.02)
        nn.init.normal_(self.lm_head.weight, std=0.02)
        nn.init.normal_(self.w_act.weight, std=0.02)
        nn.init.zeros_(self.w_act.bias)
        nn.init.normal_(self.w_conf.weight, std=0.02)
        nn.init.zeros_(self.w_conf.bias)
        nn.init.normal_(self.w_val.weight, std=0.02)
        nn.init.zeros_(self.w_val.bias)
        with torch.no_grad():
            self.tok.weight[PAD_ID].zero_()

    def config(self) -> dict:
        return {
            "vocab_size": self.vocab_size,
            "d_model": self.d_model,
            "n_layer": self.n_layer,
            "n_head": self.n_head,
            "max_seq": self.max_seq,
            "action_path": self.action_path,
        }

    def forward(self, ids: torch.Tensor, key_padding_mask: torch.Tensor | None = None):
        ids = ids[:, -self.max_seq :]
        if key_padding_mask is not None:
            key_padding_mask = key_padding_mask[:, -self.max_seq :]
        b, t = ids.shape
        pos = torch.arange(t, device=ids.device).unsqueeze(0).expand(b, t)
        x = self.tok(ids) * math.sqrt(self.d_model) + self.pos(pos)
        causal = torch.triu(
            torch.ones(t, t, device=ids.device, dtype=torch.bool),
            diagonal=1,
        )
        for block in self.blocks:
            x = block(x, attn_mask=causal, key_padding_mask=key_padding_mask)
        hidden = self.ln_f(x)
        return self.lm_head(hidden), hidden

    def embed(self, ids: torch.Tensor) -> torch.Tensor:
        ids = ids[:, -self.max_seq :]
        b, t = ids.shape
        pos = torch.arange(t, device=ids.device).unsqueeze(0).expand(b, t)
        return self.tok(ids) * math.sqrt(self.d_model) + self.pos(pos)

    def pool_user_span(self, hidden: torch.Tensor, ids: torch.Tensor) -> torch.Tensor:
        pooled = []
        for b in range(ids.size(0)):
            seq = ids[b].tolist()
            last_u = None
            last_a = None
            for i, tok in enumerate(seq):
                t = int(tok)
                if t == PAD_ID:
                    continue
                if t == USER_ID:
                    last_u = i
                elif t == ARM_ID:
                    last_a = i
            start = last_u if last_u is not None else 0
            end = last_a if last_a is not None and last_a > start else hidden.size(1)
            if end <= start:
                end = start + 1
            pooled.append(hidden[b, start:end].mean(dim=0))
        return torch.stack(pooled, dim=0)

    def action_representation(
        self,
        ids: torch.Tensor,
        *,
        path: ActionPath | None = None,
        key_padding_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        path = path or self.action_path
        ids = ids[:, -self.max_seq :]
        if path == "pre_attention":
            x = self.embed(ids)
            return self.pool_user_span(x, ids)
        if key_padding_mask is not None:
            key_padding_mask = key_padding_mask[:, -self.max_seq :]
        _, hidden = self.forward(ids, key_padding_mask=key_padding_mask)
        return self.pool_user_span(hidden, ids)

    def action_logits(
        self,
        ids_list: list[int],
        *,
        path: ActionPath | None = None,
    ) -> torch.Tensor:
        ids = torch.tensor([ids_list[-self.max_seq :]], dtype=torch.long)
        pooled = self.action_representation(ids, path=path)
        return self.w_act(pooled)[0]

    def action_heads(
        self,
        ids: torch.Tensor,
        *,
        path: ActionPath | None = None,
        key_padding_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        pooled = self.action_representation(ids, path=path, key_padding_mask=key_padding_mask)
        logits = self.w_act(pooled)
        conf = torch.sigmoid(self.w_conf(pooled).squeeze(-1))
        value = self.w_val(pooled).squeeze(-1)
        return logits, conf, value

    def predict_action_p(
        self,
        ids: list[int],
        *,
        path: ActionPath | None = None,
    ) -> tuple[str, float]:
        self.eval()
        with torch.no_grad():
            logits = self.action_logits(ids, path=path)
            p = F.softmax(logits.float(), dim=-1)
            idx = int(p.argmax().item())
            return ACTION_ORDER[idx], float(p[idx].item())

    def predict_action(self, ids: list[int], *, path: ActionPath | None = None) -> str:
        return self.predict_action_p(ids, path=path)[0]

    def generate(self, ids: list[int], *, max_new: int = 48, eos: int | None = None) -> list[int]:
        self.eval()
        out = list(ids)
        new: list[int] = []
        with torch.no_grad():
            for _ in range(max_new):
                t = torch.tensor([out[-self.max_seq :]], dtype=torch.long)
                logits, _ = self.forward(t)
                nxt = int(logits[0, -1].argmax().item())
                new.append(nxt)
                out.append(nxt)
                if eos is not None and nxt == eos:
                    break
        return new

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {"state": self.state_dict(), "config": self.config(), "version": self.version},
            path,
        )

    @classmethod
    def load(cls, path: Path) -> "ArmGPT":
        blob = torch.load(path, map_location="cpu", weights_only=False)
        cfg = dict(blob["config"])
        action_path = cfg.pop("action_path", "pre_attention")
        model = cls(**cfg, action_path=action_path)
        model.load_state_dict(blob["state"], strict=False)
        model.version = str(blob.get("version") or TORCH_VERSION)
        model.eval()
        return model
