"""op_extract.py — trích op 2 tầng (R-11..R-14, D-18; bảng động từ 02§3).

Tầng RULE: quét động từ hiệu lực trên MỌI node (kể cả "Điều khoản thi hành" — op hay
nấp ở đó); ngôn ngữ sửa đổi VN gần công thức nên rule là xương sống tất định.
Tầng LLM: JSON-schema (ExtractedOp, source_quote BẮT BUỘC), few-shot BẮT BUỘC có:
tách enumeration; `ngưng hiệu lực` ≠ `bãi bỏ` (TT10); binding "Thông tư này"
trong/ngoài quote; hiệu lực phân kỳ theo chủ đề; không đoán target (unknown→null).

Resolver: surface→node qua alias tại ngày văn bản nguồn; target là node `amending`
→ chuyển target_op (R-12); op insert TẠO node đích (birth-id) ngay lúc đề xuất;
cross-validation ngoặc provenance (R-13) lệch → cờ đỏ; thay-cụm-từ → materialize
danh sách op amend node-level cho curator (R-14/D-21).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from api.schemas import ExtractedOp, ExtractionResult
from ingest.model import ParsedDoc, ParsedNode, ProposedOp
from ingest.surface import LEVEL_RANK, RE_DOCNO, RefGroup, extract_docno, parse_surface
from ingest.tree_parser import RE_DIEU, RE_DIEM, RE_KHOAN, parse_vn_date, strip_quoted_new_text

logger = logging.getLogger("lawstate.ingest.op_extract")

# --- cụm từ kích hoạt (02§3) --------------------------------------------------

RE_AMEND = re.compile(
    r"(?:Sửa đổi, bổ sung|Sửa đổi)\s+(?:tên\s+)?(?!.{0,30}vào\s)([^:“\n]{2,300}?)\s*(?:như sau\s*:|(?=\s*\n\s*“))",
    re.IGNORECASE)
RE_AMENDED_AS = re.compile(          # "khoản 2 Điều 8 được sửa đổi(, bổ sung)? như sau:"
    r"([^:“\n.;]{2,160}?)\s+được sửa đổi(?:, bổ sung)?\s+như sau\s*:", re.IGNORECASE)
RE_INSERT = re.compile(
    r"Bổ sung\s+([^:“\n]{2,200}?)\s*(?:như sau\s*:|:\s*$|:\s*“)", re.IGNORECASE)
RE_REPEAL = re.compile(r"Bãi bỏ\s+([^.;“\n]{2,220})", re.IGNORECASE)
RE_HET_HIEU_LUC = re.compile(r"hết hiệu lực(?:\s+thi hành)?", re.IGNORECASE)
RE_SUSPEND = re.compile(r"Ngưng hiệu lực thi hành\s+([^;\n]{2,400})", re.IGNORECASE)
RE_PHRASE = re.compile(
    r"[Tt]hay thế cụm từ\s+[“\"]([^”\"]+)[”\"]\s+bằng\s+(?:cụm từ\s+)?[“\"]([^”\"]+)[”\"]"
    r"(?:\s+tại\s+([^.;\n]{2,220}))?")
RE_DINH_CHINH = re.compile(r"[Đđ]ính chính\s+([^.;\n]{2,240})")
RE_NORM_DECL = re.compile(
    r"(?:thay thế|Thông tư này thay thế|Luật này thay thế)\s+"
    r"((?:Thông tư|Nghị định|Luật|Bộ luật|Quyết định|Nghị quyết)[^.;\n]{0,120})", re.IGNORECASE)
RE_BLANKET = re.compile(
    r"(?:mọi|các)\s+quy định(?:\s+trước đây)?\s+trái với\s+(?:Thông tư|Nghị định|Luật|"
    r"Quyết định|Nghị quyết)\s+này[^.;\n]{0,80}?(?:hết|không còn)\s+hiệu lực", re.IGNORECASE)
RE_VALID_FROM = re.compile(r"(?:kể\s+)?từ\s+ngày\s+([^,;.]{4,60})")
RE_VALID_TO = re.compile(
    r"(?:cho\s+)?đến\s+(?:hết\s+)?ngày\s+([^;.]{2,240}?)(?=\s+đối với\b|\s*[;.]|$)",
    re.IGNORECASE)
RE_PROVENANCE_PAREN = re.compile(     # "(đã được bổ sung theo khoản 2 Điều 1 Thông tư số …)"
    r"\(\s*(?:đã\s+)?được\s+(?:sửa đổi|bổ sung|sửa đổi, bổ sung)[^)]{0,400}?"
    r"(?:theo|tại|bởi)\s+([^)]{4,400})\)", re.IGNORECASE)
RE_PROVENANCE_INLINE = re.compile(    # "Điều 32g TT39 đã được sửa đổi, bổ sung bởi khoản 11 Điều 1 TT06"
    r"(?:đã\s+)?được\s+(?:sửa đổi, bổ sung|sửa đổi|bổ sung)(?:\s+một số điều)?\s+"
    r"(?:theo|bởi|tại)\s+((?:các\s+)?(?:khoản|điểm|Điều|Thông tư|Luật|Nghị định|Nghị quyết|Quyết định)"
    r"[^;.\n“()]{0,200})", re.IGNORECASE)
RE_LIST_SUBJECT = re.compile(r"các\s+(?:văn bản|quy định|thông tư|điều khoản)[^:.;]{0,30}sau(?:\s+đây)?",
                             re.IGNORECASE)
RE_SUCCESSION_CUE = re.compile(
    r"kể từ ngày\s+(?:Thông tư|Luật|Bộ luật|Nghị định|Quyết định|Nghị quyết)\s+này có hiệu lực"
    r"|hiệu lực thi hành,\s*các văn bản sau", re.IGNORECASE)
RE_DA_IN = re.compile(r"đã in là\s*:?\s*[“\"]([^”\"]+)[”\"]", re.IGNORECASE)
RE_SUA_LAI = re.compile(r"(?:[Nn]ay\s+)?(?:đính chính thành|sửa lại là)\s*:?\s*[“\"]([^”\"]+)[”\"]",
                        re.IGNORECASE)

_QUOTE_OPEN = ("“", '"')


@dataclass
class ExtractionContext:
    doc_key: str
    issued_date: date | None
    effective_date: date | None
    store: Any
    doc: ParsedDoc
    scope_predicate: dict[str, Any] | None = None    # grandfather carve-out từ điều chuyển tiếp
    extra_dates: dict[str, date] = field(default_factory=dict)  # hiệu lực phân kỳ đã phát hiện


# ============================================================================
# helpers
# ============================================================================

def find_quote_block(text: str, from_pos: int) -> tuple[str, int, int] | None:
    """Khối “…” (hoặc "…") đầu tiên sau from_pos, depth-aware với ngoặc cong."""
    i = from_pos
    n = len(text)
    while i < n and text[i] not in "“\"":
        i += 1
    if i >= n:
        return None
    if text[i] == "“":
        depth, j = 1, i + 1
        while j < n and depth > 0:
            if text[j] == "“":
                depth += 1
            elif text[j] == "”":
                depth -= 1
            j += 1
        return text[i:j], i, j
    j = text.find('"', i + 1)
    if j == -1:
        return None
    return text[i:j + 1], i, j + 1


def split_quoted_units(block: str) -> list[tuple[str, str, str]]:
    """Tách khối quote chứa NHIỀU đơn vị: '8. …\n9. …' → [(level,label,text)…].
    Tách enumeration là bắt buộc (02§5.1). Chỉ tách ở CẤP CỦA MARKER ĐẦU TIÊN —
    marker sâu hơn (điểm trong khoản 10 TT06) ở lại trong text của đơn vị cha;
    khối thay toàn bộ Điều giữ nguyên con (D-08 — engine tái cấu trúc khi apply)."""
    inner = strip_quoted_new_text(block)
    lines = inner.split("\n")
    top: str | None = None
    for ln in lines:
        s = ln.strip()
        if RE_DIEU.match(s):
            top = "dieu"
            break
        if RE_KHOAN.match(s):
            top = "khoan"
            break
        if RE_DIEM.match(s):
            top = "diem"
            break
    if top is None:
        return [("", "", inner)]
    matcher = {"dieu": RE_DIEU, "khoan": RE_KHOAN, "diem": RE_DIEM}[top]
    units: list[tuple[str, str, str]] = []
    cur: tuple[str, str] | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, cur
        if cur is not None:
            units.append((cur[0], cur[1], "\n".join(buf).strip()))
        buf = []

    for ln in lines:
        s = ln.strip()
        m = matcher.match(s)
        if m:
            flush()
            cur = (top, m.group(1).lower())
            buf = [s]
        else:
            buf.append(s)
    flush()
    return units or [("", "", inner)]


def _strip_unit_marker(text: str, level: str, label: str) -> tuple[str | None, str]:
    """'8. Để gửi tiền.' → (None, 'Để gửi tiền.'); 'Điều 7a. Tên\nbody' → ('Tên', body)."""
    first, _, rest = text.partition("\n")
    if level == "dieu":
        m = RE_DIEU.match(first.strip())
        if m:
            return (m.group(2).strip().rstrip(".") or None, rest.strip())
        return None, text
    m = RE_KHOAN.match(first.strip()) or RE_DIEM.match(first.strip())
    if m:
        return None, (m.group(2).strip() + ("\n" + rest.strip() if rest.strip() else "")).strip()
    return None, text


def _dates_from_sentence(sent: str, ctx: ExtractionContext) \
        -> tuple[date | None, date | None, str | None]:
    """(valid_from, valid_to, valid_to_event) đọc từ chính câu op; thiếu valid_from →
    hiệu lực chung văn bản. 'đến ngày <sự kiện chưa định danh>' → valid_to_event (D-11)."""
    vf = None
    m = RE_VALID_FROM.search(sent)
    if m:
        vf = parse_vn_date("ngày " + m.group(1))
    vto: date | None = None
    ev: str | None = None
    m = RE_VALID_TO.search(sent)
    if m:
        candidate = m.group(1).strip()
        d = parse_vn_date("ngày " + candidate)
        if d is not None:
            vto = d
        elif re.search(r"có hiệu lực|văn bản|ban hành", candidate, re.IGNORECASE):
            ev = "đến ngày " + candidate
    return vf or ctx.effective_date, vto, ev


def _sentence_at(text: str, pos: int) -> str:
    start = max(text.rfind("\n", 0, pos), text.rfind(". ", 0, pos))
    start = 0 if start < 0 else start + 1
    end_candidates = [i for i in (text.find(";", pos), text.find("\n", pos)) if i != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip()


# ============================================================================
# Tầng RULE (R-11) — quét MỌI node
# ============================================================================

def rule_extract(ctx: ExtractionContext) -> list[ProposedOp]:
    ops: list[ProposedOp] = []
    seq = 0
    has_dieu = any(n.level == "dieu" for n in ctx.doc.nodes)
    for node in ctx.doc.nodes:
        if node.level == "preamble" and has_dieu:
            # preamble của văn bản có Điều: chỉ quét đính chính (công văn đính chính
            # không có Điều — toàn bộ nằm preamble thì quét đủ như node thường)
            seq = _scan_dinh_chinh(node, node.full_text(), ctx, ops, seq, taken=[])
            continue
        text = node.full_text()
        seq = _rule_scan_node(node, text, ctx, ops, seq)
    return ops


def _children_are_directives(node: ParsedNode, ctx: ExtractionContext) -> bool:
    """Khoản cha kiểu TT06 k6: directive tổng + các điểm con tự mang mệnh lệnh + quote
    — cha KHÔNG được emit op (con emit), tránh op trùng/rác."""
    kids = ctx.doc.children(node.path)
    return any(re.match(r"^(Sửa đổi|Bổ sung|Bãi bỏ|Thay thế|Ngưng hiệu lực|Đính chính)",
                        k.body.strip(), re.IGNORECASE) for k in kids)


def _rule_scan_node(node: ParsedNode, text: str, ctx: ExtractionContext,
                    ops: list[ProposedOp], seq: int) -> int:
    taken: list[tuple[int, int]] = []
    prov_spans = [(m.start(), m.end()) for m in RE_PROVENANCE_PAREN.finditer(text)]
    if "“" not in text and _children_are_directives(node, ctx):
        return seq                       # container directive — op nằm ở các node con

    def overlaps(a: int, b: int) -> bool:
        # ngoặc provenance "(đã được sửa đổi, bổ sung theo…)" KHÔNG phải mệnh lệnh op
        if any(s <= a < e for s, e in prov_spans):
            return True
        return any(not (b <= s or a >= e) for s, e in taken)

    # --- thay-cụm-từ (D-21/R-14) — trước amend để không nuốt bởi RE_AMEND ---
    for m in RE_PHRASE.finditer(text):
        new_ops = _phrase_ops(node, m, ctx, seq + 1)
        ops.extend(new_ops)
        seq += len(new_ops)
        taken.append((m.start(), m.end()))

    # --- đính chính (D-12) — trước amend: văn bản đính chính hay kèm "như sau:"/"đã in là" ---
    seq = _scan_dinh_chinh(node, text, ctx, ops, seq, taken)

    # --- ngưng hiệu lực ≠ bãi bỏ (bẫy #3) ---
    for m in RE_SUSPEND.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        sent = _sentence_at(text, m.start())
        vf, vto, ev = _dates_from_sentence(sent, ctx)
        for surface_path, doc_surface in _target_refs(m.group(1)):
            seq += 1
            ops.append(ProposedOp(
                kind="suspend", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id, target_surface=_surface_str(surface_path, doc_surface),
                target_doc_key=None, target_path=surface_path,
                valid_from=vf, valid_to=vto, valid_to_event=ev,
                provenance_mentions=_provenance_mentions(sent),
                extractor="rule", confidence=0.9))
        taken.append((m.start(), m.end()))

    # --- "thay thế Thông tư số …" → repeal toàn văn bản cũ + norm_decl kế vị (D-09) ---
    for m in RE_NORM_DECL.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        docno = extract_docno(_strip_provenance(m.group(1)))
        if docno is None:
            continue
        sent = _sentence_at(text, m.start())
        seq = _doc_repeal_ops(node, [m.group(1).strip()], sent, ctx, ops, seq)
        seq += 1
        ops.append(ProposedOp(
            kind="norm_decl", source_quote=sent, seq=seq, source_path=node.path,
            source_node=node.id, target_surface=sent.strip()[:300],
            target_doc_key=ctx.doc_key,
            valid_from=ctx.effective_date, scope_predicate=ctx.scope_predicate,
            extractor="rule", confidence=0.85,
            notes="norm succession: văn bản này kế vị văn bản bị thay thế (D-09)"))
        taken.append((m.start(), m.end()))

    # --- blanket derogation (D-14) ---
    for m in RE_BLANKET.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        seq += 1
        ops.append(ProposedOp(
            kind="blanket_derogation", source_quote=_sentence_at(text, m.start()),
            seq=seq, source_path=node.path, source_node=node.id,
            valid_from=ctx.effective_date, extractor="rule", confidence=0.9))
        taken.append((m.start(), m.end()))

    # --- amend ("Sửa đổi, bổ sung X như sau: “…”") ---
    for m in list(RE_AMEND.finditer(text)) + list(RE_AMENDED_AS.finditer(text)):
        if overlaps(m.start(), m.end()):
            continue
        target_spec = m.group(1).strip()
        heading_op = bool(re.search(r"\btên\b", text[m.start():m.start() + 40], re.IGNORECASE))
        qb = find_quote_block(text, m.end())
        if qb is None:
            continue
        block, qs, qe = qb
        sent = text[m.start():qe].strip()
        refs = _target_refs(target_spec)
        units = split_quoted_units(block)
        vf, _, _ = _dates_from_sentence(text[max(0, m.start() - 100):m.start() + 60], ctx)
        for i, (surface_path, doc_surface) in enumerate(refs):
            unit = units[i] if i < len(units) else units[-1] if units else ("", "", strip_quoted_new_text(block))
            heading, body = _strip_unit_marker(unit[2], *(unit[0], unit[1])) \
                if unit[0] else (None, unit[2])
            seq += 1
            op = ProposedOp(
                kind="amend", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id, target_surface=_surface_str(surface_path, doc_surface),
                target_path=surface_path, target_part="heading" if heading_op else "body",
                new_text=None if heading_op else (body or None),
                new_heading=heading if not heading_op else _heading_from_block(block),
                valid_from=vf, scope_predicate=ctx.scope_predicate,
                provenance_mentions=_provenance_mentions(sent),
                extractor="rule", confidence=0.9)
            if heading_op and op.new_heading is None:
                op.new_heading = strip_quoted_new_text(block)
            ops.append(op)
        taken.append((m.start(), qe))

    # --- insert ("Bổ sung X vào (sau) Y như sau: “…”") ---
    for m in RE_INSERT.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        spec = m.group(1).strip()
        qb = find_quote_block(text, m.end() - 1)
        block, qs, qe = qb if qb else ("", m.end(), m.end())
        sent = text[m.start():qe].strip() if qb else _sentence_at(text, m.start())
        seq = _insert_ops(node, spec, block, sent, ctx, ops, seq)
        taken.append((m.start(), qe))

    # --- repeal ("Bãi bỏ …") — unit, toàn văn bản, hoặc danh sách "các văn bản sau" ---
    for m in RE_REPEAL.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        sent = _sentence_at(text, m.start())
        vf, _, _ = _dates_from_sentence(sent, ctx)
        spec = m.group(1)
        if RE_LIST_SUBJECT.search(spec):
            seq = _list_repeal_ops(node, sent, ctx, ops, seq, vf)
        else:
            seq = _repeal_spec_ops(node, spec, sent, ctx, ops, seq, vf)
        taken.append((m.start(), m.end()))

    # --- "<X> hết hiệu lực (thi hành)" ---
    for m in RE_HET_HIEU_LUC.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        sent = _sentence_at(text, m.start())
        cut = sent.rfind("hết hiệu lực")
        subject = sent[:cut] if cut >= 0 else ""
        # bỏ mệnh đề dẫn "Kể từ ngày … có hiệu lực thi hành," trước chủ ngữ thật
        subject = re.sub(r"^.*?có hiệu lực(?:\s+thi hành)?\s*,\s*", "", subject)
        prov_free_subject = _strip_provenance(subject)
        if re.search(r"có hiệu lực|[Nn]gưng hiệu lực|trái với", prov_free_subject) \
                or not subject.strip():
            continue
        vf, _, _ = _dates_from_sentence(sent, ctx)
        succession = bool(RE_SUCCESSION_CUE.search(sent))
        if RE_LIST_SUBJECT.search(subject):
            seq = _list_repeal_ops(node, sent, ctx, ops, seq, vf)
        else:
            refs = parse_surface(prov_free_subject)
            if refs and any(g.paths for g in refs):
                for group in refs:
                    for surface_path in group.paths:
                        seq += 1
                        ops.append(ProposedOp(
                            kind="repeal", source_quote=sent, seq=seq, source_path=node.path,
                            source_node=node.id,
                            target_surface=_surface_str(surface_path, group.doc_surface),
                            target_path=surface_path, valid_from=vf,
                            provenance_mentions=_provenance_mentions(sent),
                            extractor="rule", confidence=0.85))
            else:
                seq = _doc_repeal_ops(node, [prov_free_subject], sent, ctx, ops, seq, vf)
        if succession:
            seq += 1
            ops.append(ProposedOp(
                kind="norm_decl", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id, target_surface=sent.strip()[:300],
                target_doc_key=ctx.doc_key, valid_from=vf,
                extractor="rule", confidence=0.8,
                notes="norm succession: văn bản này kế vị các văn bản hết hiệu lực (D-09)"))
        taken.append((m.start(), m.end()))

    return seq


def _repeal_spec_ops(node: ParsedNode, spec: str, sent: str, ctx: ExtractionContext,
                     ops: list[ProposedOp], seq: int, vf: date | None) -> int:
    """'Bãi bỏ <spec>': có đơn vị → repeal từng unit; chỉ số hiệu → repeal toàn văn bản."""
    prov_free = _strip_provenance(spec)
    refs = parse_surface(prov_free)
    if refs and any(g.paths for g in refs):
        for surface_path, doc_surface in _target_refs(spec):
            seq += 1
            ops.append(ProposedOp(
                kind="repeal", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id,
                target_surface=_surface_str(surface_path, doc_surface),
                target_path=surface_path, valid_from=vf,
                provenance_mentions=_provenance_mentions(sent),
                extractor="rule", confidence=0.9))
        return seq
    if extract_docno(prov_free):
        return _doc_repeal_ops(node, [prov_free], sent, ctx, ops, seq, vf)
    return seq


def _doc_repeal_ops(node: ParsedNode, subjects: list[str], sent: str,
                    ctx: ExtractionContext, ops: list[ProposedOp], seq: int,
                    vf: date | None = None, first_only: bool = False) -> int:
    """Repeal TOÀN văn bản: mỗi số hiệu một op `repeal` nhắm NORM của văn bản đó
    (không có node đơn lẻ nào đại diện cả văn bản; norm id mint nếu chưa có — F4
    ghi bảng norm khi ratify). target_doc_key giữ số hiệu (kể cả out-of-corpus).
    first_only: item danh sách dạng 'Quyết định số X … về việc sửa đổi QĐ Y' — chỉ
    số hiệu ĐẦU là đích, phần sau là mô tả."""
    for subject in subjects:
        docnos = list(dict.fromkeys(RE_DOCNO.findall(_strip_provenance(subject))))
        if first_only:
            docnos = docnos[:1]
        for docno in docnos:
            replaced_doc = ctx.store.find_doc(docno)
            existing = ctx.store.norm_for_doc(replaced_doc) if replaced_doc else None
            seq += 1
            op = ProposedOp(
                kind="repeal", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id, target_surface=subject.strip()[:300],
                target_doc_key=docno, target_norm=existing or uuid4(),
                valid_from=vf or ctx.effective_date,
                provenance_mentions=_provenance_mentions(sent),
                extractor="rule", confidence=0.85,
                notes="repeal toàn văn bản → nhắm Norm (D-09)"
                      + ("" if replaced_doc else " · out-of-corpus"))
            op.target_unique = replaced_doc is not None
            ops.append(op)
    return seq


def _list_repeal_ops(node: ParsedNode, sent: str, ctx: ExtractionContext,
                     ops: list[ProposedOp], seq: int, vf: date | None) -> int:
    """'(Bãi bỏ|hết hiệu lực) các văn bản sau đây:' → phân phối xuống từng item:
    node con (điểm/khoản) hoặc dòng gạch đầu dòng trong chính body."""
    items: list[tuple[str, str]] = []          # (item_text, source_path)
    for child in ctx.doc.children(node.path):
        if child.body.strip():
            items.append((child.body.strip(), child.path))
    if not items:
        after_colon = node.body.split(":", 1)[-1]
        for ln in after_colon.split("\n"):
            ln = ln.strip().lstrip("-–• ").strip()
            if len(ln) > 8:
                items.append((ln, node.path))
    for item_text, src_path in items:
        src_node = ctx.doc.node_at(src_path) or node
        prov_free = _strip_provenance(item_text)
        # item mở đầu bằng LOẠI văn bản → repeal toàn văn bản (số hiệu đầu; phần
        # 'về việc sửa đổi Điều 2 QĐ …' chỉ là mô tả). Mở đầu bằng đơn vị → repeal unit.
        if re.match(r"(?:Thông tư|Quyết định|Nghị định|Luật|Bộ luật|Nghị quyết|Văn bản)\b",
                    prov_free.strip(), re.IGNORECASE):
            seq = _doc_repeal_ops(src_node, [item_text], item_text[:400], ctx, ops, seq,
                                  vf, first_only=True)
            continue
        groups = parse_surface(prov_free)
        unit_groups = [g for g in groups if g.paths]
        if unit_groups:
            group = unit_groups[0]
            for surface_path in group.paths:
                seq += 1
                ops.append(ProposedOp(
                    kind="repeal", source_quote=item_text[:400], seq=seq,
                    source_path=src_path, source_node=src_node.id,
                    target_surface=_surface_str(surface_path, group.doc_surface),
                    target_path=surface_path, valid_from=vf,
                    provenance_mentions=_provenance_mentions(item_text),
                    extractor="rule", confidence=0.85))
        elif extract_docno(prov_free):
            seq = _doc_repeal_ops(src_node, [item_text], item_text[:400], ctx, ops, seq,
                                  vf, first_only=True)
    return seq


def _scan_dinh_chinh(node: ParsedNode, text: str, ctx: ExtractionContext,
                     ops: list[ProposedOp], seq: int, taken: list[tuple[int, int]]) -> int:
    """Hai dạng đính chính: (a) 'đã in là: “X” … đính chính thành/sửa lại là: “Y”' —
    target từ 'Tại <ref>' trước đó; (b) 'Đính chính <ref> như sau: “…”'.
    valid_from = ĐẦU cửa sổ của text bị đính chính (D-12 hồi tố) — lấy ngày hiệu lực
    của văn bản trong provenance mention nếu resolve được."""
    printed = False
    m_in = RE_DA_IN.search(text)
    m_out = RE_SUA_LAI.search(text)
    if m_in and m_out and m_out.start() > m_in.start():
        printed = True
        frm, to = m_in.group(1), m_out.group(1)
        seg_start = max(text.rfind("\n", 0, m_in.start()), text.rfind(";", 0, m_in.start()))
        seg = text[seg_start + 1:m_in.start()]
        m_tai = re.search(r"[Tt]ại\s+(.{4,300}?)\s*[,;]?\s*$", seg)
        spec = m_tai.group(1) if m_tai else seg
        sent = text[seg_start + 1:m_out.end()].strip()
        mentions = _provenance_mentions(seg) or _provenance_mentions(text)
        vf = _window_start_from_mentions(mentions, ctx) or ctx.effective_date
        for surface_path, doc_surface in _target_refs(spec):
            seq += 1
            ops.append(ProposedOp(
                kind="dinh_chinh", source_quote=sent[:600], seq=seq, source_path=node.path,
                source_node=node.id, target_surface=_surface_str(surface_path, doc_surface),
                target_path=surface_path, new_text=to, phrase_from=frm, phrase_to=to,
                valid_from=vf, provenance_mentions=mentions,
                extractor="rule", confidence=0.85,
                notes="đính chính dạng 'đã in là/sửa lại là' — hồi tố về đầu cửa sổ (D-12)"))
        taken.append((seg_start + 1, m_out.end()))
    if printed:
        return seq
    for m in RE_DINH_CHINH.finditer(text):
        if any(not (m.end() <= s or m.start() >= e) for s, e in taken):
            continue
        sent = _sentence_at(text, m.start())
        # dạng phrase-swap: 'Đính chính cụm từ “X” thành “Y”' — không thay toàn body
        m_swap = RE_CUM_TU_SWAP.search(text, m.start())
        if m_swap:
            frm, to = m_swap.group(1), m_swap.group(2)
            new_text, end = None, m_swap.end()
        else:
            frm = to = None
            qb = find_quote_block(text, m.end())
            new_text = strip_quoted_new_text(qb[0]) if qb else None
            end = qb[2] if qb else m.end()
        mentions = _provenance_mentions(sent)
        vf = _window_start_from_mentions(mentions, ctx) or ctx.effective_date
        for surface_path, doc_surface in _target_refs(m.group(1)):
            heading, body = (None, new_text)
            if new_text:
                leaf = surface_path.split("/")[-1]
                lvl, _, lb = leaf.partition(":")
                heading, body = _strip_unit_marker(new_text, lvl, lb)
            seq += 1
            ops.append(ProposedOp(
                kind="dinh_chinh", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id, target_surface=_surface_str(surface_path, doc_surface),
                target_path=surface_path, new_text=body, new_heading=heading,
                phrase_from=frm, phrase_to=to,
                valid_from=vf, provenance_mentions=mentions,
                extractor="rule", confidence=0.8))
        taken.append((m.start(), end))
    return seq


RE_CUM_TU_SWAP = re.compile(
    r"cụm từ\s*“([^”]{1,120})”\s*(?:thành|bằng|sửa lại là|đính chính thành)\s*“([^”]{1,120})”",
    re.IGNORECASE)


def _window_start_from_mentions(mentions: list[str], ctx: ExtractionContext) -> date | None:
    """Ngày hiệu lực của văn bản được mention (= đầu cửa sổ text bị đính chính)."""
    for mention in mentions:
        docno = extract_docno(mention)
        if not docno:
            continue
        dk = ctx.store.find_doc(docno)
        if dk:
            meta = ctx.store.doc_meta(dk) or {}
            eff = meta.get("effective_date")
            if eff:
                return eff if isinstance(eff, date) else date.fromisoformat(str(eff))
    return None


def _heading_from_block(block: str) -> str | None:
    inner = strip_quoted_new_text(block)
    m = RE_DIEU.match(inner.strip())
    if m:
        return m.group(2).strip().rstrip(".") or None
    return inner.strip() or None


def _phrase_ops(node: ParsedNode, m: re.Match[str], ctx: ExtractionContext,
                seq: int) -> list[ProposedOp]:
    """Thay-cụm-từ: KHÔNG vào enum op — materialize danh sách op amend node-level
    cho curator duyệt (mỗi node bị chạm một op, template batch `phrase_replace`)."""
    frm, to, where = m.group(1), m.group(2), m.group(3)
    sent = m.group(0)
    touched: list[tuple[str, str | None]] = []
    if where:
        touched = _target_refs(where)
    ops: list[ProposedOp] = []
    for i, (surface_path, doc_surface) in enumerate(touched):
        ops.append(ProposedOp(
            kind="amend", source_quote=sent, seq=seq + i, source_path=node.path,
            source_node=node.id, target_surface=_surface_str(surface_path, doc_surface),
            target_path=surface_path, phrase_from=frm, phrase_to=to,
            valid_from=ctx.effective_date, extractor="rule:phrase", confidence=0.85,
            notes=f"materialize thay cụm từ “{frm}” → “{to}” (D-21)"))
    if not touched:
        ops.append(ProposedOp(
            kind="amend", source_quote=sent, seq=seq, source_path=node.path,
            source_node=node.id, target_surface=None, phrase_from=frm, phrase_to=to,
            valid_from=ctx.effective_date, extractor="rule:phrase", confidence=0.3,
            red_flags=["phrase_replace_no_target_list"],
            notes="thay cụm từ không nêu địa chỉ — curator phải chọn node bị chạm (D-21)"))
    return ops


def _insert_ops(node: ParsedNode, spec: str, block: str, sent: str,
                ctx: ExtractionContext, ops: list[ProposedOp], seq: int) -> int:
    """'Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8' → 3 op insert, pair theo label."""
    m_anchor = re.search(r"\bvào\s+(?:sau\s+|cuối\s+)?(.{2,160})$", spec, re.IGNORECASE)
    new_part, anchor_part = (spec[:m_anchor.start()].strip(), m_anchor.group(1).strip()) \
        if m_anchor else (spec, "")
    append_mode = bool(re.search(r"\bvào\s+cuối\b|một đoạn vào cuối", spec, re.IGNORECASE))
    new_refs = parse_surface(new_part)
    anchor_refs = parse_surface(anchor_part) if anchor_part else []
    anchor_group = anchor_refs[0] if anchor_refs else None
    doc_surface = (anchor_group.doc_surface if anchor_group and anchor_group.doc_surface
                   else (new_refs[0].doc_surface if new_refs and new_refs[0].doc_surface else None))
    units = split_quoted_units(block) if block else []

    # "Bổ sung Mục 3 vào Chương II như sau: “Mục 3 … Điều 32a … Điều 32h”" — Mục/Chương
    # là container KHÔNG phải node (02§1) → decompose: mỗi Điều mới một op insert.
    if re.search(r"\bMục\s+\d+", new_part, re.IGNORECASE) and not new_refs:
        dieu_units = [u for u in units if u[0] == "dieu"]
        for lvl, lb, unit_text in dieu_units:
            heading, body = _strip_unit_marker(unit_text, lvl, lb)
            vf, _, _ = _dates_from_sentence(sent, ctx)
            seq += 1
            ops.append(ProposedOp(
                kind="insert", source_quote=sent[:400], seq=seq, source_path=node.path,
                source_node=node.id,
                target_surface=_surface_str(f"dieu:{lb}", doc_surface),
                target_path=f"dieu:{lb}", new_text=body, new_heading=heading,
                valid_from=vf, scope_predicate=ctx.scope_predicate,
                extractor="rule", confidence=0.85,
                notes="decompose 'Bổ sung Mục' → op per Điều mới (Mục là container, 02§1)"))
        return seq

    if (append_mode and anchor_group) or \
            (anchor_group and anchor_group.paths
             and anchor_group.paths[0].startswith("phuluc:")):
        # "Bổ sung một đoạn/khoản vào (cuối) Phụ lục N" → amend nối text vào node Phụ lục
        # (bẫy #11; Phụ lục là blob D-49 — không có node con để insert)
        target = anchor_group.paths[0]
        seq += 1
        ops.append(ProposedOp(
            kind="amend", source_quote=sent, seq=seq, source_path=node.path,
            source_node=node.id, target_surface=_surface_str(target, doc_surface),
            target_path=target, new_text=strip_quoted_new_text(block) if block else None,
            valid_from=ctx.effective_date, extractor="rule", confidence=0.8,
            notes="bổ sung vào Phụ lục/cuối — semantics nối text vào blob (curator xem diff)"))
        return seq

    if not new_refs:
        return seq
    anchor_paths = anchor_group.paths if anchor_group else []
    anchor = anchor_paths[0] if anchor_paths else None
    by_label = {}
    for lvl, lb, txt in units:
        by_label[(lvl, lb)] = txt
    for group in new_refs:
        for path in group.paths:
            leaf = path.split("/")[-1]
            lvl, _, lb = leaf.partition(":")
            target_path = path
            if anchor and not path.startswith(anchor) and len(path.split("/")) == 1 \
                    and lvl != "dieu" and lvl != "phuluc":
                target_path = f"{anchor}/{path}"
            unit_text = by_label.get((lvl, lb))
            if unit_text is None and len(units) == 1 and len(group.paths) == 1:
                unit_text = units[0][2]
            heading, body = _strip_unit_marker(unit_text, lvl, lb) if unit_text \
                else (None, None)
            vf, _, _ = _dates_from_sentence(sent, ctx)
            seq += 1
            ops.append(ProposedOp(
                kind="insert", source_quote=sent, seq=seq, source_path=node.path,
                source_node=node.id,
                target_surface=_surface_str(target_path, doc_surface or group.doc_surface),
                target_path=target_path, new_text=body, new_heading=heading,
                valid_from=vf, scope_predicate=ctx.scope_predicate,
                provenance_mentions=_provenance_mentions(sent),
                extractor="rule", confidence=0.9 if unit_text else 0.5,
                red_flags=[] if unit_text else ["insert_no_text_paired"]))
    return seq


def _strip_provenance(spec: str) -> str:
    """Bỏ provenance khỏi spec đích — cả dạng ngoặc '(đã được bổ sung theo …)' lẫn
    dạng inline '… đã được sửa đổi, bổ sung bởi khoản 11 Điều 1 TT06' — không thì
    địa chỉ provenance bị parse thành TARGET giả (bẫy TT10/TT12)."""
    spec = RE_PROVENANCE_PAREN.sub(" ", spec)
    return RE_PROVENANCE_INLINE.sub(" ", spec)


def _target_refs(spec: str) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for group in parse_surface(_strip_provenance(spec)):
        for path in group.paths:
            out.append((path, group.doc_surface))
    return out


def _surface_str(path: str, doc_surface: str | None) -> str:
    return f"{path} @ {doc_surface}" if doc_surface else path


def _provenance_mentions(sent: str) -> list[str]:
    out = [m.group(1).strip() for m in RE_PROVENANCE_PAREN.finditer(sent)]
    paren_free = RE_PROVENANCE_PAREN.sub(" ", sent)
    out += [m.group(1).strip() for m in RE_PROVENANCE_INLINE.finditer(paren_free)]
    return out


# ============================================================================
# Grandfather scope từ điều chuyển tiếp (02§4, D-25)
# ============================================================================

RE_GF_SIGNED_BEFORE = re.compile(
    r"(?:hợp đồng|thỏa thuận)[^.;]{0,160}?(?:được\s+)?(?:ký kết|giao kết|ký)\s+trước\s+ngày"
    r"[^.;]{0,80}?(?:có hiệu lực|(\d{1,2}[\s/]+tháng[\s/]*\d{1,2}[\s/]+năm[\s/]+\d{4}))",
    re.IGNORECASE)


def extract_scope_predicate(doc: ParsedDoc, effective: date | None) -> dict[str, Any] | None:
    """Điều khoản chuyển tiếp TT06-style → DSL đóng D-25 (cohort GIỮ text cũ):
    ký trước ngày hiệu lực ∧ chưa sửa đổi từ ngày đó."""
    for node in doc.nodes:
        if node.role != "transition":
            continue
        text = node.full_text()
        if RE_GF_SIGNED_BEFORE.search(text) and "tiếp tục" in text.lower():
            if effective is None:
                return None
            pred: dict[str, Any] = {"contract_signed_before": effective.isoformat()}
            if re.search(r"sửa đổi, bổ sung", text, re.IGNORECASE):
                pred["not_amended_on_or_after"] = effective.isoformat()
            return pred
    return None


# ============================================================================
# Tầng LLM (D-18) — JSON schema + few-shot bắt buộc
# ============================================================================

def _plain_extraction_schema() -> dict[str, Any]:
    """JSON Schema phẳng cho gateway (dates = string ISO; validate lại bằng Pydantic)."""
    return {
        "type": "object",
        "properties": {
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string",
                                 "enum": ["amend", "insert", "repeal", "suspend",
                                          "dinh_chinh", "norm_decl", "blanket_derogation"]},
                        "target_surface": {"type": ["string", "null"]},
                        "target_is_amending_provision": {"type": "boolean"},
                        "target_part": {"type": "string", "enum": ["body", "heading"]},
                        "new_text": {"type": ["string", "null"]},
                        "new_heading": {"type": ["string", "null"]},
                        "valid_from": {"type": ["string", "null"]},
                        "valid_to": {"type": ["string", "null"]},
                        "valid_to_event": {"type": ["string", "null"]},
                        "scope_predicate": {
                            "type": "object",
                            "properties": {
                                "contract_signed_before": {"type": ["string", "null"]},
                                "not_amended_on_or_after": {"type": ["string", "null"]},
                                "entity_class": {"type": ["string", "null"]},
                            },
                            "required": [],
                            "additionalProperties": False,
                        },
                        "source_quote": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["kind", "target_surface", "target_part",
                                 "source_quote", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["ops"],
        "additionalProperties": False,
    }


LLM_OP_SYSTEM = """Bạn trích xuất TOÁN TỬ SỬA ĐỔI (op) từ văn bản pháp quy Việt Nam. \
Trả về JSON đúng schema. Đây là ĐỀ XUẤT cho người phê chuẩn — không được đoán bừa.

BẢNG KIND (02§3): amend ("sửa đổi, bổ sung … như sau", thay text/heading node hiện có) · \
insert ("bổ sung Điều/khoản/điểm MỚI … vào …" — đơn vị CHƯA tồn tại) · repeal ("bãi bỏ", \
"hết hiệu lực thi hành" — đóng VĨNH VIỄN) · suspend ("NGƯNG hiệu lực thi hành" — treo KHẢ HỒI, \
KHÁC repeal) · dinh_chinh ("đính chính" — hồi tố về đầu cửa sổ) · norm_decl (thay thế TOÀN \
văn bản: "thay thế Thông tư số …") · blanket_derogation ("mọi quy định trước đây trái với \
Thông tư này hết hiệu lực" — KHÔNG có target).

QUY TẮC BẮT BUỘC:
1. MỘT op = MỘT thao tác trên MỘT đơn vị. TÁCH enumeration: "bổ sung khoản 8, khoản 9 và \
khoản 10 vào Điều 8" → 3 op insert riêng, mỗi op mang new_text của đúng khoản đó.
2. `ngưng hiệu lực` ≠ `bãi bỏ`: ngưng = suspend (khả hồi, thường kèm "cho đến ngày …" → \
valid_to_event nếu mốc là SỰ KIỆN chưa xác định, không phải ngày); bãi bỏ = repeal.
3. Binding "Thông tư này" (02§5.3): nằm TRONG text được quote “…” → chỉ văn bản ĐÍCH \
được sửa; nằm NGOÀI quote → chỉ văn bản sửa đổi (nguồn). target_surface phải ghi số hiệu \
văn bản đích tường minh khi xác định được.
4. Hiệu lực phân kỳ: nếu văn bản quy định ngày hiệu lực RIÊNG cho một chủ đề ("các quy \
định về X có hiệu lực từ …"), op thuộc chủ đề đó mang valid_from riêng, KHÔNG phải ngày chung.
5. KHÔNG đoán target: không xác định được đích → target_surface=null + confidence ≤ 0.3.
6. source_quote = NGUYÊN VĂN câu lệnh sửa đổi trong input (bắt buộc, để người đối chiếu).
7. new_text: bỏ ngoặc kép bao ngoài và dấu chấm sau ngoặc đóng; bỏ marker đơn vị đầu dòng \
("8." / "a)") — chỉ giữ nội dung.
8. target_surface dạng: "khoản 2 Điều 8 Thông tư số 39/2016/TT-NHNN" (đơn vị nhỏ→lớn + số hiệu).
9. Điều khoản chuyển tiếp kiểu grandfather ("hợp đồng ký trước ngày hiệu lực tiếp tục thực \
hiện…") KHÔNG phải op — nó cho scope_predicate: {"contract_signed_before": "<ngày hiệu lực>", \
"not_amended_on_or_after": "<ngày hiệu lực>"} gắn vào các op amend/insert của văn bản.
10. target_is_amending_provision=true khi đích LÀ một điều khoản sửa đổi của văn bản khác \
(vd "bãi bỏ khoản 2 Điều 1 Thông tư 26/2022" mà khoản đó chính là điều khoản sửa đổi) — \
hệ sẽ chuyển thành op-nhắm-op, không viết lại lịch sử."""

LLM_OP_FEWSHOT = """VÍ DỤ (few-shot bắt buộc):

[VD1 — tách enumeration + insert]
Input (nguồn 06/2023/TT-NHNN, hiệu lực chung 2023-09-01):
"2. Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8 như sau:
“8. Để gửi tiền.
9. Để thanh toán tiền góp vốn.
10. Để bù đắp tài chính.”."
Output: 3 op insert — {"kind":"insert","target_surface":"khoản 8 Điều 8 Thông tư số 39/2016/TT-NHNN","new_text":"Để gửi tiền.","valid_from":"2023-09-01",…}, tương tự khoản 9 ("Để thanh toán tiền góp vốn."), khoản 10 ("Để bù đắp tài chính.").

[VD2 — ngưng hiệu lực ≠ bãi bỏ, valid_to_event (TT10/2023)]
Input (nguồn 10/2023/TT-NHNN):
"Ngưng hiệu lực thi hành khoản 8, khoản 9 và khoản 10 Điều 8 của Thông tư số 39/2016/TT-NHNN (đã được bổ sung theo khoản 2 Điều 1 Thông tư số 06/2023/TT-NHNN) từ ngày 01 tháng 9 năm 2023 cho đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới quy định về các vấn đề này."
Output: 3 op suspend (KHÔNG phải repeal), mỗi op: {"kind":"suspend","target_surface":"khoản 8 Điều 8 Thông tư số 39/2016/TT-NHNN","valid_from":"2023-09-01","valid_to":null,"valid_to_event":"đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới quy định về các vấn đề này",…} — valid_to_event vì mốc kết thúc là SỰ KIỆN, chưa có ngày.

[VD3 — binding "Thông tư này" TRONG quote]
Input (nguồn 28/2026/TT-NHNN, sửa 09/2019/TT-NHNN):
"1. Bổ sung Điều 7a vào sau Điều 7 như sau:
“Điều 7a. Báo cáo
Ngân hàng gửi báo cáo theo quy định tại Điều 5 Thông tư này.”."
Output: 1 op insert target "Điều 7a Thông tư số 09/2019/TT-NHNN"; "Thông tư này" trong new_text chỉ TT09/2019 (văn bản đích), KHÔNG chỉ TT28/2026. new_heading="Báo cáo", new_text="Ngân hàng gửi báo cáo theo quy định tại Điều 5 Thông tư này."

[VD4 — hiệu lực phân kỳ theo chủ đề]
Input (nguồn 11/2026/TT-NHNN, hiệu lực chung 2026-03-01; Điều 4 khoản 2: "Các quy định về Phiếu lý lịch tư pháp tại Điều 3 Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026."):
Op sinh từ Điều 3 (quy định về Phiếu lý lịch tư pháp) mang "valid_from":"2026-07-01" (KHÔNG phải 2026-03-01).

[VD5 — không đoán target]
Input: "Bãi bỏ các quy định về báo cáo định kỳ trái với Thông tư này."
Output: {"kind":"repeal","target_surface":null,"confidence":0.2,…} — không có địa chỉ đơn vị
→ không bịa; confidence thấp để router đẩy per-op review."""


def llm_extract(ctx: ExtractionContext, gateway: Any) -> list[ProposedOp]:
    """Tầng LLM trên các node amending + node có rule-hit (D-18). Gateway None → []."""
    if gateway is None:
        return []
    roots = _amending_roots(ctx.doc)
    if not roots:
        return []
    model = getattr(getattr(gateway, "config", lambda r: None)("extract"), "model", "llm")
    ops: list[ProposedOp] = []
    seq_base = 1000                      # LLM seq offset — merge sẽ đối chiếu bằng target
    for root in roots:
        subtree = [n for n in ctx.doc.nodes
                   if n.path == root.path or (n.parent_path or "").startswith(root.path)
                   or n.path.startswith(root.path + "/")]
        body = "\n".join(n.full_text() for n in subtree)
        chapter = " | ".join(root.chapter_ctx) if root.chapter_ctx else "(không có Chương)"
        divergent = _divergent_effective_clauses(ctx.doc)
        user = (f"Văn bản nguồn: {ctx.doc_key} · ban hành {ctx.issued_date} · "
                f"hiệu lực chung {ctx.effective_date}\n"
                f"Context Chương (omnibus): {chapter}\n"
                f"Điều khoản hiệu lực đặc thù: {divergent or '(không)'}\n"
                f"--- NODE {root.path} ---\n{body}")
        try:
            out = gateway.complete_json(role="extract",
                                        system=LLM_OP_SYSTEM + "\n\n" + LLM_OP_FEWSHOT,
                                        user=user, schema=_plain_extraction_schema())
            parsed = ExtractionResult.model_validate(_coerce_dates(out))
        except Exception as exc:
            logger.warning("op_extract LLM lỗi tại %s: %s — giữ tầng rule", root.path, exc)
            continue
        for x in parsed.ops:
            seq_base += 1
            ops.append(_from_extracted(x, root, subtree, ctx, seq_base, model))
    return ops


def _coerce_dates(out: dict) -> dict:
    for op in out.get("ops", []):
        sp = op.get("scope_predicate")
        if sp is not None and not any(v for v in sp.values()):
            op["scope_predicate"] = {}
    return out


def _divergent_effective_clauses(doc: ParsedDoc) -> str:
    hits = []
    for n in doc.nodes:
        if n.role == "effectivity":
            for m in re.finditer(r"[Cc]ác quy định về[^.;\n]{2,120}có hiệu lực[^.;\n]{2,80}",
                                 n.full_text()):
                hits.append(m.group(0))
    return " | ".join(hits)


def _from_extracted(x: ExtractedOp, root: ParsedNode, subtree: list[ParsedNode],
                    ctx: ExtractionContext, seq: int, model: str) -> ProposedOp:
    src = root
    for n in subtree:                      # định vị node con chứa source_quote
        if x.source_quote[:60] in n.full_text():
            src = n
            break
    target_path = None
    doc_surface = None
    if x.target_surface:
        groups = parse_surface(x.target_surface)
        if groups and groups[0].paths:
            target_path = groups[0].paths[0]
            doc_surface = groups[0].doc_surface
    return ProposedOp(
        kind=x.kind, source_quote=x.source_quote, seq=seq,
        source_path=src.path, source_node=src.id,
        target_surface=x.target_surface, target_path=target_path,
        target_part=x.target_part, new_text=x.new_text, new_heading=x.new_heading,
        valid_from=x.valid_from or ctx.effective_date, valid_to=x.valid_to,
        valid_to_event=x.valid_to_event,
        scope_predicate=(x.scope_predicate.model_dump(exclude_none=True, mode="json") or None)
        if x.scope_predicate else None,
        extractor=f"llm:{model}", confidence=x.confidence,
        notes=("target_is_amending_provision" if x.target_is_amending_provision else None),
        provenance_mentions=_provenance_mentions(x.source_quote))


def _amending_roots(doc: ParsedDoc) -> list[ParsedNode]:
    roots = []
    amending_paths: set[str] = set()
    for n in doc.nodes:
        if n.role == "amending":
            parent_amending = any(n.path.startswith(p + "/") for p in amending_paths)
            amending_paths.add(n.path)
            if not parent_amending:
                roots.append(n)
        elif n.role == "effectivity" and any(
                r.search(n.full_text())
                for r in (RE_REPEAL, RE_NORM_DECL, RE_BLANKET, RE_HET_HIEU_LUC)):
            roots.append(n)             # op nấp ở điều thi hành (R-11)
    return roots


# ============================================================================
# Merge rule ⊕ LLM (D-19 điều kiện "rule↔LLM khớp")
# ============================================================================

def merge_ops(rule_ops: list[ProposedOp], llm_ops: list[ProposedOp],
              llm_enabled: bool) -> list[ProposedOp]:
    def key(o: ProposedOp) -> tuple:
        return (o.kind, o.target_path or (o.target_surface or "").lower(), o.target_part)

    merged: dict[tuple, ProposedOp] = {}
    order: list[tuple] = []
    rule_keys: set[tuple] = set()
    for o in rule_ops:
        k = key(o)
        merged[k] = o
        order.append(k)
        rule_keys.add(k)
    for lo in llm_ops:
        k = key(lo)
        if k in merged and k not in rule_keys:
            # trùng với op LLM đã có (nhiều root cùng trả một op) — giữ confidence cao nhất
            merged[k].confidence = max(merged[k].confidence, lo.confidence)
            continue
        if k in merged:
            ro = merged[k]
            ro.rule_llm_agree = True
            ro.confidence = max(ro.confidence, lo.confidence)
            ro.extractor = f"{ro.extractor}+{lo.extractor}"
            # rule giữ new_text tất định; LLM bù trường rule không đọc được
            ro.valid_to_event = ro.valid_to_event or lo.valid_to_event
            ro.scope_predicate = ro.scope_predicate or lo.scope_predicate
            if lo.notes == "target_is_amending_provision":
                ro.notes = lo.notes
            if lo.valid_from and ro.valid_from and lo.valid_from != ro.valid_from:
                ro.red_flags.append("date_mismatch_rule_vs_llm")
        else:
            lo.rule_llm_agree = False
            merged[k] = lo
            order.append(k)
    seen: set[tuple] = set()
    out = [merged[k] for k in order if not (k in seen or seen.add(k))]
    if not llm_enabled:
        for o in out:
            o.rule_llm_agree = False
    return sorted(out, key=lambda o: o.seq)


# ============================================================================
# Resolver + R-12/R-13
# ============================================================================

def resolve_ops(ops: list[ProposedOp], ctx: ExtractionContext) -> list[ParsedNode]:
    """Resolve target surface→node; amending-target→target_op (R-12); insert→birth node.
    Trả về danh sách node MỚI được op insert tạo (persist cùng bundle)."""
    born: list[ParsedNode] = []
    at = ctx.issued_date or ctx.effective_date or date.today()
    for op in ops:
        if op.kind == "blanket_derogation":
            continue
        if op.kind == "norm_decl":
            _resolve_norm_decl(op, ctx)
            continue
        if op.target_norm is not None:            # repeal toàn văn bản đã nhắm Norm
            continue
        if op.target_path is None:
            op.red_flags.append("target_unresolved")
            op.confidence = min(op.confidence, 0.3)
            continue
        doc_key = _target_doc_key(op, ctx)
        op.target_doc_key = doc_key
        if doc_key is None:
            op.red_flags.append("target_doc_unresolved")
            op.confidence = min(op.confidence, 0.3)
            continue
        if doc_key == ctx.doc_key:
            local = ctx.doc.node_at(op.target_path)
            if local is not None:                 # target nội bộ doc đang ingest
                op.target_node = local.id
                op.target_unique = True
                _cross_validate_provenance(op, ctx)
                continue
        res = ctx.store.resolve(doc_key, op.target_path, at)
        if res is not None and op.kind == "insert":
            # đích đã tồn tại → thực chất amend? — cờ đỏ cho curator
            op.target_node = res.node_id
            op.target_unique = True
            op.red_flags.append("insert_target_already_exists")
        elif res is not None:
            op.target_node = res.node_id
            op.target_unique = True
            if res.role == "amending" or op.notes == "target_is_amending_provision":
                _convert_to_target_op(op, res.node_id, ctx)      # R-12
        elif op.kind == "insert":
            node = _birth_node(op, doc_key, ctx)
            born.append(node)
            op.target_node = node.id
            op.target_unique = True
        elif _parent_resolves(op, doc_key, ctx, at) and op.provenance_mentions:
            # bẫy #4/D-08: đích là đơn vị do op KHÁC (chưa ratify) sinh trong lòng node cha
            # đã có — TT10 treo k8-10 Đề8 (TT06 thay toàn Đề8); cấp birth-id để op có đích,
            # provenance mention là điều kiện (chống birth bừa do typo); R-13 verify tiếp
            node = _birth_node(op, doc_key, ctx)
            born.append(node)
            op.target_node = node.id
            op.target_unique = True
            op.notes = (op.notes or "") + " | birth dưới node cha (đơn vị do op pending sinh)"
        else:
            op.red_flags.append("target_unresolved")
            op.confidence = min(op.confidence, 0.3)
        _materialize_phrase(op, ctx)                              # R-14/D-21
        _cross_validate_provenance(op, ctx)                       # R-13
    return born


def _parent_resolves(op: ProposedOp, doc_key: str, ctx: ExtractionContext, at: date) -> bool:
    parts = (op.target_path or "").split("/")
    for i in range(len(parts) - 1, 0, -1):
        parent = "/".join(parts[:i])
        if ctx.store.resolve(doc_key, parent, at) is not None:
            return True
    return False


def _complete_with_ancestor(op: ProposedOp, ctx: ExtractionContext) -> None:
    """Directive lồng (TT06): khoản cha nói 'Sửa đổi, bổ sung khoản 2, bổ sung khoản 5
    Điều 26 như sau:' — điểm con chỉ ghi 'khoản 2' → ghép container Điều từ directive
    của TỔ TIÊN (địa chỉ tương đối trong cascade sửa đổi — 02§5.4 tinh thần context-stack)."""
    path = op.target_path or ""
    top_level = path.split("/", 1)[0].split(":")[0]
    if top_level in ("dieu", "phuluc") or not op.source_path:
        return
    cur = ctx.doc.node_at(op.source_path)
    cur = ctx.doc.node_at(cur.parent_path) if cur and cur.parent_path else None
    while cur is not None:
        directive = cur.full_text().split("“", 1)[0]      # phần trước quote đầu
        for group in parse_surface(_strip_provenance(directive)):
            for p in group.paths:
                segs = p.split("/")
                if segs[0].startswith("dieu:"):
                    # lấy đủ prefix còn thiếu: path con 'khoan:2/diem:a' + container 'dieu:26'
                    prefix_segs = []
                    child_top = path.split("/", 1)[0].split(":")[0]
                    for s in segs:
                        lvl = s.split(":")[0]
                        if LEVEL_RANK.get(lvl, 0) > LEVEL_RANK.get(child_top, 0):
                            prefix_segs.append(s)
                    if prefix_segs:
                        op.target_path = "/".join(prefix_segs) + "/" + path
                        if not extract_docno(op.target_surface or "") and group.doc_surface:
                            op.target_surface = f"{op.target_path} @ {group.doc_surface}"
                        return
        cur = ctx.doc.node_at(cur.parent_path) if cur.parent_path else None


def _materialize_phrase(op: ProposedOp, ctx: ExtractionContext) -> None:
    """Thay-cụm-từ (D-21): tính new_text = old.replace(from, to) cho TỪNG node bị
    chạm để curator thấy diff thật — không auto-apply (vẫn proposed); template
    batch `phrase_replace` machine-verify đúng phép thay (R-16)."""
    if not op.phrase_from or op.target_node is None or op.new_text is not None:
        return
    info = getattr(ctx.store, "node_info", lambda _x: None)(op.target_node)
    old = (info or {}).get("body") or ""
    if op.phrase_from in old:
        op.old_text = old
        op.new_text = old.replace(op.phrase_from, op.phrase_to or "")
    else:
        op.red_flags.append("phrase_not_found_in_target")
        op.confidence = min(op.confidence, 0.3)


def _target_doc_key(op: ProposedOp, ctx: ExtractionContext) -> str | None:
    surface = op.target_surface or ""
    docno = extract_docno(surface)
    if docno:
        return ctx.store.find_doc(docno)
    src = ctx.doc.node_at(op.source_path) if op.source_path else None
    if src is not None:
        chapter_doc = _chapter_target_doc(src, ctx)
        if chapter_doc:
            return chapter_doc                                    # omnibus 02§5.4
    # heading văn bản kiểu "SỬA ĐỔI … THÔNG TƯ SỐ 39/2016/TT-NHNN" — carry là KHÔNG đủ
    # (02§5.4) nhưng dùng khi doc chỉ sửa MỘT văn bản và không có Chương
    title_doc = _single_amend_target_from_title(ctx)
    if title_doc:
        return title_doc
    return ctx.doc_key


def _chapter_target_doc(src: ParsedNode, ctx: ExtractionContext) -> str | None:
    for chap in reversed(src.chapter_ctx):
        docno = extract_docno(chap)
        if docno:
            return ctx.store.find_doc(docno) or docno
    # heading Điều cha dạng "Sửa đổi, bổ sung một số điều của Thông tư số X"
    cur = src
    while cur is not None:
        head = cur.heading or ""
        if re.search(r"sửa đổi|bổ sung|ngưng hiệu lực|bãi bỏ", head, re.IGNORECASE):
            docno = extract_docno(head)
            if docno:
                return ctx.store.find_doc(docno) or docno
        cur = ctx.doc.node_at(cur.parent_path) if cur.parent_path else None
    return None


def _single_amend_target_from_title(ctx: ExtractionContext) -> str | None:
    title = ctx.doc.title or ""
    docnos = list(dict.fromkeys(RE_DOCNO.findall(title)))
    if len(docnos) == 1 and docnos[0] != ctx.doc_key:
        return ctx.store.find_doc(docnos[0]) or docnos[0]
    return None


def _convert_to_target_op(op: ProposedOp, amending_node: Any, ctx: ExtractionContext) -> None:
    """Target là điều khoản sửa đổi → op phải nhắm OP nó sinh ra (D-10), không nhắm node."""
    candidate_ops = ctx.store.ops_from_source_node(amending_node)
    if len(candidate_ops) == 1:
        op.target_op = candidate_ops[0]
        op.target_node = None
        op.notes = (op.notes or "") + " | resolved amending-node → target_op (R-12)"
    elif len(candidate_ops) > 1:
        op.target_op = None
        op.red_flags.append("amending_target_multiple_ops")
        op.notes = (op.notes or "") + f" | node amending sinh {len(candidate_ops)} op — curator chọn"
    else:
        op.red_flags.append("amending_target_no_op_found")


def _birth_node(op: ProposedOp, doc_key: str, ctx: ExtractionContext) -> ParsedNode:
    path = op.target_path or ""
    leaf = path.split("/")[-1]
    lvl, _, lb = leaf.partition(":")
    parent = "/".join(path.split("/")[:-1]) or None
    node = ParsedNode(level=lvl, label=lb, path=path, seq=0,  # type: ignore[arg-type]
                      heading=op.new_heading, body=op.new_text or "",
                      parent_path=parent, role="rule", born_of_op=True,
                      artifact_doc_key=doc_key)
    return node


def _resolve_norm_decl(op: ProposedOp, ctx: ExtractionContext) -> None:
    docno = extract_docno(op.target_surface or "")
    replaced_doc = ctx.store.find_doc(docno) if docno else None
    existing = ctx.store.norm_for_doc(replaced_doc) if replaced_doc else None
    op.target_norm = existing or uuid4()      # norm identity sinh cùng op (F4 ghi bảng norm khi ratify)
    op.target_unique = existing is not None
    if replaced_doc is None:
        op.red_flags.append("norm_decl_doc_not_in_corpus")
        op.confidence = min(op.confidence, 0.5)


def _cross_validate_provenance(op: ProposedOp, ctx: ExtractionContext) -> None:
    """R-13: '(đã được bổ sung theo khoản 2 Điều 1 Thông tư 06…)' — chuỗi op của node
    đích PHẢI chứa op từ đúng nguồn đó; lệch → cờ đỏ giữ ở queue."""
    if not op.provenance_mentions or op.target_node is None and op.target_op is None:
        return
    for mention in op.provenance_mentions:
        docno = extract_docno(mention)
        groups = parse_surface(mention)
        src_path = groups[0].paths[0] if groups and groups[0].paths else None
        if docno is None or src_path is None:
            continue
        src_doc = ctx.store.find_doc(docno)
        if src_doc is None:
            op.red_flags.append("provenance_doc_unknown")
            continue
        at = ctx.issued_date or date.today()
        res = ctx.store.resolve(src_doc, src_path, at)
        ok = False
        if res is not None:
            source_ops = set(ctx.store.ops_from_source_node(res.node_id))
            if op.target_node is not None:
                # khớp khi op nguồn nhắm chính node đích HOẶC một TỔ TIÊN của nó
                # (TT06 thay toàn Điều 8 → op nhắm dieu:8; TT10 treo dieu:8/khoan:8)
                targets = {op.target_node}
                info = getattr(ctx.store, "node_info", lambda _x: None)(op.target_node)
                tgt_doc = (info or {}).get("doc_key") or op.target_doc_key
                tgt_path = (info or {}).get("path") or op.target_path or ""
                segs = tgt_path.split("/")
                for i in range(len(segs) - 1, 0, -1):
                    anc = ctx.store.resolve(tgt_doc, "/".join(segs[:i]), at) \
                        if tgt_doc else None
                    if anc is not None:
                        targets.add(anc.node_id)
                targeting: set = set()
                for t in targets:
                    targeting |= set(ctx.store.ops_targeting(t))
                ok = bool(source_ops & targeting)
            elif op.target_op is not None:
                ok = op.target_op in source_ops
        if not ok:
            op.red_flags.append("provenance_mismatch")           # R-13 → per-op + cờ đỏ


# ============================================================================
# API chính
# ============================================================================

def extract_ops(doc: ParsedDoc, ctx: ExtractionContext,
                gateway: Any = None) -> tuple[list[ProposedOp], list[ParsedNode]]:
    """Pipeline op extraction đầy đủ: rule → LLM → merge → resolve (+ birth nodes)."""
    ctx.scope_predicate = extract_scope_predicate(doc, ctx.effective_date)
    rule_ops = rule_extract(ctx)
    llm_ops = llm_extract(ctx, gateway)
    # hoàn thiện địa chỉ tương đối TRƯỚC merge — không thì 'khoản 1' của hai directive
    # lồng khác nhau (k6a vs k10a TT06) va chạm khóa merge và nuốt nhau
    for op in rule_ops + llm_ops:
        _complete_with_ancestor(op, ctx)
        if not op.provenance_mentions:
            op.provenance_mentions = _ancestor_mentions(op, ctx)
    ops = merge_ops(rule_ops, llm_ops, llm_enabled=gateway is not None)
    born = resolve_ops(ops, ctx)
    _apply_divergent_dates(ops, ctx)
    return ops, born


def _ancestor_mentions(op: ProposedOp, ctx: ExtractionContext) -> list[str]:
    """Ngoặc provenance nằm ở directive TỔ TIÊN (TT12 k6: '(đã được sửa đổi, bổ sung
    bởi điểm c, d khoản 6 Điều 1 TT06)' ở khoản cha, op ở điểm con)."""
    cur = ctx.doc.node_at(op.source_path) if op.source_path else None
    while cur is not None:
        mentions = _provenance_mentions(cur.full_text().split("“", 1)[0])
        if mentions:
            return mentions
        cur = ctx.doc.node_at(cur.parent_path) if cur.parent_path else None
    return []


def _apply_divergent_dates(ops: list[ProposedOp], ctx: ExtractionContext) -> None:
    """Hiệu lực phân kỳ (bẫy #10): 'Các quy định về X tại Điều N … có hiệu lực từ ngày D'
    → op liên quan mang valid_from=D + cờ ngày-cần-phân-loại (per-op — D-19).
    Hai dạng: (a) 'tại Điều N' — khớp theo source_path; (b) 'tại Thông tư này' —
    khớp theo TOPIC xuất hiện trong text của op (heuristic; cờ đỏ ép người duyệt)."""
    def flag(op: ProposedOp, d: date) -> None:
        op.valid_from = d
        if "divergent_effective_date" not in op.red_flags:
            op.red_flags.append("divergent_effective_date")

    for n in ctx.doc.nodes:
        if n.role != "effectivity":
            continue
        for m in re.finditer(
                r"[Cc]ác quy định về\s+([^.;\n]{2,120}?)\s+tại\s+"
                r"(Điều\s+\d+[a-zđ]?|Thông tư này|Luật này|Nghị định này)"
                r"[^.;\n]{0,80}?có hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+ngày\s+([^,;.]{4,40})",
                n.full_text()):
            topic, where, date_str = m.group(1), m.group(2), m.group(3)
            d = parse_vn_date("ngày " + date_str)
            if d is None:
                continue
            if where.lower().startswith("điều"):
                groups = parse_surface(where)
                if not groups or not groups[0].paths:
                    continue
                src_dieu = groups[0].paths[0]
                for op in ops:
                    if op.source_path and (op.source_path == src_dieu
                                           or op.source_path.startswith(src_dieu + "/")):
                        flag(op, d)
            else:
                # 'tại Thông tư này' — phân loại theo topic (ngữ nghĩa → cờ per-op bắt buộc)
                topic_l = topic.strip().lower()
                if len(topic_l) < 6:
                    continue
                for op in ops:
                    blob = " ".join(filter(None, (op.new_text, op.new_heading,
                                                  op.source_quote))).lower()
                    if topic_l in blob:
                        flag(op, d)
