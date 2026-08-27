"""Owned tokenizer boundary.

Bytes 0–255 stay identity. Specials occupy 256+. Vocabulary version is
persisted; the model does not get to invent tokens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agent.language.protocol import LanguageContext
from agent.schemas import ActionProposal

TOKENIZER_VERSION = "arm-tok-v1"
BYTE_SIZE = 256

SPECIALS: tuple[str, ...] = (
    "<PAD>",
    "<BOS>",
    "<EOS>",
    "<UNK>",
    "<SEP>",
    "<OBSERVE>",
    "<ATTEND>",
    "<QUERY>",
    "<REMEMBER>",
    "<PROPOSE>",
    "<SPEAK>",
    "<WAIT>",
    "<FIELD>",
    "<USER>",
    "<ARM>",
    "<SELF>",
    "<MEM>",
    "<GOAL>",
    "<CAP>",
    "<PROBE>",
    "<SET_GOAL>",
)

ACTION_TAGS: dict[str, str] = {
    "SPEAK": "<SPEAK>",
    "PROBE": "<PROBE>",
    "REMEMBER": "<REMEMBER>",
    "ATTEND": "<ATTEND>",
    "SET_GOAL": "<SET_GOAL>",
    "QUERY_FIELD": "<QUERY>",
    "WAIT": "<WAIT>",
}


class ArmTokenizer:
    def __init__(self, specials: tuple[str, ...] = SPECIALS, version: str = TOKENIZER_VERSION) -> None:
        self.version = version
        self.specials = list(specials)
        self._stoi = {s: BYTE_SIZE + i for i, s in enumerate(self.specials)}
        self._itos = {i: s for s, i in self._stoi.items()}

    @property
    def vocab_size(self) -> int:
        return BYTE_SIZE + len(self.specials)

    def special_id(self, name: str) -> int:
        return self._stoi[name]

    def encode_bytes(self, text: str) -> list[int]:
        return list(text.encode("utf-8", errors="replace"))

    def encode(self, text: str) -> list[int]:
        ids: list[int] = []
        i = 0
        while i < len(text):
            hit = None
            for s in self.specials:
                if text.startswith(s, i):
                    hit = s
                    break
            if hit is not None:
                ids.append(self._stoi[hit])
                i += len(hit)
            else:
                ids.extend(self.encode_bytes(text[i]))
                i += 1
        return ids

    def decode(self, ids: Iterable[int]) -> str:
        out: list[str] = []
        buf = bytearray()

        def flush() -> None:
            nonlocal buf
            if buf:
                out.append(buf.decode("utf-8", errors="replace"))
                buf = bytearray()

        for i in ids:
            if i < BYTE_SIZE:
                buf.append(i)
            else:
                flush()
                out.append(self._itos.get(int(i), "<UNK>"))
        flush()
        return "".join(out)

    def encode_context(self, ctx: LanguageContext, max_len: int = 192) -> list[int]:
        obs = ctx.observation
        peak = obs.energy_peak
        parts = [
            "<BOS>",
            "<FIELD>",
            f" t={obs.tick} E={obs.energy_sum:.2f} I={obs.info_sum:.2f} "
            f"peak={peak[0]},{peak[1]}={peak[2]:.2f} csi={obs.csi_energy:.2f} "
            f"rssi={obs.csi_rssi:.1f} body={obs.body_id or '-'}",
            "<SELF>",
            f" att={ctx.attention} int={obs.integrity} goals={'|'.join(ctx.goals) or 'none'}",
            "<CAP>",
            " " + ",".join(ctx.capabilities),
        ]
        for mem in ctx.memories[-4:]:
            parts.extend(["<MEM>", f" {mem.text[:80]}"])
        for ev in ctx.conversation[-4:]:
            tag = "<USER>" if ev.role == "user" else ("<ARM>" if ev.role == "arm" else "<SEP>")
            parts.extend([tag, f" {ev.text[:120]}"])
        parts.extend(["<USER>", f" {ctx.user_text[:240]}", "<ARM>"])
        ids = self.encode("".join(parts))
        bos = self.special_id("<BOS>")
        if ids[:1] != [bos]:
            ids = [bos] + ids
        return ids[-max_len:]

    def user_span(self, ids: list[int]) -> list[int]:
        """Tokens of the current utterance: last <USER> … <ARM>.

        Action labels live here. Field/SELF prefixes are the same across
        turns and must not dominate the action-head features.
        """
        uid = self._stoi.get("<USER>")
        aid = self._stoi.get("<ARM>")
        last_user = None
        last_arm = None
        for i, tok in enumerate(ids):
            if tok == uid:
                last_user = i
            elif tok == aid:
                last_arm = i
        if last_user is None:
            return ids[-32:] if ids else [0]
        end = last_arm if (last_arm is not None and last_arm > last_user) else len(ids)
        span = ids[last_user:end]
        return span if span else ids[-32:]

    def encode_target(self, proposal: ActionProposal, *, max_body: int = 120) -> list[int]:
        """Teacher-forced arm utterance: <PROPOSE><ACTION>body<EOS>."""
        act = proposal.action_type
        tag = ACTION_TAGS.get(act, "<SPEAK>")
        if tag not in self._stoi:
            tag = "<SPEAK>"
        params = proposal.parameters or {}
        if act == "SPEAK":
            body = str(params.get("text") or "")[:max_body]
        elif act == "PROBE":
            body = f"{params.get('x', 0)},{params.get('z', 0)},{params.get('magnitude', 0.5)}"
        elif act == "REMEMBER":
            body = str(params.get("note") or "")[:max_body]
        elif act == "ATTEND":
            body = str(params.get("target") or "field")
        elif act == "SET_GOAL":
            body = str(params.get("text") or "")[:max_body]
        elif act == "QUERY_FIELD":
            body = str(params.get("text") or "field")[:max_body]
        else:
            body = str(params.get("text") or "")[:max_body]
        return self.encode(f"<PROPOSE>{tag}{body}<EOS>")

    def action_from_ids(self, ids: list[int]) -> str | None:
        tags = {v: k for k, v in ACTION_TAGS.items() if v in self._stoi}
        special_ids = {self._stoi[k]: v for k, v in tags.items()}
        for i in ids:
            if int(i) in special_ids:
                return special_ids[int(i)]
        return None

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "byte_size": BYTE_SIZE,
            "specials": self.specials,
            "vocab_size": self.vocab_size,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ArmTokenizer":
        obj = json.loads(path.read_text(encoding="utf-8"))
        return cls(specials=tuple(obj["specials"]), version=str(obj["version"]))
