"""Non-blocking GateEvent bus. Publishers never wait on e-ink refresh."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Callable

from duck_gate.events import GateEvent

Listener = Callable[[GateEvent], None]


class GateBus:
    def __init__(self, maxlen: int = 64) -> None:
        self._lock = Lock()
        self._listeners: list[Listener] = []
        self._journal: deque[GateEvent] = deque(maxlen=maxlen)
        self.last: GateEvent | None = None

    def subscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners = [fn for fn in self._listeners if fn is not listener]

    def publish(self, event: GateEvent) -> None:
        """Commit first, then publish. Listeners must not raise into the gate."""
        with self._lock:
            self.last = event
            self._journal.append(event)
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(event)
            except Exception:
                continue

    def recent(self) -> list[GateEvent]:
        with self._lock:
            return list(self._journal)


BUS = GateBus()
