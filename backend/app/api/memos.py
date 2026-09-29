from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..application.create_memo import create_memo as create_memo_for_run
from ..db import get_session
from ..errors import NotFound
from ..models import Memo
from ..schemas import MemoIn, MemoOut

router = APIRouter(prefix="/api/memos", tags=["memos"])


def _out(memo: Memo) -> MemoOut:
    return MemoOut(id=memo.id, run_id=memo.run_id, docx_url=f"/api/memos/{memo.id}/docx", html_url=f"/api/memos/{memo.id}/html", docx_sha256=memo.docx_sha256)


@router.post("", response_model=MemoOut, status_code=status.HTTP_201_CREATED)
def create_memo(body: MemoIn, response: Response, session: Session = Depends(get_session)) -> MemoOut:
    """201 with the run's memo, or 200 with the one written earlier: the run is immutable, so is its memo."""
    created = create_memo_for_run(session, body.run_id)
    if not created.created:
        response.status_code = status.HTTP_200_OK
    return _out(created.memo)


@router.get("/{memo_id}/html", response_class=HTMLResponse)
def memo_as_html(memo_id: str, session: Session = Depends(get_session)) -> HTMLResponse:
    memo = session.get(Memo, memo_id)
    if memo is None:
        raise NotFound("memo", memo_id)
    return HTMLResponse(memo.html)


@router.get("/{memo_id}/docx")
def memo_as_docx(memo_id: str, session: Session = Depends(get_session)) -> FileResponse:
    memo = session.get(Memo, memo_id)
    if memo is None:
        raise NotFound("memo", memo_id)
    return FileResponse(
        memo.docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"review-memo-{memo.run_id}.docx",
    )
