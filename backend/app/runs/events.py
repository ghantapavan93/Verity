"""In-process fan-out of run stage events to SSE subscribers. One process, one bus."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from ..models import TERMINAL_STAGES, RunStageName

TERMINAL = frozenset(TERMINAL_STAGES)


@dataclass
class StageEvent:
    run_id: str
    stage: RunStageName
    detail: str | None = None


@dataclass
class EventBus:
    _queues: dict[str, list[asyncio.Queue[StageEvent]]] = field(default_factory=lambda: defaultdict(list))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, run_id: str) -> asyncio.Queue[StageEvent]:
        queue: asyncio.Queue[StageEvent] = asyncio.Queue()
        with self._lock:
            self._queues[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[StageEvent]) -> None:
        with self._lock:
            if queue in self._queues.get(run_id, []):
                self._queues[run_id].remove(queue)
            if not self._queues.get(run_id):
                self._queues.pop(run_id, None)

    def publish(self, event: StageEvent) -> None:
        """Safe to call from a worker thread."""
        with self._lock:
            queues = list(self._queues.get(event.run_id, []))
        loop = self._loop
        for queue in queues:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(queue.put_nowait, event)
            else:
                queue.put_nowait(event)


bus = EventBus()
