"""Kiểu dữ liệu lõi của engine — pure Python, KHÔNG import DB (S0.2).

Input của fold là duck-type: op dùng thẳng `api.schemas.Op`; node/artifact dùng
NodeInput/ArtifactInput dưới đây (node bảng DDL không mang text — text gốc do parser
cung cấp, xem engine/README.md). Output Version ánh xạ 1:1 cột `node_version` trừ
(version, run_id, retrievable, embedding) do snapshot.py gán lúc ghi.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID


def sv(x: Any) -> Any:
    """Enum → .value; str giữ nguyên (chấp nhận cả enum của api.schemas lẫn str thô)."""
    return getattr(x, "value", x)


def as_utc_ts(dt: datetime | None) -> float:
    """timestamp tất định cho sort key; naive coi như UTC (không phụ thuộc TZ máy)."""
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def jsonable(x: Any) -> Any:
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return jsonable(dataclasses.asdict(x))
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (UUID, date, datetime)):
        return str(x)
    return x


def digest_of(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(jsonable(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ArtifactInput:
    """Trường artifact mà fold cần (D-23 sort key + base window + oracle skip)."""
    id: str                       # khớp op.source_artifact / node.artifact_id
    doc_key: str
    doc_type: str                 # luat|nghi_quyet|nghi_dinh|thong_tu|quyet_dinh|cong_van|noi_bo|bieu_mau|vbhn
    issuer: str                   # 'QH','CP','NHNN','HDTP','SHB.<phòng>'
    issued_date: date | None = None
    effective_date: date | None = None
    title: str | None = None
    is_oracle: bool = False       # VBHN — fold BỎ QUA node của nó (chỉ dùng oracle_diff, D-22)
    audience: str = "internal"
    owner: str | None = None
    text: str | None = None
    ingested_at: datetime | None = None


@dataclass(frozen=True)
class NodeInput:
    """Node + text gốc lúc sinh (base version). Node do `insert` sinh: heading/body None —
    nội dung base lấy từ new_text/new_heading của op insert (02 §3)."""
    id: UUID
    artifact_id: str
    doc_key: str
    path: str
    role: str = "rule"            # node_role_t
    heading: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class Version:
    """Một phiên bản hiệu lực — cửa sổ nửa-mở [valid_from, valid_to); valid_to None = mở."""
    node_id: UUID
    version: int
    heading: str | None
    body: str | None
    status: str                   # active|suspended|repealed
    valid_from: date
    valid_to: date | None
    scope_predicate: dict[str, Any] | None   # None | DSL D-25 | {"complement_of": DSL}
    scope_hash: str
    provenance: tuple[UUID, ...]  # chuỗi op đã áp, thứ tự canonical


@dataclass(frozen=True)
class ConflictCertificate:
    """Tier-2: chồng cửa sổ mà precedence không phân định (D-33) — unsat-core, KHÔNG chọn bừa."""
    node_id: UUID
    member_ops: tuple[UUID, ...]
    window_from: date
    window_to: date | None
    reason: str
    doctrine: dict[str, Any]      # {rank_a, rank_b, same_issuer, art156:'khong_phan_dinh'}
    tier: int = 2


@dataclass(frozen=True)
class PendingWindow:
    """Op treo-theo-sự-kiện chưa được đóng (D-11) — nghĩa vụ sweep sau mỗi ingest."""
    op_id: UUID
    predicate: str
    target_node: UUID | None


@dataclass(frozen=True)
class ScreeningSeed:
    """Blanket derogation: không mutate — chỉ seed conflict screening theo chủ đề (D-14)."""
    op_id: UUID
    source_artifact: str
    valid_from: date | None


@dataclass(frozen=True)
class NormEvent:
    """norm_decl đã phê chuẩn: khai sinh/kế vị Norm (D-08/D-09, correlation non-binding)."""
    norm_id: UUID
    source_artifact: str
    valid_from: date
    op_id: UUID


@dataclass
class CorpusFold:
    """Kết quả fold toàn corpus tại một K."""
    versions: dict[UUID, tuple[Version, ...]] = field(default_factory=dict)
    certificates: tuple[ConflictCertificate, ...] = ()
    open_suspensions: tuple[PendingWindow, ...] = ()
    closed_windows: tuple[tuple[UUID, UUID], ...] = ()   # (op bị đóng, op close_window/repeal)
    screening_seeds: tuple[ScreeningSeed, ...] = ()
    norm_events: tuple[NormEvent, ...] = ()
    notes: tuple[str, ...] = ()                          # tier-1 auto-resolution + op bị bỏ qua
