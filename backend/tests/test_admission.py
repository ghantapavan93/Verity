"""Admission to the model: bounded calls in flight, a person served before a corpus job but never at its total expense,
and every call's wait and service time recorded."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from typing import Any

from app.providers.admission import INTERACTIVE_TURNS, AdmissionController, AdmittedProvider
from app.providers.base import Generation


class SlowProvider:
    name = "slow"
    model = "slow-1"

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.concurrent = 0
        self.peak = 0
        self.order: list[str] = []
        self._lock = threading.Lock()

    def healthy(self) -> tuple[bool, str]:
        return True, "slow"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        with self._lock:
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
            self.order.append(user)
        time.sleep(self.seconds)
        with self._lock:
            self.concurrent -= 1
        return Generation(text="{}", input_tokens=1, output_tokens=1, latency_ms=self.seconds * 1000, model=self.model)


def test_calls_in_flight_are_bounded_and_waits_are_recorded() -> None:
    slow = SlowProvider(0.05)
    controller = AdmissionController(limit=1)
    providers = [AdmittedProvider(slow, controller, "interactive") for _ in range(5)]
    threads = [threading.Thread(target=p.generate_json, args=("s", f"call {i}", {})) for i, p in enumerate(providers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert slow.peak == 1, "one call at a time on the one model"
    waits = sorted(p.last.queue_wait_ms for p in providers if p.last)
    assert waits[0] == 0.0 and waits[-1] >= 150, "the last in line waited for the four before it"
    assert all(p.last and p.last.service_ms >= 40 for p in providers)
    snapshot = controller.snapshot()
    assert snapshot["recent"]["interactive"]["calls"] == 5 and snapshot["waiting"] == 0 and snapshot["in_flight"] == 0


class HoldingProvider(SlowProvider):
    """The call asked "hold" keeps the one slot until released, so a test forms its queue before anything is served."""

    def __init__(self, seconds: float) -> None:
        super().__init__(seconds)
        self.release = threading.Event()

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        if user == "hold":
            assert self.release.wait(10), "the held call was never released"
        return super().generate_json(system, user, schema)


def _until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the queue to form"
        time.sleep(0.001)


def test_interactive_calls_go_before_batch_calls_but_batch_still_progresses() -> None:
    # The queue is formed by waiting for it, not by sleeping: under a loaded machine 5 ms sleeps let the held call finish
    # before the queue formed, and the order checked was the order threads happened to start (a release gate, 2026-10-15).
    slow = HoldingProvider(0.02)
    controller = AdmissionController(limit=1)
    blocker = AdmittedProvider(slow, controller, "batch")
    holder = threading.Thread(target=blocker.generate_json, args=("s", "hold", {}))
    holder.start()
    _until(lambda: controller.snapshot()["in_flight"] == 1)  # the slot is taken; everything below queues
    batch = [AdmittedProvider(slow, controller, "batch") for _ in range(3)]
    interactive = [AdmittedProvider(slow, controller, "interactive") for _ in range(6)]
    threads = [threading.Thread(target=p.generate_json, args=("s", f"batch {i}", {})) for i, p in enumerate(batch)]
    for t in threads:
        t.start()
    _until(lambda: controller.snapshot()["waiting"] == 3)
    threads += [threading.Thread(target=p.generate_json, args=("s", f"interactive {i}", {})) for i, p in enumerate(interactive)]
    for t in threads[3:]:
        t.start()
    _until(lambda: controller.snapshot()["waiting"] == 9)
    slow.release.set()
    for t in [holder, *threads]:
        t.join()
    order = slow.order[1:]  # after the holder
    assert order[:INTERACTIVE_TURNS] == [f"interactive {i}" for i in range(INTERACTIVE_TURNS)], "people first"
    assert order[INTERACTIVE_TURNS].startswith("batch"), "then one batch call: a corpus job is not starved"
    assert slow.peak == 1
    assert max(p.last.queue_wait_ms for p in batch if p.last) > max(p.last.queue_wait_ms for p in interactive[:INTERACTIVE_TURNS] if p.last)


def test_a_failing_call_still_releases_its_slot() -> None:
    class Broken:
        name = "broken"
        model = "b"

        def healthy(self) -> tuple[bool, str]:
            return False, "broken"

        def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
            raise RuntimeError("down")

    controller = AdmissionController(limit=1)
    provider = AdmittedProvider(Broken(), controller, "interactive")
    for _ in range(3):
        with contextlib.suppress(RuntimeError):
            provider.generate_json("s", "u", {})
    assert controller.snapshot()["in_flight"] == 0 and controller.depth == 0
    assert provider.healthy()[1].endswith("admission limit 1, 0 waiting")


def test_the_fifo_policy_serves_arrival_order_and_exists_only_for_the_measurement() -> None:
    slow = SlowProvider(0.02)
    controller = AdmissionController(limit=1, policy="fifo")
    holder = AdmittedProvider(slow, controller, "batch")
    holding = threading.Thread(target=holder.generate_json, args=("s", "hold", {}))
    holding.start()
    time.sleep(0.005)
    order = ["batch 0", "interactive 0", "batch 1", "interactive 1"]
    threads = []
    for name in order:
        provider = AdmittedProvider(slow, controller, "batch" if name.startswith("batch") else "interactive")
        threads.append(threading.Thread(target=provider.generate_json, args=("s", name, {})))
        threads[-1].start()
        time.sleep(0.005)
    for t in [holding, *threads]:
        t.join()
    assert slow.order[1:] == order and controller.snapshot()["policy"] == "fifo"


def test_the_factory_admits_every_provider_through_one_controller(monkeypatch: object, tmp_path: object) -> None:
    from app.providers import admission, make_provider

    interactive = make_provider("replay", workload="interactive")
    batch = make_provider("replay", workload="batch")
    assert isinstance(interactive, AdmittedProvider) and isinstance(batch, AdmittedProvider)
    assert interactive.controller is admission and batch.controller is admission and admission.limit >= 1
    assert interactive.workload == "interactive" and batch.workload == "batch"
