"""Pydantic contracts — map 1:1 với docs (nguồn norm ghi cạnh từng model). ĐÓNG BĂNG theo CONTRACTS.md.

Gồm 4 nhóm:
  1. Enums — giá trị TRÙNG KHỚP từng ký tự với các TYPE trong db/init.sql (S2)
  2. Model bảng — 1:1 với 16 bảng DDL (NOT NULL ⟺ required; PK-implied NOT NULL cũng required)
  3. Model pipeline — CompiledQuestion (S5.1) · ExtractedOp (R-11) · ComposerOutput (R-31)
  4. Answer — kiểu trả về của toàn hệ (00-VISION §3) + AskRequest

Đổi BREAKING bất kỳ thứ gì ở đây → DỪNG, báo user (xem CONTRACTS.md).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Persona = Literal["employee", "customer"]
TierT = Literal["A", "B", "C", "D"]


# =============================================================================
# 1. Enums — trùng khớp db/init.sql (test: tests/test_schemas.py)
# =============================================================================

class AudienceT(str, Enum):
    public = "public"
    internal = "internal"
    restricted = "restricted"


class OpKindT(str, Enum):
    amend = "amend"
    insert = "insert"
    repeal = "repeal"
    suspend = "suspend"
    close_window = "close_window"
    dinh_chinh = "dinh_chinh"
    norm_decl = "norm_decl"
    blanket_derogation = "blanket_derogation"


class OpStatusT(str, Enum):
    proposed = "proposed"
    ratified = "ratified"
    rejected = "rejected"
    superseded = "superseded"


class NodeRoleT(str, Enum):
    rule = "rule"
    definition = "definition"
    scope = "scope"
    exception = "exception"
    transition = "transition"
    effectivity = "effectivity"
    amending = "amending"
    form = "form"
    appendix = "appendix"


class NvStatusT(str, Enum):
    active = "active"
    suspended = "suspended"
    repealed = "repealed"


class EdgeKindT(str, Enum):
    dinh_nghia = "dinh_nghia"
    tham_quyen = "tham_quyen"
    ngoai_le = "ngoai_le"
    chu_de = "chu_de"
    chuyen_tiep = "chuyen_tiep"
    frontier = "frontier"


class RiskT(str, Enum):
    definitional = "definitional"
    prescriptive = "prescriptive"


class CflLabelT(str, Enum):
    mau_thuan = "mau_thuan"
    chat_hon_ve_minh = "chat_hon_ve_minh"
    chat_hon_ve_doi_tac = "chat_hon_ve_doi_tac"
    khac_pham_vi = "khac_pham_vi"


class CflForkT(str, Enum):
    internal_internal = "internal_internal"
    internal_external = "internal_external"
    external_external = "external_external"
    advisory = "advisory"


class CflStatusT(str, Enum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"
    accepted_risk = "accepted_risk"


class SevT(str, Enum):
    interruptive = "interruptive"
    advisory = "advisory"


class PevKindT(str, Enum):
    open_suspension = "open_suspension"
    open_conflict = "open_conflict"


# =============================================================================
# 2. Model bảng — 1:1 DDL (thứ tự như init.sql)
# =============================================================================

class Artifact(BaseModel):
    id: str                                  # sha256 file
    doc_key: str                             # '39/2016/TT-NHNN'
    doc_type: str                            # luat|nghi_quyet|nghi_dinh|thong_tu|quyet_dinh|cong_van|noi_bo|bieu_mau|vbhn
    issuer: str                              # 'QH','CP','NHNN','HDTP','SHB.<phòng>'
    title: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    audience: AudienceT = AudienceT.internal
    owner: str | None = None
    review_by: date | None = None
    channel: str | None = None
    is_oracle: bool = False
    synthetic: bool = False
    ingested_at: datetime | None = None      # TRỤC K (DB default now())
    raw: bytes | None = None
    text: str | None = None


class Node(BaseModel):
    id: UUID | None = None                   # birth-id (DB default), không tái dùng (INV-2)
    artifact_id: str
    parent_id: UUID | None = None
    path: str                                # 'dieu:8/khoan:2/diem:a/tiet:iii' — địa chỉ LÚC SINH
    label: str | None = None
    seq: int | None = None
    role: NodeRoleT = NodeRoleT.rule
    page_anchor: dict[str, Any] | None = None


class Alias(BaseModel):
    doc_key: str
    path: str
    valid_from: date                         # PK ⇒ NOT NULL
    node_id: UUID | None = None
    valid_to: date | None = None


class Norm(BaseModel):
    id: UUID                                 # cùng id xuyên chuỗi kế vị
    topic: str
    artifact_id: str                         # PK ⇒ NOT NULL; 1 hàng mỗi hiện thân
    valid_from: date | None = None
    valid_to: date | None = None
    correlation: dict[str, Any] | None = None  # tương chiếu cũ↔mới — NON-BINDING (D-08)


class Op(BaseModel):
    id: UUID | None = None
    kind: OpKindT
    source_artifact: str
    source_node: UUID | None = None
    source_quote: str                        # span nguyên văn — bắt buộc
    seq: int
    target_node: UUID | None = None
    target_op: UUID | None = None
    target_norm: UUID | None = None
    target_part: Literal["body", "heading"] = "body"
    new_text: str | None = None
    new_heading: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    valid_to_event: str | None = None        # sự kiện chưa định danh (D-11)
    scope_predicate: dict[str, Any] | None = None  # DSL đóng D-25 (validate = ScopePredicate)
    risk_class: RiskT | None = None
    extractor: str                           # 'rule','llm:<model>','curator:<id>'
    confidence: float | None = None
    status: OpStatusT = OpStatusT.proposed
    ratified_by: str | None = None
    ratified_at: datetime | None = None
    ratify_batch: UUID | None = None
    superseded_by: UUID | None = None
    ingested_at: datetime | None = None


class RatifyBatch(BaseModel):
    id: UUID | None = None
    invariant_template: dict[str, Any]       # S4.4
    description: str | None = None
    approved_by: str
    approved_at: datetime | None = None
    spot_check_rate: float = 0.1
    spot_checked: list[UUID] | None = None


class Edge(BaseModel):
    id: UUID | None = None
    src_node: UUID
    src_version: int                         # edge dẫn xuất theo PHIÊN BẢN node nguồn (D-13)
    dst_node: UUID | None = None
    dst_norm: UUID | None = None
    frontier_ref: str | None = None          # cả 3 đích NULL = unresolved (backlog, R-10)
    kind: EdgeKindT
    raw_citation: str | None = None
    resolved_against: date | None = None
    confidence: float = 1.0


class NodeVersion(BaseModel):
    node_id: UUID
    version: int
    heading: str | None = None
    body: str | None = None
    status: NvStatusT
    valid_from: date                         # nửa-mở [from, to)
    valid_to: date | None = None
    scope_predicate: dict[str, Any] | None = None
    scope_hash: str = ""                     # chiều s TRONG khóa (D-04)
    provenance: list[UUID]                   # chuỗi op tạo version này
    run_id: UUID
    retrievable: bool                        # false ⟺ role='amending' ∨ artifact.is_oracle (INV-8)
    embedding: list[float] | None = None     # vector(1024) BGE-M3 (D-40)


class ReplayRun(BaseModel):
    run_id: UUID
    k_cutoff: datetime
    corpus_hash: str
    started: datetime | None = None
    finished: datetime | None = None
    ops_count: int | None = None


class Conflict(BaseModel):
    id: UUID | None = None
    member_versions: list[dict[str, Any]]    # [{node_id, version}] — unsat-core tối thiểu
    tier: Literal[1, 2, 3]
    label: CflLabelT | None = None
    fork: CflForkT | None = None
    doctrine: dict[str, Any] | None = None   # {rank_a, rank_b, same_issuer, art156}
    reason: str
    status: CflStatusT = CflStatusT.open
    resolved_by_op: UUID | None = None
    ticket_ref: str | None = None
    detected_by: str | None = None
    created_at: datetime | None = None


class Notification(BaseModel):
    id: UUID | None = None
    op_id: UUID | None = None
    affected_node: UUID | None = None
    affected_doc: str | None = None
    owner: str | None = None
    severity: SevT = SevT.advisory
    acked: bool = False
    created_at: datetime | None = None


class Coverage(BaseModel):
    channel: str
    last_seq: str | None = None
    last_checked: datetime | None = None


class PendingEvent(BaseModel):
    id: UUID | None = None
    kind: PevKindT
    ref: UUID                                # op có valid_to_event | conflict chờ statement giải
    predicate: str
    status: Literal["open", "closed"] = "open"
    closed_by_op: UUID | None = None


class Precedence(BaseModel):
    doc_type: str | None = None
    issuer: str | None = None
    rank: int
    source_node: UUID | None = None          # quy tắc ưu tiên là statement CÓ NGUỒN (D-15)
    valid_from: date | None = None
    valid_to: date | None = None


class AnswerLog(BaseModel):
    qa_id: UUID | None = None
    session_id: UUID | None = None
    question: str
    audience: AudienceT                      # audience_t của DDL (≠ Persona của Answer)
    as_of: date
    as_known: datetime | None = None
    tier: TierT
    claims: list[dict[str, Any]]             # [{text, node_version_refs[], hard_pass, judge_verdict}]
    retrieved: list[dict[str, Any]]
    conflicts: list[UUID] | None = None
    banners: list[dict[str, Any]]
    run_id: UUID
    created_at: datetime | None = None


class Feedback(BaseModel):
    id: UUID | None = None
    qa_id: UUID | None = None
    node_id: UUID | None = None
    kind: str = "nghi_da_cu"                 # kênh SEM (d) — D-37
    note: str | None = None
    created_at: datetime | None = None


# =============================================================================
# 3. Model pipeline
# =============================================================================

class ScopePredicate(BaseModel):
    """DSL applicability ĐÓNG (D-25) — không predicate form nào khác hợp lệ (extra=forbid).
    Cũng chính là `cohort` của CompiledQuestion (S5.1) — một chỗ sở hữu DSL."""
    model_config = ConfigDict(extra="forbid")

    contract_signed_before: date | None = None
    not_amended_on_or_after: date | None = None
    entity_class: str | None = None


Cohort = ScopePredicate


class CompiledQuestion(BaseModel):
    """Output của question compiler (S5.1, R-27) — phần không-commodity."""
    topic_terms: list[str]
    as_of: date                              # default today do compiler điền
    as_known: datetime | None = None
    cohort: Cohort = Field(default_factory=Cohort)
    audience: Persona
    mode: Literal["current", "point_in_time", "history", "pending"]
    pinpoint: str | None = None              # địa chỉ bề mặt → đường alias→timeline (D-27)


class ExtractedOp(BaseModel):
    """Một op do LLM extract đề xuất (R-11) — JSON schema output contract của role=extract.
    (`close_window` KHÔNG có ở đây: nó do sweep/curator sinh, không do extractor.)"""
    kind: Literal["amend", "insert", "repeal", "suspend",
                  "dinh_chinh", "norm_decl", "blanket_derogation"]
    target_surface: str | None = None        # "khoản 2 Điều 8 TT 39/2016/TT-NHNN" | null
    target_is_amending_provision: bool = False  # true ⇒ resolver chuyển thành target_op (R-12)
    target_part: Literal["body", "heading"] = "body"
    new_text: str | None = None
    new_heading: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    valid_to_event: str | None = None
    scope_predicate: ScopePredicate = Field(default_factory=ScopePredicate)
    source_quote: str                        # NGUYÊN VĂN BẮT BUỘC
    confidence: float = 0.0


class ExtractionResult(BaseModel):
    ops: list[ExtractedOp]


class ComposerClaim(BaseModel):
    id: str                                  # tag "[n]"
    text: str
    refs: list[str]


class ComposerBasis(BaseModel):
    ref: str
    citation_vi: str
    interval: str                            # cửa sổ hiệu lực render sẵn, vd "01/09/2023 → nay"


class ComposerOutput(BaseModel):
    """Composer contract (R-31) — JSON schema output của role=compose.
    Thiếu căn cứ → refusal (không độn văn)."""
    answer_vi: str                           # markdown, mọi câu quy phạm mang claim tag [n]
    claims: list[ComposerClaim]
    bases: list[ComposerBasis]
    refusal: str | None = None


# =============================================================================
# 4. Answer (00-VISION §3) + request — kiểu trả về của toàn hệ, không bao giờ string trần
# =============================================================================

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


class AskRequest(BaseModel):
    question: str
    session_id: UUID | None = None
    as_of: date | None = None                # default: hôm nay
    as_known: datetime | None = None         # trục K
    cohort: Cohort | None = None             # DSL đóng D-25
    audience: Persona = "employee"
