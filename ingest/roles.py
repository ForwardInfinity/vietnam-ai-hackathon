"""roles.py — gán node_role rule-based (R-3, R-5; bẫy #14).

Quy tắc amending theo ĐÚNG chữ R-3: "node chứa động-từ-hiệu-lực + QUOTE" —
node mang mệnh lệnh sửa đổi VÀ (chính nó hoặc cây con) chứa text được quote.
Hệ quả (khớp ground truth corpus):
  - TT10 Đ1 "Ngưng hiệu lực…" KHÔNG quote → KHÔNG amending (không có text để
    contaminate; nội dung sống qua op; node retrievable).
  - Điều container "Sửa đổi, bổ sung MỘT SỐ ĐIỀU của <doc>" có con → KHÔNG amending
    (các khoản con mang quote mới là amending).
  - Điều khoản chuyển tiếp/hiệu lực của văn bản sửa đổi KHÔNG amending (bẫy #14) —
    NHƯNG con của điều hiệu lực vẫn có thể amending nếu tự mang mệnh lệnh + quote
    (TT22 Đ24 k2 sửa Đ23 TT41 nằm trong điều "Hiệu lực thi hành").
Con của node amending/definition/form kế thừa role cha (text quote nằm ở con).
"""
from __future__ import annotations

import re

from ingest.model import ParsedDoc, ParsedNode

RE_DEFINITION = re.compile(r"giải thích (từ ngữ|thuật ngữ)", re.IGNORECASE)
RE_TRANSITION = re.compile(r"(điều khoản|quy định)\s+chuyển tiếp", re.IGNORECASE)
RE_EFFECTIVITY = re.compile(
    r"^(hiệu lực( thi hành)?|điều khoản thi hành|hiệu lực và trách nhiệm thi hành|"
    r"hiệu lực thi hành và tổ chức thực hiện)\s*\.?$", re.IGNORECASE)
RE_SCOPE = re.compile(r"^(phạm vi điều chỉnh|đối tượng áp dụng|phạm vi điều chỉnh và đối tượng áp dụng)\s*\.?$",
                      re.IGNORECASE)

# Động từ hiệu lực mở đầu mệnh lệnh sửa đổi (bảng 02§3). 'đính chính' KHÔNG ở đây:
# node đính chính quote CỤM TỪ lỗi in, không phải norm text — không contaminate
# (khớp quy ước manifest F2); op vẫn được extract bình thường (R-11 quét mọi node).
_VERB = (r"(?:sửa đổi, bổ sung|sửa đổi|bổ sung|bãi bỏ|thay thế|ngưng hiệu lực"
         r"|thay đổi)")
_UNIT = (r"(?:điều|khoản|điểm|tiết|phụ lục|mục|chương|tên điều|cụm từ|đoạn"
         r"|thông tư|nghị định|luật|quyết định|nghị quyết|một số điều)")
RE_AMEND_IMPERATIVE = re.compile(
    rf"^{_VERB}\s+(?:một số điều|một đoạn|một số|một|các|tên)?\s*{_UNIT}", re.IGNORECASE)
RE_AMEND_VERB_UNIT = re.compile(
    rf"{_VERB}\s+(?:các\s+|một số\s+|một\s+)?{_UNIT}", re.IGNORECASE)
RE_CONTAINER_HEADING = re.compile(
    r"^Sửa đổi, bổ sung một số điều(?:\s+của|\s+và|\s+các)", re.IGNORECASE)


def _heading_role(heading: str | None) -> str | None:
    if not heading:
        return None
    h = heading.strip().rstrip(".").strip()
    if RE_DEFINITION.search(h):
        return "definition"
    if RE_TRANSITION.search(h):
        return "transition"
    if RE_EFFECTIVITY.match(h):
        return "effectivity"
    if RE_SCOPE.match(h):
        return "scope"
    return None


def _has_amend_directive(node: ParsedNode) -> bool:
    head = (node.heading or "").strip()
    body_start = node.body.strip()
    # văn bản/điều đính chính: quote là cụm từ lỗi in, không phải norm — không amending
    if re.match(r"^Đính chính\b", head, re.IGNORECASE) \
            or re.match(r"^Đính chính\b", body_start, re.IGNORECASE):
        return False
    if RE_AMEND_IMPERATIVE.match(head) or RE_AMEND_IMPERATIVE.match(body_start):
        return True
    return bool(RE_AMEND_VERB_UNIT.search(node.full_text()))


def _quote_in_own_text(node: ParsedNode) -> bool:
    return "“" in node.full_text()


def assign_roles(doc: ParsedDoc, doc_type: str = "thong_tu") -> None:
    """Gán role in-place cho doc.nodes. Idempotent."""
    children: dict[str | None, list[ParsedNode]] = {}
    for n in doc.nodes:
        children.setdefault(n.parent_path, []).append(n)

    subtree_quote: dict[str, bool] = {}

    def compute_quote(n: ParsedNode) -> bool:
        if n.path in subtree_quote:
            return subtree_quote[n.path]
        val = _quote_in_own_text(n) or any(compute_quote(c) for c in children.get(n.path, []))
        subtree_quote[n.path] = val
        return val

    role_by_path: dict[str, str] = {}
    for node in doc.nodes:
        if node.level == "phuluc":
            node.role = "form" if doc_type == "bieu_mau" else "appendix"
            role_by_path[node.path] = node.role
            continue
        if doc_type == "bieu_mau":
            node.role = "form"
            role_by_path[node.path] = "form"
            continue
        if node.level == "preamble":
            node.role = "rule"
            continue

        parent_role = role_by_path.get(node.parent_path or "")

        # kế thừa cứng: definition/amending/form (text quote sống ở con node amending)
        if parent_role in ("definition", "amending", "form"):
            node.role = parent_role
            role_by_path[node.path] = parent_role
            continue

        # amending: mệnh lệnh sửa đổi + quote trong cây con; container "một số điều" loại
        is_container = (bool(RE_CONTAINER_HEADING.match((node.heading or "").strip()))
                        and bool(children.get(node.path)))
        if not is_container and _has_amend_directive(node) and compute_quote(node):
            node.role = "amending"
            role_by_path[node.path] = "amending"
            continue

        hr = _heading_role(node.heading)
        if hr:
            # bẫy #14: heading chuyển tiếp/hiệu lực thắng scan động từ trong body
            node.role = hr
            role_by_path[node.path] = hr
            continue

        if parent_role in ("transition", "effectivity", "scope"):
            node.role = parent_role
            role_by_path[node.path] = parent_role
            continue

        node.role = "rule"
        role_by_path[node.path] = "rule"
