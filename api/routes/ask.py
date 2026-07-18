"""POST /v1/ask — JSON (contract F1 giữ nguyên) + SSE khi Accept: text/event-stream (S6).

SSE là ADDITIVE qua content negotiation — client cũ nhận JSON như trước, không breaking.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api import answer_service
from api.auth import get_role
from api.schemas import Answer, AskRequest
from api.sse import answer_to_events

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=Answer)
def ask(req: AskRequest, request: Request, role: str = Depends(get_role)):
    """{question, as_of?, as_known?, cohort?, audience} → Answer.

    - JSON (mặc định): trả `Answer` — 4 mục cố định + tier + banner + coverage.
    - SSE (`Accept: text/event-stream`): meta → token → citation → banner → tier → done.
    Audience hiệu dụng: role customer bị ghim customer (INV-12) — không thể nâng quyền qua body.
    """
    ans = answer_service.compute_answer(req, role)
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return StreamingResponse(
            answer_to_events(ans),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return ans
