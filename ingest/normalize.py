"""normalize.py — chuẩn hóa văn bản TRƯỚC mọi tầng khác (R-3; bẫy 02§7 #1, #2).

Thứ tự bắt buộc: NFC ngay cửa vào → vá số hiệu chứa khoảng trắng lỗi → gộp
header vỡ dòng. Số hiệu phải lành lặn TRƯỚC tokenize (parser lẫn BM25 của F5
đều tiêu thụ text đã qua đây).
"""
from __future__ import annotations

import html as _html
import re
import unicodedata

# Loại văn bản hợp lệ trong số hiệu — guard để không vá nhầm phân số/ngày tháng.
# '32/2024/QH15' (không dash) và '39/2016/TT-NHNN' (dash) đều phải khớp.
_DOCNO_TYPES = ("TT", "TTLT", "NĐ", "ND", "QĐ", "QD", "NQ", "QH", "CT", "PL",
                "UBTVQH", "L", "TB", "VBHN")

# Số hiệu "lỏng": cho phép khoảng trắng (kể cả xuống dòng) quanh '/' và '-'.
_RE_DOCNO_LOOSE = re.compile(
    r"(\d{1,4})\s*/\s*(\d{4})\s*/\s*([A-ZĐ]{1,8}\d*)((?:\s*-\s*[A-ZĐ][A-ZĐ0-9]{0,11})?)"
)

_RE_WS = re.compile(r"[ \t\u00a0\u2007\u202f]+")

# Ranh giới block HTML → xuống dòng (corpus TVPL hay là HTML — D-43 né OCR).
_RE_HTML_BLOCK = re.compile(r"</?(p|div|tr|table|h[1-6]|li|ul|ol|br)[^>]*>", re.I)
_RE_HTML_TAG = re.compile(r"<[^>]+>")


def nfc(text: str) -> str:
    """Bẫy #1: văn bản VN trộn NFC/NFD — chuẩn NFC ngay cửa vào."""
    return unicodedata.normalize("NFC", text)


def strip_html(text: str) -> str:
    """Vét HTML tối thiểu (không thêm dependency): block tag → newline, bỏ tag còn lại."""
    if "<" not in text or ">" not in text:
        return text
    if not re.search(r"<(p|div|html|body|table|span|br)\b", text, re.I):
        return text
    text = _RE_HTML_BLOCK.sub("\n", text)
    text = _RE_HTML_TAG.sub(" ", text)
    return _html.unescape(text)


def _docno_type_ok(typ: str) -> bool:
    return any(typ.startswith(t) for t in _DOCNO_TYPES)


def fix_docno_whitespace(text: str) -> str:
    """Bẫy #2: `32 /2026/TT- NHNN` (khoảng trắng lỗi ngay trong bản gốc) → `32/2026/TT-NHNN`.
    Chỉ vá khi segment loại văn bản thuộc whitelist — không đụng ngày `16/6/2010`."""

    def _fix(m: re.Match[str]) -> str:
        num, year, typ, agency = m.group(1), m.group(2), m.group(3), m.group(4)
        if not _docno_type_ok(typ):
            return m.group(0)
        agency_clean = ""
        if agency:
            agency_clean = "-" + re.sub(r"[\s-]+", "", agency)
        return f"{num}/{year}/{typ}{agency_clean}"

    return _RE_DOCNO_LOOSE.sub(_fix, text)


def merge_broken_headers(text: str, scan_lines: int = 60) -> str:
    """Gộp header vỡ dòng (R-3): dòng 'Số:' bị cắt giữa chừng, dòng kết thúc bằng '-'
    nối tiếp ID ở dòng sau. Chỉ quét vùng đầu văn bản để không phá body."""
    lines = text.split("\n")
    head, tail = lines[:scan_lines], lines[scan_lines:]
    out: list[str] = []
    i = 0
    while i < len(head):
        line = head[i]
        nxt = head[i + 1] if i + 1 < len(head) else None
        if nxt is not None:
            stripped = line.rstrip()
            nxt_stripped = nxt.strip()
            # 'Số: 39/2016/TT-' + 'NHNN'  |  'Số: 39/2016/' + 'TT-NHNN'
            if (re.search(r"Số\s*:\s*\S*[/-]$", stripped)
                    and re.fullmatch(r"[A-ZĐ0-9-]{1,16}", nxt_stripped)):
                head[i + 1] = stripped + nxt_stripped
                i += 1
                continue
        out.append(line)
        i += 1
    return "\n".join(out + tail)


def collapse_spaces(text: str) -> str:
    """Khoảng trắng đặc biệt (nbsp…) → space; nén space kép; giữ nguyên newline."""
    return "\n".join(_RE_WS.sub(" ", ln).rstrip() for ln in text.split("\n"))


def normalize(text: str) -> str:
    """Pipeline chuẩn hóa đầy đủ theo R-3. Idempotent."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    text = nfc(text)
    text = strip_html(text)
    text = collapse_spaces(text)
    text = merge_broken_headers(text)
    text = fix_docno_whitespace(text)
    return text
