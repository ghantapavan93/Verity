"""POST /api/model/wake: the interface asks for the model to be woken when a reader adds a contract or starts a question, so the question
finds it awake (application/wake_model.py). Behind the gate like every route that spends: a request without a session,
or from another origin, is refused before anything is woken."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..application.start_run import refuse_past_daily_budget
from ..application.wake_model import waker
from ..config import settings
from ..db import get_session
from ..errors import TooManyRequests
from ..models import Run
from ..schemas import ModelWakeOut
from . import access

router = APIRouter(prefix="/api/model", tags=["model"])

# One address's share of the day's wake-ups: a script holding a session could otherwise spend all of them (security
# review, 2026-10-13). Three an hour still wakes the model for a reader each time it has gone back to sleep.
WAKES_PER_ADDRESS, WAKE_WINDOW_S = 3, 3600
address_wakes = access.SlidingWindow(WAKES_PER_ADDRESS, WAKE_WINDOW_S)


@router.post("/wake", response_model=ModelWakeOut)
def wake(request: Request, session: DbSession = Depends(get_session)) -> ModelWakeOut:
    # Nothing to wake for: questions are paused, today's questions are spent, or this reader's are (api/access.py
    # limit_run_starts would refuse their next question before any model call).
    if access.paused():
        return ModelWakeOut(state="off")
    try:
        refuse_past_daily_budget(session)
    except TooManyRequests:
        return ModelWakeOut(state="limit")
    workspace = access.current_workspace(request)
    if access.is_public_workspace(workspace):
        asked = session.scalar(select(func.count(Run.id)).where(Run.workspace_id == workspace, Run.created_at >= access._day_start())) or 0
        if asked >= settings.anonymous_max_runs_per_day:
            return ModelWakeOut(state="limit")
    address = access.client_address(request)
    return ModelWakeOut(state=waker.request(allow=lambda: address_wakes.take(address) is None))
