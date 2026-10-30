from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..application.create_memo import create_memo as create_memo_for_run
from ..application.create_memo import memo_file
from ..application.workspace import require_memo, require_run
from ..db import get_session
from ..errors import NotFound
from ..models import Memo
from ..schemas import MemoIn, MemoOut
from .access import current_workspace
from .contract import CONFLICT, FOUND, GATED, INVALID, WRITES, held_or_created, media, merged

router = APIRouter(prefix="/api/memos", tags=["memos"], responses=GATED)
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _out(memo: Memo) -> MemoOut:
    return MemoOut(
        id=memo.id,
        run_id=memo.run_id,
        docx_url=f"/api/memos/{memo.id}/docx",
        html_url=f"/api/memos/{memo.id}/html",
        docx_sha256=memo.docx_sha256,
        review_head=memo.review_head or "",
    )


@router.post("", response_model=MemoOut, status_code=status.HTTP_201_CREATED, responses=merged(WRITES, INVALID, FOUND, CONFLICT, held_or_created(MemoOut)))
def create_memo(body: MemoIn, response: Response, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> MemoOut:
    """201 with a memo for the run's current review state, or 200 with the one already written under it and under the
    rules in force (application.create_memo.content_key). A review after a memo, or a change to what a memo would say,
    makes the next request write a new memo; the earlier one is kept as it was, and served by its id."""
    require_run(session, body.run_id, workspace)
    created = create_memo_for_run(session, body.run_id)
    if not created.created:
        response.status_code = status.HTTP_200_OK
    return _out(created.memo)


# The memo page is served from the workbench's own origin and carries text from an uploaded contract, escaped when it was
# written (memo.service). The policy is the second line: it runs nothing, loads nothing and is framed by no one; its one
# inline <style> is all it may use.
MEMO_POLICY = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


@router.get("/{memo_id}/html", response_class=HTMLResponse, responses=FOUND)
def memo_as_html(memo_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> HTMLResponse:
    return HTMLResponse(require_memo(session, memo_id, workspace).html, headers={"Content-Security-Policy": MEMO_POLICY})


@router.get("/{memo_id}/docx", response_class=FileResponse, responses=merged(FOUND, media(DOCX, "The memo as a Word document.")))
def memo_as_docx(memo_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> FileResponse:
    memo = require_memo(session, memo_id, workspace)
    path = memo_file(memo)
    if not path.is_file():
        # The record is intact and its file is not in this store: say that, rather than fail while opening it.
        raise NotFound("memo file", memo_id)
    return FileResponse(
        path,
        media_type=DOCX,
        filename=f"review-memo-{memo.run_id}.docx",
    )
