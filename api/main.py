"""LawState API — FastAPI /v1 (docs/03 S6).

F1: /health + /v1/ask stub trung thực (Tier D khi chưa có snapshot — hệ không bịa
khi không có căn cứ). Các endpoint còn lại thuộc F3-F6.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from answer.llm_gateway import check_family_guard
from api.schemas import Answer, AskRequest

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://lawstate:lawstate@localhost:5432/lawstate"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # D-30/D-41: judge khác họ extract/compose — vi phạm thì không cho server boot
    check_family_guard()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="LawState API",
    description="Máy tính hiệu lực pháp quy ba trục thời gian + tầng trả lời có kiểm chứng (SHB).",
    version="0.1.0",
)


def _db_ok() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@app.get("/health")
def health() -> JSONResponse:
    db = _db_ok()
    body = {"status": "ok" if db else "degraded", "db": "ok" if db else "unreachable"}
    return JSONResponse(body, status_code=200 if db else 503)


@app.post("/v1/ask", response_model=Answer)
def ask(req: AskRequest) -> Answer:
    """Stub trung thực F1: corpus chưa nạp, chưa có run snapshot nào — mọi câu hỏi
    trả Tier D kèm lý do, coverage attestation rỗng (chưa quét kênh nào). Không có
    code path nào render văn tổng hợp khi không có căn cứ đã compile (INV-7/INV-8)."""
    return Answer(
        tier="D",
        audience=req.audience,
        as_of=req.as_of or date.today(),
        as_known=req.as_known,
        run_id=None,
        answer=[],
        bases=[],
        conflicts=[],
        upcoming_changes=[],
        banners=[],
        coverage=[],
        refusal_reason=(
            "Corpus chưa nạp: chưa có trạng thái hiệu lực nào được compile "
            "(run_id=null), nên không có căn cứ để trả lời. Hệ từ chối thay vì bịa; "
            "câu hỏi được route tới chuyên gia pháp chế."
        ),
    )
