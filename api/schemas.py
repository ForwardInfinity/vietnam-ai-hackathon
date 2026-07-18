"""Pydantic contracts — map 1:1 với docs (nguồn norm ghi cạnh từng model).

Kiểu Answer theo docs/00-VISION.md §3: không bao giờ là string trần; render 4 mục
cố định: Trả lời / Căn cứ / Xung đột / Thay đổi sắp hiệu lực.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Persona = Literal["employee", "customer"]
TierT = Literal["A", "B", "C", "D"]


# --- Answer (00-VISION §3) ---------------------------------------------------

class PiecewiseBlock(BaseModel):
    """Một nhánh của content piecewise theo (khoảng thời gian × lớp chủ thể)."""
    interval_from: date | None = None
    interval_to: date | None = None          # nửa-mở [from, to); None = vô hạn
    cohort: str | None = None                # mô tả lớp chủ thể; None = mọi chủ thể
    text_vi: str


class Basis(BaseModel):
    """Một căn cứ — ghim vào phiên bản node (expr), kèm provenance chain."""
    ref: str                                 # tag trích dẫn, vd "[1]"
    citation_vi: str                         # "khoản 2 Điều 8 TT 39/2016/TT-NHNN"
    doc_key: str | None = None
    path: str | None = None
    node_id: UUID | None = None
    version: int | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: str | None = None                # nv_status_t
    quote: str | None = None                 # trích đoạn ghim (Tier C sources-only)
    provenance_vi: str | None = None         # "Đ8 TT39, bổ sung bởi TT06, k8–10 ngưng bởi TT10"


class ConflictItem(BaseModel):
    conflict_id: UUID | None = None
    tier: int                                # 1|2|3 (D-33)
    label: str | None = None                 # cfl_label_t
    reason: str
    member_refs: list[str] = Field(default_factory=list)


class UpcomingChange(BaseModel):
    effective_from: date
    description_vi: str
    doc_key: str | None = None
    node_path: str | None = None


class Banner(BaseModel):
    """Banner do CODE lắp từ flags substrate (R-31) — model không thể bỏ/bịa.
    Thứ tự render: conflict > cohort_ambiguous > consolidation_pending > pending_change."""
    kind: str
    text_vi: str


class CoverageAttestation(BaseModel):
    """Freshness = chứng thực coverage theo kênh liệt kê được (D-32), KHÔNG hứa với thế giới."""
    channel: str
    last_seq: str | None = None
    last_checked: datetime | None = None


class Answer(BaseModel):
    """Kiểu trả về của toàn hệ (00-VISION §3). 4 mục render cố định:
    answer=Trả lời · bases=Căn cứ · conflicts=Xung đột · upcoming_changes=Thay đổi sắp hiệu lực."""
    tier: TierT
    audience: Persona
    as_of: date
    as_known: datetime | None = None
    run_id: UUID | None = None               # None ⟺ chưa có snapshot nào được compile
    qa_id: UUID | None = None
    answer: list[PiecewiseBlock] = Field(default_factory=list)
    bases: list[Basis] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    upcoming_changes: list[UpcomingChange] = Field(default_factory=list)
    banners: list[Banner] = Field(default_factory=list)
    coverage: list[CoverageAttestation] = Field(default_factory=list)
    refusal_reason: str | None = None        # bắt buộc khi tier='D'


# --- API request -------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    session_id: UUID | None = None
    as_of: date | None = None                # default: hôm nay
    as_known: datetime | None = None         # trục K
    cohort: dict | None = None               # DSL đóng D-25 — validate ở compiler (F5)
    audience: Persona = "employee"
