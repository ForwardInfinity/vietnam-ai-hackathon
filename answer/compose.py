"""Context pack & composer (R-30, R-31).

- Mỗi node kèm header đầy đủ `[n] | doc_key | path | cửa sổ | status | scope |
  chuỗi sửa đổi` — verifier cứng đối chiếu trên đúng text đã cấp.
- Có ranh giới version/scope → đưa CẢ các nhánh, ép trả lời CÓ ĐIỀU KIỆN
  (không bao giờ chọn thầm — D-04/D-26).
- Composer qua gateway role=compose, output theo JSON contract ComposerOutput.
- Banner do CODE lắp từ flags, đúng thứ tự conflict > cohort_ambiguous >
  consolidation_pending > pending_change — model không thể bỏ/bịa.
- OfflineComposer: soạn tất định từ trích dẫn VERBATIM (demo/test không cần
  LLM; vẫn đi qua verifier cứng như mọi composer).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from api.schemas import (Banner, ComposerBasis, ComposerClaim, ComposerOutput,
                         CompiledQuestion, PiecewiseBlock)
from retrieval.query_builder import OpBrief, SnapshotRow, surface_of_path

# ---------------------------------------------------------------------------
# Context pack (R-30)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextEntry:
    ref: str                      # "[1]"
    row: SnapshotRow
    header: str
    branch_label: str | None = None   # nhãn nhánh khi node có ranh giới scope

    @property
    def full_text(self) -> str:
        return f"{self.header}\n{self.row.text}"


def format_interval(vf: date, vt: date | None) -> str:
    f = vf.strftime("%d/%m/%Y")
    return f"{f} → {vt.strftime('%d/%m/%Y')}" if vt else f"{f} → nay"


def scope_desc(scope: dict[str, Any] | None) -> str:
    if not scope:
        return "mọi chủ thể"
    parts = []
    if scope.get("contract_signed_before"):
        parts.append(f"HĐ ký trước {_dmy(scope['contract_signed_before'])}")
    if scope.get("not_amended_on_or_after"):
        parts.append(f"chưa sửa đổi, bổ sung từ {_dmy(scope['not_amended_on_or_after'])}")
    if scope.get("entity_class"):
        parts.append(f"chủ thể: {scope['entity_class']}")
    return ", ".join(parts) or "mọi chủ thể"


def _dmy(v: Any) -> str:
    d = v if isinstance(v, date) else date.fromisoformat(str(v))
    return d.strftime("%d/%m/%Y")


def citation_of(row: SnapshotRow) -> str:
    return f"{surface_of_path(row.path)} {row.doc_key}"


def provenance_vi(row: SnapshotRow, ops: dict[str, OpBrief]) -> str:
    """'khoản 8 Điều 8 39/2016/TT-NHNN — insert bởi 06/2023/TT-NHNN (01/09/2023),
    suspend bởi 10/2023/TT-NHNN (01/09/2023)' — node → chuỗi op → artifact gốc."""
    base = citation_of(row)
    chain = []
    _VI = {"amend": "sửa đổi", "insert": "bổ sung", "repeal": "bãi bỏ",
           "suspend": "ngưng hiệu lực", "dinh_chinh": "đính chính",
           "close_window": "đóng cửa sổ", "norm_decl": "kế vị norm",
           "blanket_derogation": "bãi bỏ chung"}
    for op_id in row.provenance:
        b = ops.get(op_id)
        if b:
            when = f" ({_dmy(b.valid_from)})" if b.valid_from else ""
            chain.append(f"{_VI.get(b.kind, b.kind)} bởi {b.source_doc_key}{when}")
    return base if not chain else f"{base} — {', '.join(chain)}"


def detect_branch_groups(rows: list[SnapshotRow]) -> dict[str, list[SnapshotRow]]:
    """node_id → các nhánh scope song song CÙNG hiệu lực (ranh giới scope D-04)."""
    by_node: dict[str, list[SnapshotRow]] = {}
    for r in rows:
        by_node.setdefault(r.node_id, []).append(r)
    return {nid: rs for nid, rs in by_node.items() if len({r.scope_hash for r in rs}) > 1}


def build_context_pack(rows: list[SnapshotRow], ops: dict[str, OpBrief] | None = None
                       ) -> list[ContextEntry]:
    ops = ops or {}
    branch_nodes = detect_branch_groups(rows)
    entries: list[ContextEntry] = []
    for i, r in enumerate(rows, start=1):
        label = None
        if r.node_id in branch_nodes:
            label = scope_desc(r.scope_predicate) if r.scope_predicate else "còn lại"
        header = (f"[{i}] {r.doc_key} | {r.path} ({surface_of_path(r.path)})"
                  f" | hiệu lực {format_interval(r.valid_from, r.valid_to)}"
                  f" | {r.status} | scope: {scope_desc(r.scope_predicate)}"
                  f" | {provenance_vi(r, ops)}")
        if label:
            header += f" | NHÁNH: {label}"
        entries.append(ContextEntry(ref=f"[{i}]", row=r, header=header, branch_label=label))
    return entries


# ---------------------------------------------------------------------------
# Composer protocol + 2 hiện thân
# ---------------------------------------------------------------------------

class Composer(Protocol):
    def compose(self, cq: CompiledQuestion, question: str, pack: list[ContextEntry],
                feedback: str | None = None) -> ComposerOutput: ...


COMPOSER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer_vi": {"type": "string"},
        "claims": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                           "refs": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "text", "refs"], "additionalProperties": False}},
        "bases": {"type": "array", "items": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "citation_vi": {"type": "string"},
                           "interval": {"type": "string"}},
            "required": ["ref", "citation_vi", "interval"], "additionalProperties": False}},
        "refusal": {"type": ["string", "null"]},
    },
    "required": ["answer_vi", "claims", "bases", "refusal"],
    "additionalProperties": False,
}

_SYSTEM_COMPOSE = """Anh là trợ lý pháp quy của ngân hàng, soạn câu trả lời CHỈ từ các trích đoạn được cấp.
LUẬT CỨNG (vi phạm = câu trả lời bị hủy bởi verifier):
1. CHỈ dùng nội dung trong các mục [n] được cấp — không kiến thức ngoài, không suy diễn thêm nghĩa vụ.
2. Mọi câu quy phạm trong answer_vi phải mang ít nhất một tag [n] trỏ đúng mục nguồn.
3. Con số, ngưỡng, tỷ lệ, thời hạn: chép VERBATIM từ nguồn — không làm tròn, không quy đổi.
4. Đoạn đặt trong ngoặc kép phải là trích NGUYÊN VĂN từ nguồn.
5. Nếu context có nhiều NHÁNH (theo cửa sổ hiệu lực hoặc theo lớp chủ thể/scope):
   trả lời CÓ ĐIỀU KIỆN theo TỪNG nhánh, nêu rõ điều kiện — KHÔNG BAO GIỜ tự chọn một nhánh.
6. Thiếu căn cứ để trả lời câu hỏi → điền refusal (ngắn gọn vì sao), answer_vi để trống — không độn văn.
7. Trả lời tiếng Việt, ngắn gọn, có cấu trúc."""

_CUSTOMER_TONE = """
8. Người đọc là KHÁCH HÀNG phổ thông: dùng lời dễ hiểu, tránh biệt ngữ nghiệp vụ;
   không nhắc tài liệu nội bộ; vẫn giữ tag [n] và số liệu verbatim."""


class GatewayComposer:
    """Composer qua LLM gateway (role=compose) — một họ với extractor (D-41)."""

    def __init__(self, gateway=None):
        if gateway is None:
            from answer.llm_gateway import get_gateway
            gateway = get_gateway()
        self._gw = gateway

    def compose(self, cq, question, pack, feedback=None):
        system = _SYSTEM_COMPOSE + (_CUSTOMER_TONE if cq.audience == "customer" else "")
        lines = [f"Câu hỏi: {question}",
                 f"Trả lời theo trạng thái văn bản tại ngày (as_of): {cq.as_of.isoformat()}",
                 f"Cohort đã biết: {cq.cohort.model_dump(exclude_none=True) or 'chưa rõ'}",
                 "", "NGUỒN ĐƯỢC CẤP:"]
        for e in pack:
            lines.append(e.full_text)
            lines.append("")
        if feedback:
            lines.append(f"LẦN TRƯỚC BỊ VERIFIER TỪ CHỐI: {feedback}\nSửa đúng các lỗi đó.")
        out = self._gw.complete_json("compose", system, "\n".join(lines), COMPOSER_SCHEMA)
        return ComposerOutput.model_validate(out)


class OfflineComposer:
    """Composer tất định không-LLM: mỗi nguồn chính → một claim trích NGUYÊN VĂN.

    Dùng cho demo/test khi không có key. Trung thực theo INV: chỉ verbatim từ
    snapshot, vẫn bị verifier cứng soát như mọi composer."""

    def __init__(self, max_claims: int = 4, quote_chars: int = 320):
        self._max_claims = max_claims
        self._quote_chars = quote_chars

    @staticmethod
    def _cut(text: str, limit: int) -> str:
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        cut = text[:limit]
        return cut[: cut.rfind(" ")] if " " in cut else cut

    def compose(self, cq, question, pack, feedback=None):
        if not pack:
            return ComposerOutput(answer_vi="", claims=[], bases=[],
                                  refusal="Không có căn cứ trong phạm vi được cấp.")
        # giữ thứ tự relevance của pack; nếu một nhánh của node được chọn thì kéo
        # đỦ các nhánh anh em (không bao giờ trả lời một nửa ranh giới scope — D-04)
        chosen = list(pack[: self._max_claims])
        have = {e.ref for e in chosen}
        chosen_nodes = {e.row.node_id for e in chosen}
        for e in pack:
            if e.branch_label and e.ref not in have and e.row.node_id in chosen_nodes:
                chosen.append(e)
                have.add(e.ref)
        claims, parts = [], []
        for e in chosen:
            quote = self._cut(e.row.text, self._quote_chars)
            cond = f"Trường hợp {e.branch_label}: " if e.branch_label else ""
            claims.append(ComposerClaim(id=f"c{len(claims)+1}",
                                        text=f'{cond}"{quote}" {e.ref}',
                                        refs=[e.ref]))
            parts.append(f"- {cond}Theo {citation_of(e.row)} {e.ref}: \"{quote}\"")
        bases = [ComposerBasis(ref=e.ref, citation_vi=citation_of(e.row),
                               interval=format_interval(e.row.valid_from, e.row.valid_to))
                 for e in chosen]
        return ComposerOutput(answer_vi="\n".join(parts), claims=claims, bases=bases,
                              refusal=None)


# ---------------------------------------------------------------------------
# Banner — CODE lắp từ flags, model không thể bỏ/bịa (R-31)
# ---------------------------------------------------------------------------

FLAG_BANNER_ORDER = ("in_conflict", "cohort_ambiguous", "consolidation_pending",
                     "pending_change", "open_suspension")

_BANNER_TEXT = {
    "in_conflict": "⚠ Câu trả lời chạm vùng XUNG ĐỘT quy phạm đang mở — xem mục Xung đột; hệ không tự phân xử.",
    "cohort_ambiguous": "Câu trả lời PHÂN NHÁNH theo lớp chủ thể/thời điểm ký hợp đồng — thiếu dữ kiện cohort nên trả lời piecewise, không chọn thầm một nhánh.",
    "consolidation_pending": "Có thay đổi đã đến hạn hiệu lực nhưng CHƯA được phê chuẩn vào trạng thái — nội dung dưới đây có thể chưa hợp nhất đủ.",
    "pending_change": "Có thay đổi SẮP HIỆU LỰC chạm các điều khoản trong câu trả lời — xem mục Thay đổi sắp hiệu lực.",
    "open_suspension": "Điều khoản liên quan đang NGƯNG HIỆU LỰC chờ sự kiện đóng (văn bản QPPL mới).",
}

JUDGE_BANNER = Banner(kind="judge_uncalibrated",
                      text_vi="Kiểm chứng ngữ nghĩa (judge) chưa hiệu chuẩn κ≥0.8 — trần Tier B.")
CUSTOMER_DISCLAIMER = Banner(kind="disclaimer",
                             text_vi="Thông tin mang tính tham khảo theo văn bản công khai, "
                                     "không phải tư vấn pháp lý; vui lòng liên hệ ngân hàng để được hỗ trợ chính thức.")


def assemble_banners(flags: set[str], judge_capped: bool, audience: str,
                     clarify_question: str | None = None) -> list[Banner]:
    banners = [Banner(kind=f, text_vi=_BANNER_TEXT[f])
               for f in FLAG_BANNER_ORDER if f in flags]
    if judge_capped:
        banners.append(JUDGE_BANNER)
    if clarify_question and audience == "employee":
        banners.append(Banner(kind="clarify", text_vi=f"Để trả lời đúng một nhánh: {clarify_question}"))
    if audience == "customer":
        banners.append(CUSTOMER_DISCLAIMER)
    return banners


def clarify_question_for(branch_groups: dict[str, list[SnapshotRow]]) -> str | None:
    """Đúng MỘT câu hỏi lại (R-27) từ ranh giới scope đầu tiên."""
    for rows in branch_groups.values():
        for r in rows:
            sp = r.scope_predicate or {}
            if sp.get("contract_signed_before"):
                return (f"Hợp đồng được ký trước {_dmy(sp['contract_signed_before'])} "
                        f"và chưa sửa đổi, bổ sung từ ngày đó phải không?")
            if sp.get("entity_class"):
                return f"Khách hàng thuộc nhóm '{sp['entity_class']}' phải không?"
    return None


# ---------------------------------------------------------------------------
# Piecewise blocks (00-VISION §3): (khoảng thời gian × lớp chủ thể)
# ---------------------------------------------------------------------------

def build_piecewise_blocks(out: ComposerOutput, pack: list[ContextEntry]) -> list[PiecewiseBlock]:
    by_ref = {e.ref: e for e in pack}
    branch_claims: dict[str, list[ComposerClaim]] = {}
    plain_claims: list[ComposerClaim] = []
    for c in out.claims:
        entry = next((by_ref[r] for r in c.refs if r in by_ref and by_ref[r].branch_label), None)
        if entry is not None:
            branch_claims.setdefault(entry.ref, []).append(c)
        else:
            plain_claims.append(c)

    if not branch_claims:  # không ranh giới → một khối duy nhất
        first = by_ref.get(next(iter(out.claims[0].refs), ""), None) if out.claims else None
        return [PiecewiseBlock(
            interval_from=first.row.valid_from if first else None,
            interval_to=first.row.valid_to if first else None,
            cohort=None, text_vi=out.answer_vi)]

    # nhánh scope render TRÊN phần chung (ngoại lệ/điều kiện lên trước — 00-VISION §5)
    blocks: list[PiecewiseBlock] = []
    for ref, claims in branch_claims.items():
        e = by_ref[ref]
        blocks.append(PiecewiseBlock(
            interval_from=e.row.valid_from, interval_to=e.row.valid_to,
            cohort=e.branch_label, text_vi="\n".join(c.text for c in claims)))
    if plain_claims:
        blocks.append(PiecewiseBlock(cohort=None,
                                     text_vi="\n".join(c.text for c in plain_claims)))
    return blocks
