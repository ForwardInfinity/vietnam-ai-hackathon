"""Adapter cho seam của F6 (`api.integrations.run_answer_pipeline`).

F6 gọi: `answer.pipeline.answer_question(req: AskRequest, entitlements=...) -> Answer`.
Đây là lớp mỏng: AskRequest → SessionCtx → answer.service.answer_question trên
PgStore (một cửa). `entitlements` của F6 chỉ để ĐỐI CHIẾU phòng thủ — nguồn
chân lý quyền đọc là retrieval.query_builder.entitlements_for (INV-12, một chỗ).
"""
from __future__ import annotations

import logging

from answer.compiler import SessionCtx
from answer.service import answer_question as _answer
from api.schemas import Answer, AskRequest
from retrieval.query_builder import entitlements_for, pg_store

log = logging.getLogger("lawstate.answer.pipeline")


def answer_question(req: AskRequest, entitlements: tuple[str, ...] | None = None) -> Answer:
    ctx = SessionCtx(
        audience=req.audience,
        as_of=req.as_of,
        as_known=req.as_known,
        cohort=req.cohort,
        session_id=str(req.session_id) if req.session_id else None,
    )
    if entitlements is not None:
        mine = set(entitlements_for(req.audience))
        if set(entitlements) != mine:  # phòng thủ: không bao giờ NỚI quyền theo caller
            log.warning("entitlements caller %s ≠ query_builder %s — dùng bảng một cửa",
                        entitlements, tuple(sorted(mine)))

    import psycopg

    from api.db import database_url

    try:
        with psycopg.connect(database_url()) as conn:
            store = pg_store(conn, as_known=req.as_known)
            return _answer(req.question, ctx, store=store)
    except psycopg.OperationalError as exc:
        # DB không chạm được (smoke/dev không Postgres): vẫn trả lời TRUNG THỰC
        # Tier D như khi chưa có snapshot — không 500, không bịa (INV-7)
        log.warning("answer.pipeline: DB unreachable — trả Tier D honest (%s)", exc)
        return _answer(req.question, ctx, store=None)
