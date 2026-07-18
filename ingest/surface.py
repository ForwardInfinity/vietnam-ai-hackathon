"""surface.py — ngữ pháp địa chỉ bề mặt dùng chung cho citation (R-8) và op resolver (R-12).

parse_surface("các điểm a, b, c và đ khoản 1 Điều 39 Thông tư số 39/2016/TT-NHNN")
→ một RefGroup có 4 path 'dieu:39/khoan:1/diem:{a,b,c,đ}' + doc_surface.

Expand enumeration (02§5.1): mỗi đơn vị liệt kê là MỘT ref riêng. Kết hợp trái→phải:
item cấp CAO đóng MỌI chain cấp thấp đang chờ ("điểm a khoản 1, điểm b khoản 2
Điều X" → (a,1,X), (b,2,X); "khoản 8, khoản 9 và khoản 10 Điều 8" → 3 ref).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LEVEL_RANK = {"tiet": 0, "diem": 1, "khoan": 2, "dieu": 3, "phuluc": 3}

RE_DOCNO = re.compile(r"\d{1,4}/\d{4}/[A-ZĐ]+\d*(?:-[A-ZĐ0-9]+)?"
                      r"|[A-ZĐ]{2,4}-[A-ZĐ]{2,4}-\d+/[A-ZĐ0-9]+"
                      r"|[A-ZĐ]{2,4}-\d+/\d{4}"
                      r"|\d{1,5}/(?:QĐ|QD|NQ|CT|TB)-[A-ZĐ0-9]{1,12}")   # '1058/QĐ-TTg' (không năm)

_DOC_KINDS = r"(?:Thông tư|Nghị định|Luật|Bộ luật|Quyết định|Nghị quyết|Quy trình|Quy định|Chính sách|Văn bản)"

# 'Thông tư số 39/2016/TT-NHNN' | 'Luật Các tổ chức tín dụng ngày 16 tháng 6 năm 2010'
RE_DOC_REF = re.compile(
    rf"{_DOC_KINDS}(?:\s+liên tịch)?[^,;.()\n]{{0,80}}?"
    rf"(?:số\s+(?:{RE_DOCNO.pattern})|(?:{RE_DOCNO.pattern})"
    rf"|ngày\s+\d{{1,2}}\s+tháng\s+\d{{1,2}}\s+năm\s+\d{{4}}|ngày\s+\d{{1,2}}/\d{{1,2}}/\d{{4}}"
    rf"|năm\s+(?:19|20)\d{{2}})",       # 'Bộ luật Dân sự năm 2015' — cite theo năm
    re.IGNORECASE)

RE_DOC_THIS = re.compile(rf"{_DOC_KINDS}\s+này", re.IGNORECASE)
RE_RELATIVE_UNIT = re.compile(r"(Điều|[Kk]hoản|[Đđ]iểm)\s+này")

# một item đơn vị: 'Điều 39' | 'khoản 1a' | 'điểm đ' | 'điểm a1' | 'tiết a(iii)' | 'Phụ lục 04'
_END = r"(?![a-zà-ỹđ0-9])"      # label không ăn sang chữ kế ('Điều này' KHÔNG phải label 'n')
_LABEL = rf"(?:số\s+)?[0-9]+[a-zđ]?[0-9]?{_END}|[a-zđ][0-9]?(?:\s*\([ivx]+\))?{_END}|\([ivx]+\)"
_CONT = rf"[0-9]+[a-zđ]?[0-9]?{_END}|[a-zđ][0-9]?(?:\s*\([ivx]+\))?{_END}|\([ivx]+\)"
_RE_UNIT_ITEM = re.compile(
    rf"(?:các\s+)?(Điều|điều|[Kk]hoản|[Đđ]iểm|[Tt]iết|Phụ\s*lục)\s+({_LABEL})"
    rf"((?:\s*[,;]\s*(?:và\s+|hoặc\s+)?(?:{_CONT})(?=[\s,;.)]|$)"
    rf"|\s*,?\s+(?:và|hoặc)\s+(?:{_CONT})(?=[\s,;.)]|$))*)")

_RE_ENUM_SPLIT = re.compile(r"\s*[,;]\s*|\s+(?:và|hoặc)\s+|^(?:và|hoặc)\s+")


def _kw_level(kw: str) -> str:
    k = kw.lower()
    if k.startswith("phụ"):
        return "phuluc"
    return {"điều": "dieu", "khoản": "khoan", "điểm": "diem", "tiết": "tiet"}[k]


@dataclass
class RefGroup:
    """Một nhóm tham chiếu đã expand: paths (tương đối trong doc đích) + doc đích."""
    paths: list[str] = field(default_factory=list)
    doc_surface: str | None = None      # nguyên văn phần văn bản đích (None = cùng doc)
    doc_this: bool = False              # 'Thông tư này' — binding theo 02§5.3
    relative_container: str | None = None  # 'dieu' ⟸ '… Điều này' | 'khoan' ⟸ '… khoản này'
    span: tuple[int, int] = (0, 0)
    raw: str = ""


def _norm_label(label: str) -> str:
    label = label.strip().lower().removeprefix("số ").strip()
    m = re.fullmatch(r"([a-zđ])\s*\(([ivx]+)\)", label)
    if m:
        return f"{m.group(1)}({m.group(2)})"        # tiết hỗn hợp a(iii)
    return label.strip("()")


def _expand_items(kw: str, first: str, rest: str) -> list[tuple[str, str]]:
    level = _kw_level(kw)
    labels = [_norm_label(first)]
    if rest:
        for piece in _RE_ENUM_SPLIT.split(rest.strip()):
            piece = piece.strip().strip(")")
            if piece and re.fullmatch(r"[0-9]+[a-zđ]?[0-9]?|[a-zđ][0-9]?|[ivx]+|[a-zđ]\([ivx]+\)",
                                      piece):
                labels.append(_norm_label(piece))
    out: list[tuple[str, str]] = []
    for lb in labels:
        m = re.fullmatch(r"([a-zđ])\(([ivx]+)\)", lb)
        if level in ("tiet", "diem") and m:
            # dạng hỗn hợp a(iii): tiết iii nằm dưới điểm a — thứ tự thấp→cao để _combine nối
            out.append(("tiet", m.group(2)))
            out.append(("diem", m.group(1)))
        else:
            out.append((level, lb))
    return out


def parse_surface(text: str) -> list[RefGroup]:
    """Tìm mọi nhóm tham chiếu pinpoint trong `text` và expand enumeration."""
    groups: list[RefGroup] = []
    pos = 0
    while True:
        m = _RE_UNIT_ITEM.search(text, pos)
        if not m:
            break
        items: list[list[tuple[str, str]]] = []
        start, end = m.start(), m.end()
        while m:
            items.append(_expand_items(m.group(1), m.group(2), m.group(3) or ""))
            end = m.end()
            nxt = _RE_UNIT_ITEM.search(text, end)
            if not nxt:
                break
            connector = text[end:nxt.start()]
            if nxt.start() - end > 30 or not re.fullmatch(
                    r"[\s,;]*(?:và|hoặc|của|cùng|tại|thuộc)?[\s,;]*", connector):
                break
            m = nxt

        group = _combine([it for chunk in items for it in chunk])
        seg_end = end
        tail = text[seg_end:seg_end + 200]
        lead_ws = len(tail) - len(tail.lstrip())
        tail_s = tail.lstrip()
        for pre in ("", "của "):
            if tail_s.startswith(pre):
                cand = tail_s[len(pre):]
                md = RE_DOC_REF.match(cand)
                if md:
                    group.doc_surface = md.group(0).strip()
                    seg_end += lead_ws + len(pre) + md.end()
                    break
                mthis = RE_DOC_THIS.match(cand)
                if mthis:
                    group.doc_this = True
                    seg_end += lead_ws + len(pre) + mthis.end()
                    break
                mrel = RE_RELATIVE_UNIT.match(cand)
                if mrel:
                    group.relative_container = _kw_level(mrel.group(1))
                    seg_end += lead_ws + len(pre) + mrel.end()
                    break
        group.span = (start, seg_end)
        group.raw = text[start:seg_end].strip()
        groups.append(group)
        pos = max(seg_end, end)
    return groups


def _combine(flat: list[tuple[str, str]]) -> RefGroup:
    """Item cấp cao đóng MỌI chain đang chờ có tip cấp thấp hơn; không nối được → chain mới."""
    chains: list[list[tuple[str, str]]] = []

    def rank(lv: str) -> int:
        return LEVEL_RANK[lv]

    for lv, lb in flat:
        extended = False
        for chain in chains:
            if rank(lv) > rank(chain[-1][0]):
                chain.append((lv, lb))
                extended = True
        if not extended:
            chains.append([(lv, lb)])

    paths: list[str] = []
    for chain in chains:
        ordered = sorted(chain, key=lambda x: -rank(x[0]))
        paths.append("/".join(f"{lv}:{lb}" for lv, lb in ordered))
    seen: set[str] = set()
    uniq = [p for p in paths if not (p in seen or seen.add(p))]
    return RefGroup(paths=uniq)


def extract_docno(surface: str) -> str | None:
    m = RE_DOCNO.search(surface)
    return m.group(0) if m else None


def path_top_level(path: str) -> str:
    return path.split("/", 1)[0]
