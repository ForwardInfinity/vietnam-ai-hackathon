"""citation.py — citation → edge có kiểu, 3 tầng (R-8..R-10, D-13, 02§5).

  (a) regex pinpoint + expand enumeration ("điểm a, b, c và đ khoản 1 Điều 39" → 4 edge)
      + gán kiểu theo cue tất định (ngoai_le/dinh_nghia/chuyen_tiep);
  (b) ^Căn cứ → tham_quyen MIỄN PHÍ bằng regex; "Luật X được sửa đổi bởi Luật Y"
      trong căn cứ → dst_norm (trỏ Norm, không trỏ artifact);
  (c) LLM (gateway role `extract`) resolve tham chiếu tương đối + gán kiểu edge còn
      lại — prompt CHỨA quy tắc binding 02§5.3 và context-stack omnibus 02§5.4.

Resolve qua alias tại ngày văn bản nguồn (R-9). Không resolve được → edge 3-đích-NULL
confidence 0 vào backlog (R-10). Ref theo mảng ("quy định của NHNN về …") → dst_norm,
KHÔNG cưỡng ép về unit. Ref nằm TRONG text được quote của node amending bị BỎ QUA —
nội dung đó chỉ sống qua op (D-05); F4 re-derive edge cho version mới bằng
`extract_citations_for_text`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from ingest.model import EdgeDraft, ParsedDoc, ParsedNode
from ingest.surface import RE_DOC_REF, RE_DOC_THIS, RefGroup, extract_docno, parse_surface
from ingest.tree_parser import parse_vn_date

logger = logging.getLogger("lawstate.ingest.citation")

RE_NGOAI_LE_CUE = re.compile(
    r"(trừ\s+(các\s+)?trường hợp|không áp dụng\s+(quy định\s+)?(tại|đối với)|ngoại trừ)",
    re.IGNORECASE)
RE_DINH_NGHIA_CUE = re.compile(
    r"(theo\s+quy định tại|quy định tại|theo quy định của|được hiểu theo|thực hiện theo)",
    re.IGNORECASE)

# ref theo mảng — không số hiệu → dst_norm (D-13, 02§5.2)
RE_CHU_DE = re.compile(
    r"quy định của\s+"
    r"(Ngân hàng Nhà nước(?: Việt Nam)?|NHNN|Chính phủ|pháp luật|Thống đốc[^,;.\n]{0,40})"
    r"\s+về\s+([^,;.\n]{4,110})",
    re.IGNORECASE)
RE_CHU_DE_VBPL = re.compile(          # "văn bản quy phạm pháp luật quy định về lãi suất…"
    r"văn bản quy phạm pháp luật\s+(?:quy định\s+)?về\s+([^,;.\n]{4,90})", re.IGNORECASE)
RE_CHU_DE_LAW_NAME = re.compile(      # dẫn Luật theo TÊN không số hiệu/không đơn vị → Norm
    r"(?:theo|phù hợp với|quy định của|căn cứ)\s+(Luật\s+[A-Za-zÀ-ỹ][^,;.\n0-9]{3,60}?)"
    r"(?=\s+và|\s*[,;.]|\s+tại)", re.IGNORECASE)

RE_FRONTIER = re.compile(
    r"(Basel(?:\s+[IVX]+)?|chuẩn mực\s+[^,;.\n]{0,40}quốc tế|điều ước quốc tế"
    r"|Moody'?s|Standard\s*&\s*Poor'?s?|S&P|Fitch)",
    re.IGNORECASE)

RE_AMENDED_BY = re.compile(
    r"(đã\s+)?được sửa đổi, bổ sung(\s+một số điều)?\s+(theo|bởi|tại)", re.IGNORECASE)

_QUOTE_SPAN = re.compile(r"[“][^”]*[”]|\"[^\"]*\"", re.S)


def quoted_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTE_SPAN.finditer(text)]


def _in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


RE_NGOAI_LE_LAW_KHAC = re.compile(
    r"trừ trường hợp\s+((?:luật|pháp luật|văn bản)[^,;.\n]{0,60}?(?:khác|liên quan)[^,;.\n]{0,40})",
    re.IGNORECASE)
RE_NGOAI_LE_LIST = re.compile(r"trừ\s+(?:các\s+)?(?:khoản|điểm|trường hợp)[^,;.\n]{0,20}sau\s*đây",
                              re.IGNORECASE)


@dataclass
class CitationContext:
    doc_key: str
    issued_date: date | None
    store: Any                              # alias.Store
    effective_date: date | None = None      # cho cohort chuyen_tiep
    chapter_target_doc: str | None = None   # omnibus: doc đích theo Chương (02§5.4)
    local_paths: dict[str, Any] = None      # type: ignore[assignment]  # path -> ParsedNode của doc ĐANG ingest

    def __post_init__(self) -> None:
        if self.local_paths is None:
            self.local_paths = {}


RE_OP_DIRECTIVE_START = re.compile(
    r"^(?:Sửa đổi, bổ sung|Sửa đổi|Bổ sung|Bãi bỏ|Thay thế|Ngưng hiệu lực|Đính chính)\b",
    re.IGNORECASE)


def _is_op_directive_node(node: ParsedNode) -> bool:
    """Node mở đầu bằng mệnh lệnh sửa đổi (kể cả khi không amending vì không quote —
    TT10 Đ1, TT12 Đ2): ref trong đó là ĐÍCH THAO TÁC, không phải dẫn chiếu áp dụng."""
    return bool(RE_OP_DIRECTIVE_START.match((node.heading or "").strip())
                or RE_OP_DIRECTIVE_START.match(node.body.strip())
                or node.role == "amending")


def _kind_from_cues(text: str, span_start: int, src: ParsedNode) -> tuple[str | None, float]:
    """Kiểu edge từ cue tất định quanh vị trí ref; None → cần LLM tầng (c)."""
    window = text[max(0, span_start - 90):span_start]
    if RE_NGOAI_LE_CUE.search(window):
        return "ngoai_le", 0.95
    if src.role == "transition":
        return "chuyen_tiep", 0.95
    if _is_op_directive_node(src):
        # ref trong mệnh lệnh op → edge tham_quyen (đích thao tác — nuôi where-used/
        # blast-radius, KHÔNG vào mandatory closure, KHÔNG kích definitional risk)
        return "tham_quyen", 0.8
    if RE_DINH_NGHIA_CUE.search(window):
        return "dinh_nghia", 0.9
    return None, 0.6


def resolve_group(group: RefGroup, ctx: CitationContext, src: ParsedNode,
                  in_quote: bool) -> tuple[str | None, bool]:
    """→ (doc_key đích | None nếu không xác định được, resolved_doc?).
    Binding 'Thông tư này' (02§5.3): TRONG quote → doc ĐÍCH của chương/op;
    NGOÀI quote → doc đang ingest."""
    if group.doc_this:
        if in_quote and ctx.chapter_target_doc:
            return ctx.chapter_target_doc, True
        return ctx.doc_key, True
    if group.doc_surface:
        docno = extract_docno(group.doc_surface)
        issued = parse_vn_date(group.doc_surface)
        title_hint = None
        if not docno and not issued:
            title_hint = group.doc_surface
        found = ctx.store.find_doc(docno, issued=issued, title_hint=title_hint)
        return (found, found is not None)
    # ref trần không doc → cùng doc; trong omnibus chương "Sửa đổi TT X" → X (02§5.4)
    if ctx.chapter_target_doc:
        return ctx.chapter_target_doc, True
    return ctx.doc_key, True


def _relative_paths(group: RefGroup, src: ParsedNode) -> list[str]:
    """Ghép ref tương đối ('khoản 6, 7 Điều này' / bare 'khoản 3') vào path node nguồn."""
    out = []
    src_parts = {p.rsplit("/", 1)[-1].split(":")[0]: p for p in _prefixes(src.path)}
    for path in group.paths:
        top = path.split("/", 1)[0].split(":")[0]
        if top in ("dieu", "phuluc"):
            out.append(path)
            continue
        container = None
        if group.relative_container and group.relative_container in src_parts:
            container = src_parts[group.relative_container]
        elif top == "khoan" and "dieu" in src_parts:
            container = src_parts["dieu"]
        elif top == "diem" and "khoan" in src_parts:
            container = src_parts["khoan"]
        elif top == "tiet" and "diem" in src_parts:
            container = src_parts["diem"]
        out.append(f"{container}/{path}" if container else path)
    return out


def _prefixes(path: str) -> list[str]:
    segs = path.split("/")
    return ["/".join(segs[:i + 1]) for i in range(len(segs))]


# ============================================================================
# Tầng (b): ^Căn cứ → tham_quyen
# ============================================================================

def extract_can_cu_edges(doc: ParsedDoc, ctx: CitationContext,
                         preamble: ParsedNode | None) -> list[EdgeDraft]:
    edges: list[EdgeDraft] = []
    src = preamble
    if src is None:
        return edges
    for line in doc.can_cu_lines:
        docno = extract_docno(line)
        m_arr = RE_CHU_DE.search(line) if not docno else None
        if m_arr:
            # "Căn cứ các quy định của NHNN về hoạt động cho vay…" — căn cứ theo MẢNG
            # → chu_de trỏ Norm (QT nội bộ SHB cite mảng ngay phần căn cứ)
            norm_id = _find_norm_by_topic(ctx.store, m_arr.group(2).strip())
            edges.append(EdgeDraft(
                src_path=src.path, src_node=src.id, kind="chu_de", raw_citation=line,
                dst_norm=norm_id, resolved_against=ctx.issued_date,
                confidence=0.9 if norm_id else 0.0))
            continue
        issued = parse_vn_date(line) if not docno else None
        title_hint = None
        if not docno:
            m = re.match(r"Căn cứ\s+(.{4,90}?)(?:\s+ngày|\s+số|;|$)", line, re.IGNORECASE)
            if m:
                title_hint = m.group(1).strip()
        found = ctx.store.find_doc(docno, issued=issued, title_hint=title_hint)
        norm_id = ctx.store.norm_for_doc(found) if found else None
        edges.append(EdgeDraft(
            src_path=src.path, src_node=src.id, kind="tham_quyen", raw_citation=line,
            dst_doc_key=found, dst_norm=norm_id,
            resolved_against=ctx.issued_date,
            confidence=1.0 if norm_id is not None else 0.0))
        # "Luật X ... đã được sửa đổi, bổ sung ... bởi Luật Y" → vẫn MỘT edge trỏ Norm
        # (danh tính xuyên sửa đổi); docno của Y chỉ để backlog biết chuỗi.
    return edges


# ============================================================================
# Tầng (a): pinpoint regex + cue kinds
# ============================================================================

def extract_pinpoint_edges(doc: ParsedDoc, ctx: CitationContext) -> tuple[list[EdgeDraft], list[dict]]:
    """→ (edges resolved/unresolved, leftovers cho tầng LLM (c))."""
    edges: list[EdgeDraft] = []
    leftovers: list[dict] = []
    for node in doc.nodes:
        if node.level == "preamble":
            # preamble vẫn quét pinpoint/chu_de (công văn đính chính, SHB doc dẫn mảng
            # ngay phần mở đầu) — nhưng BỎ các dòng Căn cứ (đã thành tham_quyen R-8b)
            text = "\n".join(ln for ln in node.body.split("\n")
                             if not ln.strip().startswith("Căn cứ"))
        else:
            text = node.full_text()
        spans = quoted_spans(text)
        # Edge dẫn xuất theo PHIÊN BẢN node (D-13): version 1 của node amending CHỨA
        # text quote → ref trong quote cũng thành edge (node không retrievable nên không
        # lọt closure — D-05 vẫn giữ); binding "Thông tư này" trong quote → doc ĐÍCH
        # (02§5.3) qua chapter_target_doc tính cho từng node amending.
        skip_quotes = False
        saved_chapter = ctx.chapter_target_doc
        if node.role == "amending":
            ctx.chapter_target_doc = _amended_doc_for_node(node, doc, ctx) or saved_chapter
        for group in parse_surface(text):
            in_quote = _in_spans(group.span[0], spans)
            if skip_quotes and in_quote:
                continue        # text được quote chỉ sống qua op (D-05)
            dst_doc, doc_ok = resolve_group(group, ctx, node, in_quote)
            kind, kconf = _kind_from_cues(text, group.span[0], node)
            paths = group.paths if (group.doc_surface or group.doc_this) \
                else _relative_paths(group, node)
            for path in paths:
                if kind is None:
                    leftovers.append({"node": node, "raw": group.raw, "path": path,
                                      "dst_doc": dst_doc, "confidence": kconf})
                    continue
                edges.append(_make_edge(node, kind, group.raw, dst_doc if doc_ok else None,
                                        path, ctx, kconf))
        # chu_de: ref theo mảng → dst_norm, KHÔNG cưỡng ép về unit (R-10)
        chu_de_hits: list[tuple[int, str, str]] = []
        for m in RE_CHU_DE.finditer(text):
            chu_de_hits.append((m.start(), m.group(0), m.group(2)))
        for m in RE_CHU_DE_VBPL.finditer(text):
            chu_de_hits.append((m.start(), m.group(0), m.group(1)))
        for m in RE_CHU_DE_LAW_NAME.finditer(text):
            if extract_docno(m.group(1)) is None:
                chu_de_hits.append((m.start(), m.group(0), m.group(1)))
        for pos, raw, topic in chu_de_hits:
            if skip_quotes and _in_spans(pos, spans):
                continue
            norm_id = _find_norm_by_topic(ctx.store, topic.strip())
            edges.append(EdgeDraft(
                src_path=node.path, src_node=node.id, kind="chu_de",
                raw_citation=raw.strip(), dst_norm=norm_id,
                resolved_against=ctx.issued_date,
                confidence=0.9 if norm_id else 0.0))
        # doc-ref đứng một mình (không đơn vị): out-of-corpus → frontier (D-13 "ngoài
        # kho"); in-corpus → chu_de mức văn bản (norm chưa ratify → backlog)
        taken_spans = [g.span for g in parse_surface(text)]
        for m in RE_DOC_REF.finditer(text):
            if any(a <= m.start() < b for a, b in taken_spans):
                continue                      # đã là doc_surface của một pinpoint group
            if skip_quotes and _in_spans(m.start(), spans):
                continue
            docno = extract_docno(m.group(0))
            if docno is None or docno == ctx.doc_key:
                continue
            in_corpus = ctx.store.find_doc(docno)
            if in_corpus is None:
                edges.append(EdgeDraft(
                    src_path=node.path, src_node=node.id, kind="frontier",
                    raw_citation=m.group(0)[:200], frontier_ref=docno,
                    resolved_against=ctx.issued_date, confidence=0.5))
            else:
                edges.append(EdgeDraft(
                    src_path=node.path, src_node=node.id, kind="chu_de",
                    raw_citation=m.group(0)[:200],
                    dst_norm=ctx.store.norm_for_doc(in_corpus),
                    resolved_against=ctx.issued_date,
                    confidence=0.9 if ctx.store.norm_for_doc(in_corpus) else 0.0))
        # ngoại lệ không địa chỉ: "trừ trường hợp luật khác có liên quan quy định khác"
        # (Đ468 BLDS) → ngoai_le trỏ frontier; "trừ các khoản sau đây" → ngoai_le tới con
        for m in RE_NGOAI_LE_LAW_KHAC.finditer(text):
            if skip_quotes and _in_spans(m.start(), spans):
                continue
            edges.append(EdgeDraft(
                src_path=node.path, src_node=node.id, kind="ngoai_le",
                raw_citation=m.group(0)[:200], frontier_ref=m.group(1).strip()[:120],
                resolved_against=ctx.issued_date, confidence=0.7))
        if RE_NGOAI_LE_LIST.search(text):
            for child in doc.children(node.path):
                edges.append(EdgeDraft(
                    src_path=node.path, src_node=node.id, kind="ngoai_le",
                    raw_citation=f"trừ các khoản sau đây → {child.path}",
                    dst_doc_key=ctx.doc_key, dst_path=child.path, dst_node=child.id,
                    resolved_against=ctx.issued_date, confidence=0.85))
        for m in RE_FRONTIER.finditer(text):
            if skip_quotes and _in_spans(m.start(), spans):
                continue
            edges.append(EdgeDraft(
                src_path=node.path, src_node=node.id, kind="frontier",
                raw_citation=m.group(0), frontier_ref=m.group(1),
                resolved_against=ctx.issued_date, confidence=0.9))
        # điều khoản chuyển tiếp grandfather → self-edge chuyen_tiep mang COHORT
        # (D-29 cần "chuyen_tiep khớp cohort"; cohort không phải node/norm nên không
        # có đích ngoài — dst = chính clause để không rơi vào backlog unresolved)
        m_gf = RE_GRANDFATHER_CLAUSE.search(text)
        if m_gf:
            eff = _doc_effective_date(ctx)
            cohort = f"COHORT:contract_signed_before={eff.isoformat()}" if eff else "COHORT:?"
            edges.append(EdgeDraft(
                src_path=node.path, src_node=node.id, kind="chuyen_tiep",
                raw_citation=f"{cohort} · {m_gf.group(0)[:160]}",
                dst_doc_key=ctx.doc_key, dst_path=node.path, dst_node=node.id,
                resolved_against=ctx.issued_date, confidence=0.9))
        ctx.chapter_target_doc = saved_chapter
    return edges, leftovers


def _amended_doc_for_node(node: ParsedNode, doc: ParsedDoc, ctx: CitationContext) -> str | None:
    """Doc đang bị node amending này sửa: Chương (omnibus 02§5.4) → heading tổ tiên → title."""
    for chap in reversed(node.chapter_ctx):
        d = extract_docno(chap)
        if d:
            return ctx.store.find_doc(d) or d
    cur: ParsedNode | None = node
    while cur is not None:
        d = extract_docno(cur.heading or "")
        if d and d != ctx.doc_key:
            return ctx.store.find_doc(d) or d
        cur = doc.node_at(cur.parent_path) if cur.parent_path else None
    title_docs = [d for d in dict.fromkeys(
        __import__("ingest.surface", fromlist=["RE_DOCNO"]).RE_DOCNO.findall(doc.title or ""))
        if d != ctx.doc_key]
    if len(title_docs) == 1:
        return ctx.store.find_doc(title_docs[0]) or title_docs[0]
    return None


RE_GRANDFATHER_CLAUSE = re.compile(
    r"(?:hợp đồng|thỏa thuận|giao dịch)[^.;]{0,160}?(?:được\s+)?"
    r"(?:ký kết|giao kết|ký|xác lập|thực hiện)\s+trước\s+ngày",
    re.IGNORECASE)


def _doc_effective_date(ctx: CitationContext) -> date | None:
    if ctx.effective_date is not None:
        return ctx.effective_date
    meta = ctx.store.doc_meta(ctx.doc_key) or {}
    eff = meta.get("effective_date")
    if eff is None:
        return None
    return eff if isinstance(eff, date) else date.fromisoformat(str(eff))


# ---- dinh_nghia theo TERM (02§5.2): term được giải thích tại điều 'Giải thích từ ngữ'
# → node chứa term nhận edge tới node định nghĩa (input closure D-29: 'dinh_nghia cho
# term có mặt'). Định nghĩa bind trong phạm vi văn bản định nghĩa ("Trong Thông tư
# này, các từ ngữ dưới đây…") → chỉ nối same-doc.

RE_TERM_DEF = re.compile(
    r"^(?P<term>[^.;\n]{2,70}?)\s+(?:là|được hiểu là|bao gồm)\s", re.IGNORECASE)


def extract_term_definition_edges(doc: ParsedDoc, ctx: CitationContext) -> list[EdgeDraft]:
    terms: list[tuple[str, ParsedNode]] = []
    for n in doc.nodes:
        if n.role != "definition" or n.level not in ("khoan", "diem"):
            continue
        m = RE_TERM_DEF.match(n.body.strip())
        if m:
            term = m.group("term").strip()
            if len(term) >= 6:                    # tránh term quá ngắn gây nhiễu
                terms.append((term.lower(), n))
    if not terms:
        return []
    edges: list[EdgeDraft] = []
    for node in doc.nodes:
        if node.level == "preamble" or node.role in ("definition", "amending"):
            continue
        low = node.full_text().lower()
        for term, def_node in terms:
            if term in low:
                edges.append(EdgeDraft(
                    src_path=node.path, src_node=node.id, kind="dinh_nghia",
                    raw_citation=f"term: {term}", dst_doc_key=ctx.doc_key,
                    dst_path=def_node.path, dst_node=def_node.id,
                    resolved_against=ctx.issued_date, confidence=0.7))
    return edges


def _find_norm_by_topic(store: Any, topic: str) -> Any:
    norms = getattr(store, "norms", None)
    if isinstance(norms, dict):
        for key, nid in norms.items():
            meta = store.doc_meta(key) or {}
            topics = [str(meta.get("norm_topic", "")).lower()]
            if any(topic.lower()[:25] in t or t and t in topic.lower() for t in topics if t):
                return nid
    return None


def _make_edge(src: ParsedNode, kind: str, raw: str, dst_doc: str | None, path: str,
               ctx: CitationContext, conf: float) -> EdgeDraft:
    e = EdgeDraft(src_path=src.path, src_node=src.id, kind=kind, raw_citation=raw,
                  dst_doc_key=dst_doc, dst_path=path,
                  resolved_against=ctx.issued_date, confidence=conf)
    if dst_doc == ctx.doc_key and path in ctx.local_paths:
        e.dst_node = ctx.local_paths[path].id   # ref nội bộ doc đang ingest (chưa có alias)
        return e
    if dst_doc is not None:
        res = ctx.store.resolve(dst_doc, path, ctx.issued_date or DATE_FALLBACK)
        if res is not None:
            e.dst_node = res.node_id
        else:
            e.confidence = 0.0          # unresolved → backlog (R-10)
    else:
        e.confidence = 0.0
    return e


DATE_FALLBACK = date(2100, 1, 1)


# ============================================================================
# Tầng (c): LLM resolve tham chiếu tương đối + gán kiểu còn lại
# ============================================================================

LLM_EDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_path": {"type": "string"},
                    "raw_citation": {"type": "string"},
                    "kind": {"type": "string",
                             "enum": ["dinh_nghia", "tham_quyen", "ngoai_le",
                                      "chu_de", "chuyen_tiep", "frontier"]},
                    "target_doc": {"type": ["string", "null"]},
                    "target_path": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["node_path", "raw_citation", "kind",
                             "target_doc", "target_path", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["edges"],
    "additionalProperties": False,
}

LLM_EDGE_SYSTEM = """Bạn phân loại KIỂU tham chiếu pháp lý và resolve tham chiếu tương đối \
trong văn bản pháp quy Việt Nam. Trả về JSON đúng schema.

KIỂU edge (chọn một): dinh_nghia (dẫn chiếu quy định/định nghĩa để áp dụng), ngoai_le \
("trừ trường hợp…" — ngoại lệ của quy tắc), chuyen_tiep (điều khoản chuyển tiếp trỏ cohort), \
chu_de (dẫn theo MẢNG chủ đề, không số hiệu — vd "quy định của NHNN về hoạt động cho vay"), \
tham_quyen (căn cứ ban hành), frontier (chuẩn ngoài kho: Basel, điều ước quốc tế).

QUY TẮC BINDING (02§5.3 — bắt buộc):
- "Thông tư này/Điều này/Khoản này" nằm TRONG text được quote (“…”) của điều khoản sửa đổi \
→ bind vào văn bản ĐÍCH được sửa (ví dụ Điều 7a chèn vào Thông tư 09/2019 nói "Thông tư này" \
= 09/2019, KHÔNG phải thông tư sửa đổi).
- Nằm NGOÀI quote → bind vào văn bản ĐANG sửa đổi (văn bản nguồn).

OMNIBUS context-stack (02§5.4 — bắt buộc): trong văn bản sửa NHIỀU văn bản chia theo \
Chương ("Chương II — Sửa đổi Thông tư X"), tham chiếu trần "Điều 9" bên trong chương đó \
= Điều 9 của X (theo Chương gần nhất), KHÔNG phải của văn bản đang ingest.

target_path dùng dạng chuẩn: 'dieu:8/khoan:2/diem:a'. Không chắc target → target_doc=null, \
target_path=null, confidence ≤ 0.3. KHÔNG bịa số hiệu văn bản."""


def llm_classify_leftovers(leftovers: list[dict], ctx: CitationContext,
                           gateway: Any) -> list[EdgeDraft]:
    if not leftovers or gateway is None:
        # thoái lui tất định: cue 'quy định tại' đã hụt → dinh_nghia confidence thấp
        return [_make_edge(lo["node"], "dinh_nghia", lo["raw"], lo["dst_doc"], lo["path"],
                           ctx, min(lo.get("confidence", 0.6), 0.6)) for lo in leftovers]
    payload = [{"node_path": lo["node"].path, "sentence": _sentence_around(lo),
                "citation": lo["raw"], "chapter_context": lo["node"].chapter_ctx}
               for lo in leftovers]
    user = (f"Văn bản nguồn: {ctx.doc_key}\n"
            f"Các văn bản trong kho: {', '.join(ctx.store.doc_keys())}\n"
            f"Tham chiếu cần phân loại (JSON):\n{payload}")
    try:
        out = gateway.complete_json(role="extract", system=LLM_EDGE_SYSTEM, user=user,
                                    schema=LLM_EDGE_SCHEMA)
    except Exception as exc:                                 # gateway lỗi → thoái lui rule
        logger.warning("citation LLM layer lỗi (%s) — thoái lui cue tất định", exc)
        return llm_classify_leftovers(leftovers, ctx, None)
    by_path = {lo["node"].path: lo["node"] for lo in leftovers}
    edges = []
    for item in out.get("edges", []):
        node = by_path.get(item["node_path"])
        if node is None:
            continue
        dst_doc = item.get("target_doc")
        if dst_doc is not None and ctx.store.find_doc(dst_doc) is None:
            dst_doc = None                                   # không bịa doc ngoài kho
        edges.append(_make_edge(node, item["kind"], item["raw_citation"], dst_doc,
                                item.get("target_path") or "", ctx,
                                float(item.get("confidence", 0.5))))
    return edges


def _sentence_around(lo: dict) -> str:
    text = lo["node"].full_text()
    idx = text.find(lo["raw"][:40])
    lo_i = max(0, idx - 200)
    return text[lo_i: idx + len(lo["raw"]) + 200]


# ============================================================================
# API chính
# ============================================================================

def extract_edges(doc: ParsedDoc, ctx: CitationContext,
                  gateway: Any = None) -> list[EdgeDraft]:
    ctx.local_paths = {n.path: n for n in doc.nodes}
    preamble = doc.node_at("preamble")
    edges = extract_can_cu_edges(doc, ctx, preamble)
    pin, leftovers = extract_pinpoint_edges(doc, ctx)
    edges.extend(pin)
    edges.extend(extract_term_definition_edges(doc, ctx))
    edges.extend(llm_classify_leftovers(leftovers, ctx, gateway))
    return edges


def extract_citations_for_text(text: str, src_node_id: Any, src_path: str,
                               ctx: CitationContext, src_role: str = "rule",
                               src_version: int = 1) -> list[EdgeDraft]:
    """Cho F4 re-derive edge theo PHIÊN BẢN node sau replay (D-13)."""
    fake = ParsedNode(level="dieu", label="", path=src_path, seq=0, body=text)
    fake.id = src_node_id
    fake.role = src_role
    doc = ParsedDoc(doc_key=ctx.doc_key, title=None, issued_date=ctx.issued_date,
                    effective_date=None, nodes=[fake])
    out = []
    for e in extract_edges(doc, ctx):
        e.src_version = src_version
        out.append(e)
    return out
