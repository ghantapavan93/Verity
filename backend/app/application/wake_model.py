"""Waking the model before the question. A hosted model that sleeps when idle takes minutes to wake (Modal, measured
2026-10-13: the server up in 67 s, the first token at 168 s); a reader who opens a contract and then reads and types
gives it that time, so opening a contract asks for a wake-up and the question finds the model awake.

A wake-up costs a cold start and the endpoint's idle minutes whether or not a question follows, so it is bounded: none
while one is under way, none while the model is answering or answered recently (settings.model_awake_s), and at most
settings.model_wakeups_per_day a UTC day for all readers together. It runs beside the request, never in it, and a
failure is logged and changes nothing else: the question still checks the model first and waits for it if it must.
Off by default (settings.model_wakeup): the workstation's model runs on the machine itself and never sleeps.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date
from typing import Literal

from ..config import settings
from ..models import utcnow
from ..providers import admission, ollama

log = logging.getLogger(__name__)

# off: this deployment does not wake its model; awake: the model answered recently or is answering; waking: a wake-up
# is under way (this request's or another's); limit: today's wake-ups are spent, and the question will wake it itself.
WakeState = Literal["off", "awake", "waking", "limit"]


def _wake_the_configured_model() -> None:
    ollama.OllamaProvider().wake()


def _today() -> date:
    return utcnow().date()


class ModelWaker:
    def __init__(
        self,
        wake: Callable[[], None] = _wake_the_configured_model,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = _today,
    ) -> None:
        self._wake, self._clock, self._today = wake, clock, today
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._day: date | None = None
        self._spent = 0

    def request(self) -> WakeState:
        """Ask for the model to be woken; say what was done. Never waits for the model."""
        if not settings.model_wakeup or settings.provider.lower() != "ollama":
            return "off"
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return "waking"
            heard = ollama.last_answer()
            if admission.in_flight > 0 or (heard is not None and self._clock() - heard < settings.model_awake_s):
                return "awake"
            today = self._today()
            if today != self._day:
                self._day, self._spent = today, 0
            if self._spent >= settings.model_wakeups_per_day:
                return "limit"
            self._spent += 1
            self._thread = threading.Thread(target=self._run, name="model-wake", daemon=True)
            self._thread.start()
            return "waking"

    def _run(self) -> None:
        started = self._clock()
        try:
            self._wake()
        except Exception as error:  # noqa: BLE001 - a wake-up is a courtesy: any failure is logged, nothing else depends on it
            log.warning("model wake-up failed after %.0f s: %s", self._clock() - started, error)
        else:
            log.info("model awake after %.0f s", self._clock() - started)


# One per process, like the admission controller: every request in this process shares its bounds.
waker = ModelWaker()
