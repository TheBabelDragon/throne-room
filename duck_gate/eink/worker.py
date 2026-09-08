"""Background consumer. Duck Gate must not block on an e-paper refresh."""

from __future__ import annotations

import threading
from queue import Empty, Queue

from duck_gate.bus import GateBus
from duck_gate.eink.sink import EInkSink
from duck_gate.events import GateEvent


class EInkWorker:
    def __init__(self, sink: EInkSink, bus: GateBus | None = None) -> None:
        self.sink = sink
        self.bus = bus
        self._queue: Queue[GateEvent] = Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.coalesced = 0

    def attach(self, bus: GateBus) -> None:
        self.bus = bus
        bus.subscribe(self.submit)

    def submit(self, event: GateEvent) -> None:
        self._queue.put(event)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="eink-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def drain(self) -> int:
        """Apply queued events, keeping only the newest sequence. For tests."""
        latest: GateEvent | None = None
        skipped = 0
        while True:
            try:
                event = self._queue.get_nowait()
            except Empty:
                break
            if latest is not None:
                skipped += 1
            latest = event
        self.coalesced += skipped
        if latest is None:
            return 0
        self.sink.accept(latest)
        return 1

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                first = self._queue.get(timeout=0.05)
            except Empty:
                continue
            latest = first
            skipped = 0
            while True:
                try:
                    latest = self._queue.get_nowait()
                    skipped += 1
                except Empty:
                    break
            self.coalesced += skipped
            self.sink.accept(latest)
