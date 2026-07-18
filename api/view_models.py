"""Response model cho các endpoint F6 (S6) — TÁCH khỏi api/schemas.py (đóng băng F1).

schemas.py = contract dữ liệu 1:1 DDL + LLM; file này = shape trả về của bề mặt API.
Contract test: tests/api/test_contract_shapes.py validate response bằng đúng các model này.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Timeline / graph / norm (D-27, FR-2)
# ---------------------------------------------------------------------------

class OpProvenance(BaseModel):
    """Một op trong phả hệ version — INV-6 nhìn thấy được: ai ký, per-op hay batch."""
    id: UUID
    kind: str
    source_doc_key: str | None = None
    source_quote: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    valid_to_event: str | None = None
    status: str | None = None
    extractor: str | None = None
    ratified_by: str | None = None           # người ký per-op
    ratify_batch: UUID | None = None
    batch_approved_by: str | None = None     # người ký cả lô (INV-6 đường batch)
    superseded_by: UUID | None = None


class VersionOut(BaseModel):
    node_id: UUID
    version: int
    heading: str | None = None
    body: str | None = None
    status: str
    valid_from: date
    valid_to: date | None = None
    scope_predicate: dict[str, Any] | None = None
    scope_hash: str = ""
    retrievable: bool
    run_id: UUID
    never_active: bool = False               # version treo mà bản active chưa từng tồn tại
    provenance: list[OpProvenance] = Field(default_factory=list)
    diff_from_prev: str | None = None        # unified diff với version liền trước cùng scope


class SuspensionBand(BaseModel):
    valid_from: date
    valid_to: date | None = None             # None = treo vô thời hạn (chờ sự kiện)
    event_predicate: str | None = None
    event_status: str | None = None          # open|closed (pending_event D-11)


class AliasWindow(BaseModel):
    doc_key: str
    path: str
    valid_from: date | None = None
    valid_to: date | None = None


class TimelineOut(BaseModel):
    key: str
    node_id: UUID
    doc_key: str
    path: str
    role: str
    heading: str | None = None
    audience: str
    aliases: list[AliasWindow] = Field(default_factory=list)
    versions: list[VersionOut] = Field(default_factory=list)      # MỌI version, mọi status
    suspensions: list[SuspensionBand] = Field(default_factory=list)
    source_link: str | None = None           # link văn bản gốc (FR-2)
    page_anchor: dict[str, Any] | None = None
    note: str | None = None


class GraphNodeOut(BaseModel):
    node_id: UUID
    doc_key: str
    path: str
    label: str | None = None
    role: str
    heading: str | None = None
    is_center: bool = False


class GraphEdgeOut(BaseModel):
    id: UUID
    src_node: UUID
    src_version: int
    dst_node: UUID | None = None
    dst_norm: UUID | None = None
    frontier_ref: str | None = None
    kind: str
    raw_citation: str | None = None
    confidence: float = 1.0
    direction: Literal["outbound", "inbound"]


class GraphOut(BaseModel):
    key: str
    center_nodes: list[UUID]
    depth: int
    as_of: date | None = None
    nodes: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)
    norms: list[dict[str, Any]] = Field(default_factory=list)     # đích dst_norm có tên
    note: str | None = None


class NormIncarnation(BaseModel):
    artifact_id: str
    doc_key: str | None = None
    title: str | None = None
    doc_type: str | None = None
    issuer: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    correlation: dict[str, Any] | None = None


class NormOut(BaseModel):
    id: UUID
    topic: str
    incarnations: list[NormIncarnation]
    correlation_note: str = "Tương chiếu cũ↔mới là NON-BINDING (D-08) — chỉ để tra cứu, không phải danh tính."


class ArtifactOut(BaseModel):
    id: str
    doc_key: str
    doc_type: str
    issuer: str
    title: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    audience: str
    channel: str | None = None
    is_oracle: bool = False
    synthetic: bool = False
    ingested_at: datetime | None = None
    text: str | None = None


# ---------------------------------------------------------------------------
# Admin: ops queue / decision / batch (FR-9, FR-10)
# ---------------------------------------------------------------------------

class TargetView(BaseModel):
    node_id: UUID | None = None
    doc_key: str | None = None
    path: str | None = None
    heading: str | None = None
    current_text: str | None = None          # version hiệu lực hôm nay (hoặc mới nhất)
    current_version: int | None = None
    current_status: str | None = None
    target_op: UUID | None = None
    target_norm: UUID | None = None


class QueueItem(BaseModel):
    op: dict[str, Any]                       # full row op (schemas.Op tương thích)
    source_doc_key: str | None = None
    source_doc_title: str | None = None
    target: TargetView
    diff: str | None = None                  # unified diff hiện tại vs sau-áp (FR-9)
    queue: Literal["per_op", "batch_eligible"]
    batch_approved_by: str | None = None


class OpsQueueOut(BaseModel):
    status: str
    total: int
    items: list[QueueItem]
    order: str = "risk definitional trước, confidence tăng dần (R-17)"


class DecisionRequest(BaseModel):
    action: Literal["approve", "reject", "edit", "supersede"]
    edits: dict[str, Any] | None = None      # cột op cho action=edit/supersede
    note: str | None = None


class DecisionOut(BaseModel):
    op_id: UUID
    action: str
    status: str
    actor: str
    new_op_id: UUID | None = None            # action=supersede → op mới (D-20)
    note: str | None = None


class BatchRequest(BaseModel):
    op_ids: list[UUID]
    invariant_template: dict[str, Any]
    description: str | None = None
    spot_check_rate: float = 0.1


class BatchVerifyOut(BaseModel):
    all_ok: bool
    results: list[dict[str, Any]]            # VerifyResult.as_dict()
    template_error: str | None = None


class SpotCheckItem(BaseModel):
    op_id: UUID
    source_quote: str | None = None
    target_path: str | None = None
    target_doc_key: str | None = None
    new_text: str | None = None


class BatchOut(BaseModel):
    batch_id: UUID
    approved_by: str
    ratified_count: int
    spot_check_rate: float
    spot_check: list[SpotCheckItem]
    verify: BatchVerifyOut
    description: str | None = None


# ---------------------------------------------------------------------------
# Admin: replay / backlog / conflicts / demand / notifications
# ---------------------------------------------------------------------------

class ReplayOut(BaseModel):
    status: Literal["ok", "stub"]
    run_id: UUID | None = None
    changed_nodes: list[dict[str, Any]] = Field(default_factory=list)
    certificates: list[dict[str, Any]] = Field(default_factory=list)
    guard_violations: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


class BacklogOut(BaseModel):
    counts: dict[str, int]
    consolidation_pending: list[dict[str, Any]] = Field(default_factory=list)
    oracle_mismatch: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_refs: list[dict[str, Any]] = Field(default_factory=list)
    pending_events: list[dict[str, Any]] = Field(default_factory=list)
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ConflictTriageRequest(BaseModel):
    status: Literal["open", "resolved", "dismissed", "accepted_risk"] | None = None
    fork: Literal["internal_internal", "internal_external", "external_external", "advisory"] | None = None
    label: Literal["mau_thuan", "chat_hon_ve_minh", "chat_hon_ve_doi_tac", "khac_pham_vi"] | None = None
    ticket_ref: str | None = None
    resolved_by_op: UUID | None = None


class ConflictCreateRequest(BaseModel):
    member_versions: list[dict[str, Any]]
    tier: Literal[1, 2, 3]
    reason: str
    label: str | None = None
    fork: str | None = None
    doctrine: dict[str, Any] | None = None
    ticket_ref: str | None = None


class DemandItem(BaseModel):
    question: str
    count: int
    audiences: list[str] = Field(default_factory=list)
    last_asked: datetime | None = None


class DemandOut(BaseModel):
    total_tier_d: int
    items: list[DemandItem]


class NotificationOut(BaseModel):
    id: UUID
    op_id: UUID | None = None
    affected_node: UUID | None = None
    affected_doc: str | None = None
    owner: str | None = None
    severity: str
    acked: bool
    created_at: datetime | None = None


class NotificationDigestOut(BaseModel):
    total: int
    unacked: int
    by_owner: dict[str, list[NotificationOut]]


class IngestOut(BaseModel):
    artifact_id: str
    doc_key: str
    created: bool                            # False = đã tồn tại (sha256 trùng)
    pipeline: Literal["f3", "stub"]
    proposed_ops: int = 0
    note: str | None = None


class FeedbackRequest(BaseModel):
    qa_id: UUID | None = None
    node_id: UUID | None = None
    kind: str = "nghi_da_cu"
    note: str | None = None


class FeedbackOut(BaseModel):
    id: UUID
    recorded: bool = True
