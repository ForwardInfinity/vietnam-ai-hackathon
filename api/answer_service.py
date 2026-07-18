"""Tính Answer cho /v1/ask — seam giữa bề mặt API (F6) và answering pipeline (F5).

F5 đã merge → gọi answer.pipeline qua api.integrations (một chỗ đổi chữ ký).
F5 chưa merge → stub TRUNG THỰC: Tier D + lý do; có run/coverage thì vẫn attest
(meta thật, nội dung từ chối) và ghi answer_log (INV-10) khi có run_id.
KHÔNG code path nào bịa văn tổng hợp ở đây (INV-7/INV-8).
"""
from __future__ import annotations

import json
import logging
from datetime import date

from api import db, gate, integrations
from api.auth import effective_persona
from api.schemas import Answer, AskRequest, CoverageAttestation

log = logging.getLogger("lawstate.answer")


def _latest_run_id(conn) -> str | None:
    row = conn.execute(
        "SELECT run_id FROM replay_run WHERE finished IS NOT NULL ORDER BY finished DESC LIMIT 1"
    ).fetchone()
    return str(row["run_id"]) if row else None


def _coverage(conn) -> list[CoverageAttestation]:
    rows = conn.execute(
        "SELECT channel, last_seq, last_checked FROM coverage ORDER BY channel"
    ).fetchall()
    return [CoverageAttestation(**r) for r in rows]


def _log_answer(conn, req: AskRequest, ans: Answer) -> None:
    """INV-10: ghi answer_log MỌI câu — chỉ khi có run_id (cột NOT NULL).
    TODO(F4): trước replay run đầu tiên, câu hỏi chưa log được (schema đòi run_id)."""
    if ans.run_id is None:
        return
    row = conn.execute(
        """INSERT INTO answer_log (session_id, question, audience, as_of, as_known,
                                   tier, claims, retrieved, banners, run_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING qa_id""",
        (
            req.session_id,
            req.question,
            "public" if ans.audience == "customer" else "internal",
            ans.as_of,
            ans.as_known,
            ans.tier,
            json.dumps([]),
            json.dumps([]),
            json.dumps([b.model_dump(mode="json") for b in ans.banners]),
            ans.run_id,
        ),
    ).fetchone()
    ans.qa_id = row["qa_id"]


def compute_answer(req: AskRequest, role: str) -> Answer:
    persona = effective_persona(role, req.audience)
    req = req.model_copy(update={"audience": persona})
    entitlements = gate.entitlements_for(persona)

    # Đường F5 (khi merge) — mọi filter audience nằm trong query_builder một cửa của họ
    try:
        ans = integrations.run_answer_pipeline(req, entitlements)
        if isinstance(ans, Answer):
            return ans
        return Answer.model_validate(ans)
    except integrations.IntegrationMissing as missing:
        return _honest_stub(req, persona, missing.todo)


def _honest_stub(req: AskRequest, persona: str, todo: str) -> Answer:
    as_of = req.as_of or date.today()
    run_id = None
    coverage: list[CoverageAttestation] = []
    try:
        with db.tx() as conn:
            run_id = _latest_run_id(conn)
            coverage = _coverage(conn)
    except Exception:
        pass  # DB chưa sẵn sàng → refusal vẫn đúng, metadata rỗng

    if run_id is None:
        reason = (
            "Chưa có trạng thái hiệu lực nào được compile (chưa có replay run) — "
            "không có căn cứ để trả lời. Hệ từ chối thay vì bịa; câu hỏi được "
            "route tới chuyên gia pháp chế. [" + todo + "]"
        )
    else:
        reason = (
            "Snapshot hiệu lực đã có (run được pin ở meta) nhưng answering pipeline "
            "chưa được nối — hệ từ chối thay vì trả lời không kiểm chứng. [" + todo + "]"
        )

    ans = Answer(
        tier="D",
        audience=persona,  # type: ignore[arg-type]
        as_of=as_of,
        as_known=req.as_known,
        run_id=run_id,  # type: ignore[arg-type]
        coverage=coverage,
        refusal_reason=reason,
    )

    if run_id is not None:
        try:
            with db.tx() as conn:
                _log_answer(conn, req, ans)
        except Exception as exc:  # log lỗi nhưng không giết câu trả lời
            log.warning("answer_log ghi lỗi: %s", exc)
    return ans
