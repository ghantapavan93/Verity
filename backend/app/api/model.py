"""POST /api/model/wake: the interface asks for the model to be woken when a reader opens a contract, so the question
finds it awake (application/wake_model.py). Behind the gate like every route that spends: a request without a session,
or from another origin, is refused before anything is woken."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from ..application.start_run import refuse_past_daily_budget
from ..application.wake_model import waker
from ..db import get_session
from ..errors import TooManyRequests
from ..schemas import ModelWakeOut
from . import access

router = APIRouter(prefix="/api/model", tags=["model"])


@router.post("/wake", response_model=ModelWakeOut)
def wake(session: DbSession = Depends(get_session)) -> ModelWakeOut:
    # Nothing to wake for: questions are paused, or today's questions are spent.
    if access.paused():
        return ModelWakeOut(state="off")
    try:
        refuse_past_daily_budget(session)
    except TooManyRequests:
        return ModelWakeOut(state="limit")
    return ModelWakeOut(state=waker.request())
