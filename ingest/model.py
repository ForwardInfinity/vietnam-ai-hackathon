"""model.py — dataclass nội bộ của pipeline ingest (pure, không DB).

Bundle là output của pipeline thuần: orchestrator persist nó vào DB đúng thứ tự
R-3; demo/tests dùng trực tiếp không cần Postgres. Birth-id (D-07) cấp client-side
bằng uuid4 ngay lúc dựng bundle để pure-pipeline == DB-pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

Level = Literal["preamble", "dieu", "khoan", "diem", "tiet", "phuluc"]

#: Các cấp đếm trong exit test R-4 (khớp corpus/manifest.json `counts`).
COUNT_LEVELS = ("dieu", "khoan", "diem", "tiet", "phuluc")


@dataclass
class ParsedNode:
    """Một node cây (đơn vị địa chỉ được: Điều/Khoản/Điểm/Tiết/Phụ lục — 02§1).
    `preamble` là node kỹ thuật chứa phần mở đầu + căn cứ (chỗ treo edge tham_quyen)."""
    level: Level
    label: str                       # '8', '1a', 'đ', 'iii', '04'
    path: str                        # 'dieu:8/khoan:2/diem:a' — địa chỉ LÚC SINH
    seq: int                         # thứ tự xuất hiện trong artifact (bẫy #17)
    heading: str | None = None       # Điều/Phụ lục có heading; có op CHỈ sửa heading
    body: str = ""                   # text CỦA CHÍNH node (không gồm con)
    parent_path: str | None = None
    chapter_ctx: list[str] = field(default_factory=list)  # stack heading Chương/Mục (omnibus §5.4)
    role: str = "rule"               # node_role_t — roles.py gán sau parse
    id: UUID = field(default_factory=uuid4)  # birth-id (D-07, INV-2)
    born_of_op: bool = False         # node do op insert TẠO lúc đề xuất (R-12)
    artifact_doc_key: str | None = None  # ≠ doc đang ingest khi born_of_op (target doc)

    @property
    def has_quote(self) -> bool:
        return "“" in self.body or '"' in self.body

    def full_text(self) -> str:
        return f"{self.heading}\n{self.body}".strip() if self.heading else self.body


@dataclass
class ParsedDoc:
    doc_key: str | None
    title: str | None
    issued_date: date | None
    effective_date: date | None
    nodes: list[ParsedNode]
    can_cu_lines: list[str] = field(default_factory=list)   # đoạn ^Căn cứ (R-8b)
    text: str = ""                                          # text đã normalize

    def counts(self) -> dict[str, int]:
        c = {lv: 0 for lv in COUNT_LEVELS}
        for n in self.nodes:
            if n.level in c and not n.born_of_op:
                c[n.level] += 1
        return c

    def node_at(self, path: str) -> ParsedNode | None:
        for n in self.nodes:
            if n.path == path:
                return n
        return None

    def children(self, path: str) -> list[ParsedNode]:
        return [n for n in self.nodes if n.parent_path == path]


@dataclass
class EdgeDraft:
    """Edge đề xuất (D-13). Cả 3 đích None = unresolved → backlog (R-10)."""
    src_path: str
    kind: str                        # edge_kind_t
    raw_citation: str
    src_node: UUID | None = None
    src_version: int = 1             # version đầu; F4 re-derive theo version sau replay
    dst_doc_key: str | None = None
    dst_path: str | None = None
    dst_node: UUID | None = None
    dst_norm: UUID | None = None
    frontier_ref: str | None = None
    resolved_against: date | None = None
    confidence: float = 1.0

    @property
    def resolved(self) -> bool:
        return any(x is not None for x in (self.dst_node, self.dst_norm, self.frontier_ref))


@dataclass
class ProposedOp:
    """Op đề xuất (R-11..R-14) — superset của api.schemas.ExtractedOp + kết quả resolve
    + quyết định router (R-15). Ghi DB với status='proposed' — KHÔNG BAO GIỜ tự ratify."""
    kind: str                        # op_kind_t (extractor không sinh close_window)
    source_quote: str
    seq: int
    source_path: str | None = None
    source_node: UUID | None = None
    target_surface: str | None = None
    target_doc_key: str | None = None
    target_path: str | None = None
    target_node: UUID | None = None
    target_op: UUID | None = None
    target_norm: UUID | None = None
    target_part: Literal["body", "heading"] = "body"
    new_text: str | None = None
    new_heading: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    valid_to_event: str | None = None
    scope_predicate: dict[str, Any] | None = None
    extractor: str = "rule"
    confidence: float = 0.9
    # ---- router / QA (R-13, R-15) ----
    risk_class: str | None = None            # 'definitional' | 'prescriptive'
    queue: str = "per_op"                    # 'per_op' | 'batch'
    red_flags: list[str] = field(default_factory=list)
    rule_llm_agree: bool = False
    target_unique: bool = False
    date_direct: bool = False                # ngày đọc thẳng (== effective_date văn bản)
    provenance_mentions: list[str] = field(default_factory=list)  # ngoặc "(đã được bổ sung theo …)"
    old_text: str | None = None              # body hiện tại của target (diff UI + machine-verify)
    phrase_from: str | None = None           # op thay-cụm-từ materialize (D-21/R-14)
    phrase_to: str | None = None
    id: UUID = field(default_factory=uuid4)
    notes: str | None = None

    @property
    def n_targets(self) -> int:
        return sum(x is not None for x in (self.target_node, self.target_op, self.target_norm))

    def check_ok(self) -> bool:
        """Mirror CHECK constraint của bảng op — chặn sớm trước khi INSERT."""
        if self.kind == "blanket_derogation":
            return self.n_targets == 0
        if self.n_targets != 1:
            return False
        if self.kind in ("amend", "insert", "dinh_chinh") \
                and self.new_text is None and self.new_heading is None:
            return False
        return True


@dataclass
class IngestBundle:
    """Kết quả pipeline thuần cho MỘT artifact — orchestrator persist theo thứ tự R-3."""
    doc: ParsedDoc
    meta: dict[str, Any]             # doc_key, doc_type, issuer, audience, is_oracle, …
    sha256: str
    nodes: list[ParsedNode] = field(default_factory=list)   # gồm cả node born_of_op
    aliases: list[tuple[str, str, UUID, date]] = field(default_factory=list)
    edges: list[EdgeDraft] = field(default_factory=list)
    ops: list[ProposedOp] = field(default_factory=list)

    @property
    def doc_key(self) -> str:
        return self.meta["doc_key"]
