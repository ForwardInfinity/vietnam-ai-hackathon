"""LawState API — FastAPI /v1 đủ bảng S6 (docs/03).

F1 nền: /health + /v1/ask JSON. F6: SSE cho /ask (content negotiation — additive),
timeline/graph/norms/artifacts, nhóm /admin/* (ingest, ops queue, decision, batches,
replay, backlog, conflicts, demand, notifications), /eval/run, /feedback.

Auth hackathon: header X-Role (employee|customer|curator; thiếu → customer);
/admin/* đòi curator; mutation đòi X-Actor (INV-6). Audience lọc qua api.gate
MỘT CỬA (INV-12) — không endpoint nào tự viết filter.
Logic F3/F4/F5/F7 gọi qua api.integrations — chưa merge thì stub/501 trung thực.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from answer.llm_gateway import check_family_guard
from api.routes import admin_misc, admin_ops, ask, misc, nodes

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
    version="0.2.0",
)

@app.exception_handler(psycopg.OperationalError)
async def db_unreachable(request, exc):  # endpoint cần DB nhưng DB chưa sẵn — 503 trung thực, không traceback
    return JSONResponse(
        {"detail": "Database unreachable — thử lại sau (xem /health)."}, status_code=503
    )


app.include_router(ask.router, prefix="/v1")
app.include_router(nodes.router, prefix="/v1")
app.include_router(admin_ops.router, prefix="/v1")
app.include_router(admin_misc.router, prefix="/v1")
app.include_router(misc.router, prefix="/v1")


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
