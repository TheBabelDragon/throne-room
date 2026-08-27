"""Owned tokenizer boundary.

Bytes 0–255 stay identity. Specials occupy 256+. Vocabulary version is
persisted; the model does not get to invent tokens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agent.language.protocol import LanguageContext

TOKENIZER_VERSION = "arm-tok-v0"
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
)


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
