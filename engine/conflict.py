"""Doctrine ưu tiên & xung đột (02 §6, D-15, D-33, D-34, D-35).

- Precedence là BẢNG CÓ CỬA SỔ, tham số hóa (D-15): fold nhận rows; default dưới đây
  encode Đ156 Luật BHVBQPPL 2015 (rank nhỏ = hiệu lực pháp lý cao).
- Tier-1 tự động CHỈ quy tắc đã luật hóa: cấp trên thắng; SAU-thắng CHỈ khi CÙNG cơ quan.
- Không phân định → incomparable → ConflictCertificate (unsat-core), KHÔNG chọn bừa.
- Nhãn so sánh nội quy vs pháp quy (D-34): chat_hon_ve_minh = tuân thủ → TỰ LOẠI;
  khac_pham_vi → loại; mau_thuan / chat_hon_ve_doi_tac → vào queue người.
- Ownership fork theo cặp issuer (D-35).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Sequence
from uuid import UUID

from engine.model import ConflictCertificate, sv

DEFAULT_RANK = 99

# (doc_type, issuer, rank) — hierarchy 02 §6.1; hàng None = wildcard chiều đó.
_DEFAULT_RANKS: list[tuple[str | None, str | None, int]] = [
    ("hien_phap", None, 1),
    ("luat", None, 2), ("nghi_quyet", "QH", 2),
    ("phap_lenh", None, 3), ("nghi_quyet", "UBTVQH", 3),
    ("lenh", None, 4), ("quyet_dinh", "CTN", 4),
    ("nghi_dinh", None, 5),
    ("quyet_dinh", "TTg", 6),
    ("thong_tu", None, 7),
    ("nghi_quyet", "HDTP", 8),      # diễn giải áp dụng pháp luật của TANDTC
    ("quyet_dinh", None, 9),
    ("cong_van", None, 30),         # diễn giải có nguồn, không phải quy phạm (02 §6.3)
    ("noi_bo", None, 40), ("bieu_mau", None, 41),
    (None, "SHB", 40),
]


class _PrecRow:
    __slots__ = ("doc_type", "issuer", "rank", "valid_from", "valid_to", "source_node")

    def __init__(self, doc_type, issuer, rank, valid_from=None, valid_to=None, source_node=None):
        self.doc_type, self.issuer, self.rank = doc_type, issuer, rank
        self.valid_from, self.valid_to, self.source_node = valid_from, valid_to, source_node


def default_precedence() -> list[Any]:
    """Bảng mặc định, cửa sổ mở — production phải nạp statement CÓ NGUỒN vào bảng `precedence`."""
    return [_PrecRow(dt, iss, r) for dt, iss, r in _DEFAULT_RANKS]


def _issuer_match(row_issuer: str | None, issuer: str) -> bool:
    if row_issuer is None:
        return True
    return issuer == row_issuer or issuer.startswith(row_issuer + ".")


def precedence_rank(doc_type: str, issuer: str, at: date | None, rows: Sequence[Any],
                    default: int = DEFAULT_RANK) -> int:
    """Rank tại thời điểm `at` (bảng có cửa sổ, D-15); match cụ thể nhất thắng."""
    best: tuple[int, int] | None = None       # (-specificity, rank)
    for r in rows:
        if r.doc_type is not None and r.doc_type != doc_type:
            continue
        if not _issuer_match(r.issuer, issuer):
            continue
        if at is not None:
            if r.valid_from is not None and at < r.valid_from:
                continue
            if r.valid_to is not None and at >= r.valid_to:
                continue
        spec = (r.doc_type is not None) + (r.issuer is not None)
        cand = (-spec, r.rank)
        if best is None or cand < best:
            best = cand
    return best[1] if best else default


def winning_op(
    candidates: Sequence[Any], artifacts: dict[str, Any], precedence: Sequence[Any],
) -> tuple[Any | None, list[Any], dict[UUID, int]]:
    """Chọn op thắng trong nhóm op CÙNG đặt text trên MỘT phân đoạn (đã sort canonical D-23).

    → (winner, incomparable_group, ranks). winner=None ⟺ incomparable (same-rank khác cơ quan).
    Tier-1: rank nhỏ nhất thắng; trong nhóm rank bằng + cùng cơ quan: phần tử CUỐI theo thứ tự
    canonical = lex posterior (valid_from, issued_date, seq — bẫy 7 & 17 của 02 §7)."""
    ranks = {o.id: precedence_rank(artifacts[o.source_artifact].doc_type,
                                   artifacts[o.source_artifact].issuer,
                                   o.valid_from, precedence)
             for o in candidates}
    if len(candidates) == 1:
        return candidates[0], [], ranks
    top_rank = min(ranks[o.id] for o in candidates)
    top = [o for o in candidates if ranks[o.id] == top_rank]
    if len(top) == 1:
        return top[0], [], ranks
    issuers = {artifacts[o.source_artifact].issuer for o in top}
    if len(issuers) > 1:
        return None, top, ranks
    return top[-1], [], ranks


def certificate_for(node_id: UUID, group: Sequence[Any], ranks: dict[UUID, int],
                    artifacts: dict[str, Any], window: tuple[date, date | None],
                    ) -> ConflictCertificate:
    a, b = group[0], group[1]
    docs = ", ".join(f"{artifacts[o.source_artifact].doc_key}#op{o.seq}" for o in group)
    return ConflictCertificate(
        node_id=node_id,
        member_ops=tuple(o.id for o in group),
        window_from=window[0], window_to=window[1],
        reason=(f"Chồng cửa sổ hiệu lực trên cùng node giữa {docs}; cùng hạng "
                f"({ranks[a.id]}) nhưng KHÁC cơ quan ban hành — Đ156 không phân định, "
                f"máy không tự chọn (D-33 tier-2)."),
        doctrine={"rank_a": ranks[a.id], "rank_b": ranks[b.id],
                  "same_issuer": False, "art156": "khong_phan_dinh"},
        tier=2,
    )


# ---------------------------------------------------------------------------
# D-34: nhãn so sánh nội quy ↔ pháp quy (pair-proposer offline gán trước khi vào queue)
# ---------------------------------------------------------------------------

DROP_LABELS = {"chat_hon_ve_minh", "khac_pham_vi"}       # 02 §6.4: tự loại / loại
QUEUE_LABELS = {"mau_thuan", "chat_hon_ve_doi_tac"}


def label_pair(internal_text: str, external_text: str,
               llm: Callable[[dict], dict] | None = None) -> str | None:
    """Gán nhãn D-34 cho một cặp (nội quy, pháp quy). → None = TỰ LOẠI khỏi queue.

    `llm`: callable offline (pair-proposer, R-25) trả {"label": cfl_label_t, ...} —
    test inject fake; production wrap qua answer.llm_gateway (make_gateway_labeler)."""
    label = None
    if llm is not None:
        label = sv((llm({"internal": internal_text, "external": external_text}) or {}).get("label"))
    if label is None:
        label = "mau_thuan"                               # rule fallback bảo thủ: đưa người xét
    if label in DROP_LABELS:
        return None
    if label not in QUEUE_LABELS:
        raise ValueError(f"nhãn D-34 không hợp lệ: {label}")
    return label


def make_gateway_labeler() -> Callable[[dict], dict]:
    """Wrap LLM gateway (D-41) thành pair-proposer offline; import lười, không bắt buộc."""
    from answer.llm_gateway import get_gateway              # noqa: PLC0415

    schema = {"type": "object",
              "properties": {"label": {"enum": sorted(DROP_LABELS | QUEUE_LABELS)},
                             "rationale": {"type": "string"}},
              "required": ["label"]}

    def _call(payload: dict) -> dict:
        return get_gateway().complete_json(
            role="extract",
            system=("Gán nhãn quan hệ giữa quy định nội bộ ngân hàng và quy phạm pháp luật "
                    "(D-34). chat_hon_ve_minh = nội quy siết nghĩa vụ CỦA ngân hàng (tuân thủ); "
                    "chat_hon_ve_doi_tac = siết yêu cầu VỚI khách hàng (nghi vấn); "
                    "mau_thuan = trái nghĩa vụ/quyền; khac_pham_vi = scope không giao."),
            user=f"NỘI BỘ:\n{payload['internal']}\n\nPHÁP QUY:\n{payload['external']}",
            schema=schema)

    return _call


def fork_for(issuer_a: str, issuer_b: str, frontier: bool = False) -> str:
    """Ownership fork trên certificate/notice (D-35)."""
    if frontier:
        return "advisory"
    a_int = issuer_a == "SHB" or issuer_a.startswith("SHB.")
    b_int = issuer_b == "SHB" or issuer_b.startswith("SHB.")
    if a_int and b_int:
        return "internal_internal"
    if a_int or b_int:
        return "internal_external"
    return "external_external"
