"""POST /v1/eval/run (F7, 501 khi chưa merge) + POST /v1/feedback (kênh SEM d, D-37)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api import db, integrations
from api.auth import get_role, require_curator
from api.view_models import FeedbackOut, FeedbackRequest

router = APIRouter(tags=["misc"])


@router.post("/eval/run", dependencies=[Depends(require_curator)])
def eval_run(payload: dict | None = None):
    """Chạy golden set (04) → report. F7 chưa merge → 501 trung thực."""
    try:
        report = integrations.run_eval(**(payload or {}))
    except integrations.IntegrationMissing as missing:
        raise HTTPException(501, detail=missing.todo)
    return report


@router.post("/feedback", response_model=FeedbackOut)
def feedback(body: FeedbackRequest, role: str = Depends(get_role)):
    """Nút "nghi đã cũ" (FR-8, R-37) — mọi role đều gửi được; node/qa optional."""
    with db.tx() as conn:
        row = conn.execute(
            """INSERT INTO feedback (qa_id, node_id, kind, note)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            [body.qa_id, body.node_id, body.kind, (body.note or "") + f" [role={role}]"],
        ).fetchone()
        return FeedbackOut(id=row["id"])
