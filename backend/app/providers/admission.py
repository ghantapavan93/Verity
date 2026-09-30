"""Admission to the one model: how many calls may be in flight, who is waiting, and for how long.

Every measurement so far says the model is the bottleneck and nothing else is (docs/SCALE.md: median model latency
20 s alone, 235 s at twenty concurrent runs; the API queue under 2 s). The GPU serialises the calls anyway; what an
unbounded API adds is twenty requests contending for it with no record of the contention. This controller bounds
the calls in flight, keeps two queues, interactive (a person waiting at a screen) and batch (a corpus job), serves
them by weighted round robin so a batch cannot starve a person and a person cannot starve a batch forever, and
records for every call how long it waited and how long the model took. It is a semaphore and two deques, not a
scheduler product; the numbers it records are what would justify anything more.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from .base import Generation, ModelProvider

Workload = Literal["interactive", "batch"]
INTERACTIVE_TURNS = 4  # four interactive admissions for every batch admission while both queues wait


@dataclass
class Admission:
    workload: Workload
    queue_wait_ms: float
    service_ms: float
    queue_depth_at_arrival: int


Policy = Literal["weighted", "fifo"]  # fifo exists for the measurement that justifies weighted, and for nothing else


@dataclass
class AdmissionController:
    limit: int = 1
    policy: Policy = "weighted"
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _in_flight: int = 0
    _waiting: dict[Workload, deque[threading.Event]] = field(default_factory=lambda: {"interactive": deque(), "batch": deque()})
    _arrivals: deque[threading.Event] = field(default_factory=deque)
    _served_interactive_in_a_row: int = 0
    _recent: deque[Admission] = field(default_factory=lambda: deque(maxlen=1000))

    def _take(self, workload: Workload) -> threading.Event:
        ticket = self._waiting[workload].popleft()
        self._arrivals.remove(ticket)
        return ticket

    def _next_waiter(self) -> threading.Event | None:
        interactive, batch = self._waiting["interactive"], self._waiting["batch"]
        if self.policy == "fifo":
            if not self._arrivals:
                return None
            ticket = self._arrivals[0]
            return self._take("interactive" if ticket in interactive else "batch")
        if interactive and (not batch or self._served_interactive_in_a_row < INTERACTIVE_TURNS):
            self._served_interactive_in_a_row += 1
            return self._take("interactive")
        if batch:
            self._served_interactive_in_a_row = 0
            return self._take("batch")
        if interactive:
            self._served_interactive_in_a_row += 1
            return self._take("interactive")
        return None

    def acquire(self, workload: Workload) -> tuple[float, int]:
        """Block until admitted; return the wait in milliseconds and the queue depth seen on arrival."""
        arrived = time.perf_counter()
        with self._lock:
            depth = len(self._waiting["interactive"]) + len(self._waiting["batch"])
            if self._in_flight < self.limit and not depth:
                self._in_flight += 1
                return 0.0, 0
            ticket = threading.Event()
            self._waiting[workload].append(ticket)
            self._arrivals.append(ticket)
        ticket.wait()
        return (time.perf_counter() - arrived) * 1000, depth

    def release(self, admission: Admission) -> None:
        with self._lock:
            self._recent.append(admission)
            waiter = self._next_waiter()
            if waiter is None:
                self._in_flight -= 1
            else:
                waiter.set()  # the slot passes straight to the next in line; in_flight stays

    @property
    def depth(self) -> int:
        with self._lock:
            return len(self._waiting["interactive"]) + len(self._waiting["batch"])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            recent = list(self._recent)
        by_workload: dict[str, dict[str, float]] = {}
        for workload in ("interactive", "batch"):
            rows = [a for a in recent if a.workload == workload]
            if rows:
                waits = sorted(a.queue_wait_ms for a in rows)
                by_workload[workload] = {"calls": len(rows), "queue_wait_ms_p50": waits[len(waits) // 2], "queue_wait_ms_max": waits[-1]}
        return {"limit": self.limit, "policy": self.policy, "in_flight": self._in_flight, "waiting": self.depth, "recent": by_workload}


class AdmittedProvider:
    """A provider whose calls go through the controller. The workload is fixed per instance: the API hands out an
    interactive one, a batch runner a batch one, both over the same underlying provider and controller."""

    def __init__(self, inner: ModelProvider, controller: AdmissionController, workload: Workload) -> None:
        self.inner = inner
        self.controller = controller
        self.workload: Workload = workload
        self.name = inner.name
        self.model = inner.model
        self.last: Admission | None = None

    def healthy(self) -> tuple[bool, str]:
        ok, detail = self.inner.healthy()
        return ok, f"{detail} · admission limit {self.controller.limit}, {self.controller.depth} waiting"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        waited_ms, depth = self.controller.acquire(self.workload)
        started = time.perf_counter()
        try:
            return self.inner.generate_json(system, user, schema)
        finally:
            self.last = Admission(self.workload, waited_ms, (time.perf_counter() - started) * 1000, depth)
            self.controller.release(self.last)
