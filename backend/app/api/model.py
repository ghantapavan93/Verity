"""POST /api/model/wake: the interface asks for the model to be woken when a reader adds a contract or starts a question, so the question
finds it awake (application/wake_model.py). Behind the gate like every route that spends: a request without a session,
or from another origin, is refused before anything is woken."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession

from ..application.quotas import refuse_if_spent, run_quotas
from ..application.wake_model import waker
from ..db import get_session
from ..errors import Busy, TooManyRequests
from ..schemas import ModelWakeOut
from . import access
from .contract import GATED

router = APIRouter(prefix="/api/model", tags=["model"], responses=GATED)

# One network's share of the day's wake-ups (access.client_network, as every other window): a script holding a session
# could otherwise spend all of them (security review, 2026-10-13). Three an hour still wakes the model for a reader each
# time it has gone back to sleep. By full address, one IPv6 /64 spent the day's ten in an hour (stress test, 2026-10-30).
WAKES_PER_NETWORK, WAKE_WINDOW_S = 3, 3600
address_wakes = access.SlidingWindow(WAKES_PER_NETWORK, WAKE_WINDOW_S)


@router.post("/wake", response_model=ModelWakeOut)
def wake(request: Request, session: DbSession = Depends(get_session)) -> ModelWakeOut:
    # Nothing to wake for: questions are paused, or today's questions are spent, everyone's or this reader's (the quotas
    # a new run is admitted against would refuse their next question before any model call).
    if access.paused():
        return ModelWakeOut(state="off")
    try:
        refuse_if_spent(session, run_quotas(access.current_workspace(request)))
    except (TooManyRequests, Busy):  # Busy: the visitors' queue is full (quotas.run_quotas); a wake would wait behind it
        return ModelWakeOut(state="limit")
    network = access.client_network(request)
    return ModelWakeOut(state=waker.request(allow=lambda: address_wakes.take(network) is None))
