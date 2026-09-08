"""ASCII framebuffer layouts. Hardware SPI/I2C drivers consume the same snapshot."""

from __future__ import annotations

from duck_gate.eink.snapshot import GateDisplaySnapshot


def _hash_pairs(state_hash: str) -> str:
    text = (state_hash or "00000000").upper()
    if len(text) >= 8:
        return f"{text[:4]} {text[4:8]}"
    return text


def render_frame(snap: GateDisplaySnapshot) -> str:
    if snap.status == "ADMITTED":
        return (
            "┌────────────────────────────────┐\n"
            "│                                │\n"
            "│          🦆 DUCK GATE          │\n"
            "│                                │\n"
            f"│          {snap.status:<8}              │\n"
            "│                                │\n"
            "│  ────────────────────────────  │\n"
            "│                                │\n"
            f"│  TICK       {snap.sequence:07d}            │\n"
            f"│  DELTAS          {snap.delta_count:+03d}           │\n"
            f"│  STATE     {_hash_pairs(snap.state_hash):<9}           │\n"
            "│                                │\n"
            f"│  PROTOCOL  {snap.protocol:<8}            │\n"
            "│                                │\n"
            "│  ● COMMITTED                   │\n"
            "│                                │\n"
            "└────────────────────────────────┘\n"
        )
    last_ok = snap.last_ok_sequence if snap.last_ok_sequence is not None else snap.sequence
    reason = (snap.reason or snap.status or "HALTED")[:28]
    return (
        "┌────────────────────────────────┐\n"
        "│          🦆 DUCK GATE          │\n"
        "│                                │\n"
        "│          HALTED                │\n"
        "│                                │\n"
        f"│  TICK       {snap.sequence:07d}            │\n"
        f"│  LAST OK    {last_ok:07d}            │\n"
        "│                                │\n"
        "│  REASON                         │\n"
        f"│  {reason:<28}  │\n"
        "│                                │\n"
        f"│  STATE     {_hash_pairs(snap.state_hash):<9}           │\n"
        "└────────────────────────────────┘\n"
    )
