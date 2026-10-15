"""POST /api/model/wake: the interface asks for the model to be woken when a reader adds a contract or starts a question, so the question
finds it awake (application/wake_model.py). Behind the gate like every route that spends: a request without a session,
or from another origin, is refused before anything is woken."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession

from ..application.quotas import refuse_if_spent, run_quotas
from ..application.wake_model import waker
from ..db import get_session
from ..errors import TooManyRequests
from ..schemas import ModelWakeOut
from . import access

router = APIRouter(prefix="/api/model", tags=["model"])

# One address's share of the day's wake-ups: a script holding a session could otherwise spend all of them (security
# review, 2026-10-13). Three an hour still wakes the model for a reader each time it has gone back to sleep.
WAKES_PER_ADDRESS, WAKE_WINDOW_S = 3, 3600
address_wakes = access.SlidingWindow(WAKES_PER_ADDRESS, WAKE_WINDOW_S)


@router.post("/wake", response_model=ModelWakeOut)
def wake(request: Request, session: DbSession = Depends(get_session)) -> ModelWakeOut:
    # Nothing to wake for: questions are paused, or today's questions are spent, everyone's or this reader's (the quotas
    # a new run is admitted against would refuse their next question before any model call).
    if access.paused():
        return ModelWakeOut(state="off")
    try:
        refuse_if_spent(session, run_quotas(access.current_workspace(request)))
    except TooManyRequests:
        return ModelWakeOut(state="limit")
    address = access.client_address(request)
    return ModelWakeOut(state=waker.request(allow=lambda: address_wakes.take(address) is None))
