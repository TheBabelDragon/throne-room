"""
Redis control plane + ESCAPE for Aurora action layer.

Fail-closed:
  - No Redis  →  action layer may observe files but must not dispatch.
  - ESCAPE key set  →  all action frozen until cleared.
  - Heartbeat TTL expiry  →  treated as unsupervised; freeze.

Keys / channels
---------------
aurora:control:escape          STRING  "1" = freeze (kill switch)
aurora:control:mode            STRING  observe|cautious|auto
aurora:control:heartbeat       STRING  ISO ts, refreshed with TTL
aurora:action:out              PUBSUB  emitted actions
aurora:swarm:commands          PUBSUB  compatible with wifi-sensing listener
aurora:action:state            STRING  JSON snapshot of last decision
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import redis  # type: ignore
except ImportError:
    redis = None  # type: ignore


ESCAPE_KEY = "aurora:control:escape"
MODE_KEY = "aurora:control:mode"
HEARTBEAT_KEY = "aurora:control:heartbeat"
STATE_KEY = "aurora:action:state"
OUT_CHANNEL = "aurora:action:out"
SWARM_COMMANDS = "aurora:swarm:commands"

HEARTBEAT_TTL_S = 15


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ControlSnapshot:
    connected: bool
    escape: bool
    mode: str
    heartbeat_age_s: float | None
    allowed: bool  # True only if actions may fire


class RedisControl:
    """Thin, fail-closed Redis facade."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._r = None
        self._connect()

    def _connect(self) -> None:
        if redis is None:
            self._r = None
            return
        try:
            client = redis.from_url(
                self.url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            client.ping()
            self._r = client
        except Exception:
            self._r = None

    @property
    def connected(self) -> bool:
        if self._r is None:
            return False
        try:
            self._r.ping()
            return True
        except Exception:
            self._r = None
            return False

    def ensure(self) -> bool:
        if not self.connected:
            self._connect()
        return self.connected

    def snapshot(self) -> ControlSnapshot:
        if not self.ensure():
            return ControlSnapshot(
                connected=False,
                escape=True,  # fail-closed: treat as escaped
                mode="observe",
                heartbeat_age_s=None,
                allowed=False,
            )
        assert self._r is not None
        try:
            esc = self._r.get(ESCAPE_KEY)
            escape = str(esc or "0") in {"1", "true", "TRUE", "on", "ON"}
            mode = str(self._r.get(MODE_KEY) or "cautious")
            if mode not in {"observe", "cautious", "auto"}:
                mode = "cautious"
            hb = self._r.get(HEARTBEAT_KEY)
            age: float | None = None
            if hb:
                try:
                    # store unix float alongside iso for simple age
                    raw = self._r.get(HEARTBEAT_KEY + ":unix")
                    if raw is not None:
                        age = time.time() - float(raw)
                except Exception:
                    age = None
            # heartbeat missing or very old → freeze in auto
            hb_ok = age is not None and age < HEARTBEAT_TTL_S * 2
            allowed = (not escape) and mode in {"cautious", "auto"} and (
                mode == "cautious" or hb_ok or age is None
            )
            # first boot: age None is ok once we pulse
            if mode == "observe":
                allowed = False
            if escape:
                allowed = False
            return ControlSnapshot(
                connected=True,
                escape=escape,
                mode=mode,
                heartbeat_age_s=age,
                allowed=allowed,
            )
        except Exception:
            return ControlSnapshot(
                connected=False,
                escape=True,
                mode="observe",
                heartbeat_age_s=None,
                allowed=False,
            )

    def pulse_heartbeat(self) -> None:
        if not self.ensure() or self._r is None:
            return
        try:
            pipe = self._r.pipeline()
            pipe.set(HEARTBEAT_KEY, _now(), ex=HEARTBEAT_TTL_S)
            pipe.set(HEARTBEAT_KEY + ":unix", str(time.time()), ex=HEARTBEAT_TTL_S)
            pipe.execute()
        except Exception:
            self._r = None

    def set_escape(self, on: bool = True) -> bool:
        """Arm or clear the kill switch."""
        if not self.ensure() or self._r is None:
            return False
        try:
            if on:
                self._r.set(ESCAPE_KEY, "1")
            else:
                self._r.delete(ESCAPE_KEY)
            return True
        except Exception:
            self._r = None
            return False

    def set_mode(self, mode: str) -> bool:
        if mode not in {"observe", "cautious", "auto"}:
            return False
        if not self.ensure() or self._r is None:
            return False
        try:
            self._r.set(MODE_KEY, mode)
            return True
        except Exception:
            self._r = None
            return False

    def publish_action(self, action: dict[str, Any]) -> bool:
        """Dispatch only after caller checked snapshot.allowed."""
        if not self.ensure() or self._r is None:
            return False
        # re-check escape at the last moment
        snap = self.snapshot()
        if not snap.allowed:
            return False
        payload = json.dumps(action, separators=(",", ":"))
        try:
            self._r.publish(OUT_CHANNEL, payload)
            self._r.publish(SWARM_COMMANDS, payload)
            self._r.set(STATE_KEY, payload)
            return True
        except Exception:
            self._r = None
            return False

    def write_state(self, state: dict[str, Any]) -> None:
        if not self.ensure() or self._r is None:
            return
        try:
            self._r.set(STATE_KEY, json.dumps(state, separators=(",", ":")))
        except Exception:
            self._r = None
