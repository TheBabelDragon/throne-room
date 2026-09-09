"""Millennium Lab — adversarial mathematical environments for the Duck.

The Duck is rewarded for progress, not for being right.
Unbounded prize sentences are rejected once and dropped.
A claimed breakthrough that dies in the proof-killer is never admitted.
"""

from qwuack.millennium.artifacts import Artifact, ArtifactKind, Memory
from qwuack.millennium.killer import ProofKiller, Verdict
from qwuack.millennium.lab import MillenniumLab, PONDS

__all__ = [
    "Artifact",
    "ArtifactKind",
    "Memory",
    "MillenniumLab",
    "PONDS",
    "ProofKiller",
    "Verdict",
]
