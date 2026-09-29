from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..application.save_guidance import save_guidance
from ..db import get_session
from ..errors import NotFound
from ..models import Guidance
from ..schemas import GuidanceIn, GuidanceOut

router = APIRouter(prefix="/api/guidance", tags=["guidance"])


def _out(guidance: Guidance) -> GuidanceOut:
    return GuidanceOut(id=guidance.id, sha256=guidance.sha256, text=guidance.text)


@router.post("", response_model=GuidanceOut, status_code=status.HTTP_201_CREATED)
def create_guidance(body: GuidanceIn, response: Response, session: Session = Depends(get_session)) -> GuidanceOut:
    """201 with a new guidance record, or 200 with the record that already holds these words."""
    saved = save_guidance(session, body.text)
    if not saved.created:
        response.status_code = status.HTTP_200_OK
    return _out(saved.guidance)


@router.get("/{guidance_id}", response_model=GuidanceOut)
def get_guidance(guidance_id: str, session: Session = Depends(get_session)) -> GuidanceOut:
    guidance = session.get(Guidance, guidance_id)
    if guidance is None:
        raise NotFound("guidance", guidance_id)
    return _out(guidance)
