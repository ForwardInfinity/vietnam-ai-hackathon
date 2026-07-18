"""tree_parser.py — regex state machine THUẦN theo grammar 02§1 (D-16). KHÔNG LLM.

Cây: Phần → Chương → Mục → (Tiểu mục) → Điều → Khoản → Điểm → Tiết; Phụ lục là
node hạng nhất. Chương/Mục là container (KHÔNG phải node) nhưng được giữ làm
chapter_ctx cho omnibus (02§5.4). Text được quote trong văn bản sửa đổi KHÔNG
sinh cấu trúc — quote-depth tracker chặn (bẫy contamination nguồn).

Exit test R-4: đếm dieu/khoan/diem/tiet/phuluc khớp corpus/manifest.json 100%.
"""
from __future__ import annotations

import re
from datetime import date

from ingest.model import ParsedDoc, ParsedNode

# --- mẫu nhận dạng (line-anchored, chạy SAU normalize) ------------------------

RE_PHAN = re.compile(r"^Phần\s+(thứ\s+\S+|[IVXLCDM]+|\d+)\b", re.IGNORECASE)
RE_CHUONG = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\s*[\.:]?\s*(.*)$")
RE_MUC = re.compile(r"^Mục\s+(\d+|[IVXLCDM]+)\s*[\.:]?\s*(.*)$")
RE_TIEU_MUC = re.compile(r"^Tiểu\s*mục\s+(\d+)\s*[\.:]?\s*(.*)$")
RE_DIEU = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*[\.:]?\s*(.*)$")
RE_KHOAN = re.compile(r"^(\d{1,3}[a-zđ]?)\.\s*(.*)$")           # '2.' trần → body ở dòng sau
RE_DIEM = re.compile(r"^([a-zđ][0-9]?)\)\s*(.*)$")               # 'b)' trần hợp lệ (NQ01)
RE_TIET_PAREN = re.compile(r"^\(([ivxlcdm]+)\)\s*(.*)$")          # (iii) …
RE_TIET_BARE = re.compile(r"^([ivxlcdm]{2,})\)\s*(.*)$")          # iii) … (≥2 ký tự — 'i)' đơn là điểm)
RE_TIET_MIXED = re.compile(r"^([a-zđ])\s*\(\s*([ivxlcdm]+)\s*\)\s*(.*)$")  # a(iii) …
RE_PHULUC = re.compile(r"^Phụ\s*lục\s*(?:số\s*)?([0-9IVXLCDM]+[a-zđ]?)?\s*[\.:]?\s*(.*)$",
                       re.IGNORECASE)

RE_CAN_CU = re.compile(r"^Căn\s+cứ\b", re.IGNORECASE)
RE_SO_HIEU = re.compile(r"^Số\s*:\s*([\w./-]+)")
RE_DATE = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})")
RE_DATE_SLASH = re.compile(r"ngày\s+(\d{1,2})/(\d{1,2})/(\d{4})")
# CHỈ các marker chắc chắn mở khối chữ ký — KHÔNG dùng chức danh trần ("THỐNG ĐỐC
# NGÂN HÀNG NHÀ NƯỚC" còn là dòng thẩm quyền trong preamble Quyết định)
RE_SIGNOFF = re.compile(r"^(Nơi nhận\s*:|KT\.\s|TM\.\s|TL\.\s|XÁC THỰC VĂN BẢN)")

RE_EFFECT_HEADING = re.compile(r"(hiệu lực|điều khoản thi hành)", re.IGNORECASE)


def _quote_delta(line: str) -> int:
    """Biến thiên depth ngoặc kép cong trên một dòng."""
    return line.count("“") - line.count("”")


class _QuoteTracker:
    """Theo dõi trạng thái trong/ngoài text được quote (“…” lồng được; "…" toggle).
    Dòng bắt đầu bằng ngoặc mở cũng tính là trong-quote với mục đích chặn cấu trúc."""

    def __init__(self) -> None:
        self.curly_depth = 0
        self.straight_open = False

    def line_starts_in_quote(self, line: str) -> bool:
        s = line.lstrip()
        return (self.curly_depth > 0 or self.straight_open
                or s.startswith("“") or s.startswith('"'))

    def feed(self, line: str) -> None:
        self.curly_depth = max(0, self.curly_depth + _quote_delta(line))
        if line.count('"') % 2 == 1:
            self.straight_open = not self.straight_open


def parse_vn_date(text: str) -> date | None:
    m = RE_DATE.search(text) or RE_DATE_SLASH.search(text)
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def strip_quoted_new_text(block: str) -> str:
    """Strip ngoặc kép + dấu chấm sau ngoặc đóng của text được quote (02§1)."""
    s = block.strip()
    if s.endswith("”.") or s.endswith('".'):
        s = s[:-1]
    if (s.startswith("“") and s.endswith("”")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1]
    return s.strip()


_ROMAN = set("ivxlcdm")


def _next_letter(label: str) -> str | None:
    """Điểm kế tiếp trong bảng chữ cái TIẾNG VIỆT: …c, d, đ, e… (02§1)."""
    vn = "aăâbcdđeêghiklmnoôơpqrstuưvxy"
    base = label[0]
    i = vn.find(base)
    return vn[i + 1] if 0 <= i < len(vn) - 1 else None


class _Builder:
    def __init__(self) -> None:
        self.nodes: list[ParsedNode] = []
        self.seq = 0
        self.chapter_ctx: list[str] = []
        self.cur: dict[str, ParsedNode | None] = {"dieu": None, "khoan": None,
                                                  "diem": None, "tiet": None,
                                                  "phuluc": None, "preamble": None}

    def push(self, level: str, label: str, heading: str | None, first_body: str) -> ParsedNode:
        label = label.lower()
        if level == "dieu":
            path, parent = f"dieu:{label}", None
            self.cur.update({"khoan": None, "diem": None, "tiet": None, "phuluc": None})
        elif level == "khoan":
            d = self.cur["dieu"]
            path = f"{d.path}/khoan:{label}" if d else f"khoan:{label}"
            parent = d.path if d else None
            self.cur.update({"diem": None, "tiet": None})
        elif level == "diem":
            k = self.cur["khoan"] or self.cur["dieu"]
            path = f"{k.path}/diem:{label}" if k else f"diem:{label}"
            parent = k.path if k else None
            self.cur.update({"tiet": None})
        elif level == "tiet":
            p = self.cur["diem"] or self.cur["khoan"] or self.cur["dieu"]
            path = f"{p.path}/tiet:{label}" if p else f"tiet:{label}"
            parent = p.path if p else None
        elif level == "phuluc":
            path, parent = f"phuluc:{label}", None
            self.cur.update({"dieu": None, "khoan": None, "diem": None, "tiet": None})
        else:  # preamble
            path, parent = "preamble", None
        self.seq += 1
        node = ParsedNode(level=level, label=label, path=path, seq=self.seq,  # type: ignore[arg-type]
                          heading=heading or None, body=first_body.strip(),
                          parent_path=parent, chapter_ctx=list(self.chapter_ctx))
        self.nodes.append(node)
        self.cur[level] = node
        return node

    def append_body(self, line: str) -> None:
        node = (self.cur["tiet"] or self.cur["diem"] or self.cur["khoan"]
                or self.cur["dieu"] or self.cur["phuluc"] or self.cur["preamble"])
        if node is None:
            return
        node.body = f"{node.body}\n{line}".strip() if node.body else line.strip()


def _classify_ambiguous_roman(label: str, b: _Builder) -> str:
    """'i)' / 'v)' / 'x)' đơn ký tự: điểm hay tiết? — theo dãy đang mở (02§1 note)."""
    diem, tiet = b.cur["diem"], b.cur["tiet"]
    if diem is not None and _next_letter(diem.label) == label:
        return "diem"
    if tiet is not None:
        return "tiet"
    if diem is not None and set(label) <= _ROMAN:
        # có điểm đang mở nhưng không phải kế tiếp (vd đang 'c' gặp 'i)') → tiết dưới điểm
        return "tiet"
    return "diem"


def parse_document(text: str) -> ParsedDoc:
    """State machine chính. `text` PHẢI đã qua normalize.normalize()."""
    lines = text.split("\n")
    b = _Builder()
    qt = _QuoteTracker()
    in_signoff = False
    header_zone = True          # trước node đầu tiên: header + căn cứ → preamble
    can_cu: list[str] = []
    header_lines: list[str] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        in_quote = qt.line_starts_in_quote(raw)
        qt.feed(raw)

        if not in_quote:
            # ---- Phụ lục mở lại thu thập sau khối chữ ký ----
            m = RE_PHULUC.match(line)
            if m and (in_signoff or b.cur["dieu"] is None or not b.cur["dieu"].body
                      or _looks_like_phuluc_start(line)):
                in_signoff = False
                header_zone = False
                label = (m.group(1) or str(_count_level(b, "phuluc") + 1)).lower()
                b.push("phuluc", label, m.group(2).strip() or None, "")
                continue
            if in_signoff:
                continue
            if RE_SIGNOFF.match(line):
                in_signoff = True
                continue

            # ---- containers (không phải node — chỉ cập nhật context) ----
            if RE_PHAN.match(line):
                header_zone = False
                continue
            m = RE_CHUONG.match(line)
            if m:
                header_zone = False
                b.chapter_ctx = [f"Chương {m.group(1)}. {m.group(2)}".strip().rstrip(".")]
                b._pending_container = "chuong"  # type: ignore[attr-defined]
                continue
            m = RE_MUC.match(line) or RE_TIEU_MUC.match(line)
            if m:
                header_zone = False
                base = b.chapter_ctx[:1]
                b.chapter_ctx = base + [line]
                b._pending_container = "muc"  # type: ignore[attr-defined]
                continue
            # dòng heading của Chương/Mục nằm dòng dưới ("Chương I\nQUY ĐỊNH CHUNG")
            if getattr(b, "_pending_container", None) and line.isupper():
                if b.chapter_ctx:
                    b.chapter_ctx[-1] = f"{b.chapter_ctx[-1]} {line}".strip()
                b._pending_container = None  # type: ignore[attr-defined]
                continue
            b._pending_container = None  # type: ignore[attr-defined]

            m = RE_DIEU.match(line)
            if m:
                header_zone = False
                b.push("dieu", m.group(1), m.group(2).strip() or None, "")
                continue
            if b.cur["dieu"] is not None and b.cur["phuluc"] is None:
                m = RE_KHOAN.match(line)
                if m:
                    b.push("khoan", m.group(1), None, m.group(2))
                    continue
                m = RE_TIET_MIXED.match(line)
                if m and b.cur["khoan"] is not None:
                    # dạng hỗn hợp a(iii): đảm bảo điểm 'a' tồn tại rồi treo tiết dưới nó
                    diem = b.cur["diem"]
                    if diem is None or diem.label != m.group(1):
                        b.push("diem", m.group(1), None, "")
                    b.push("tiet", m.group(2), None, m.group(3))
                    continue
                m = RE_TIET_PAREN.match(line) or RE_TIET_BARE.match(line)
                if m and b.cur["khoan"] is not None:
                    b.push("tiet", m.group(1), None, m.group(2))
                    continue
                m = RE_DIEM.match(line)
                if m and b.cur["khoan"] is not None:
                    label = m.group(1)
                    if len(label) == 1 and set(label) <= _ROMAN and label not in ("a",):
                        lv = _classify_ambiguous_roman(label, b)
                    else:
                        lv = "diem"
                    b.push(lv, label, None, m.group(2))
                    continue

        # ---- không phải marker cấu trúc (hoặc đang trong quote) ----
        if header_zone:
            if RE_CAN_CU.match(line):
                can_cu.append(line)
            header_lines.append(line)
            if b.cur["preamble"] is None:
                b.push("preamble", "", None, "")
            b.append_body(line)
        else:
            b.append_body(line)

    doc_key = _find_doc_key(header_lines)
    title = _find_title(header_lines)
    issued = _find_issued_date(header_lines)
    effective = _find_effective_date(b.nodes, issued)
    return ParsedDoc(doc_key=doc_key, title=title, issued_date=issued,
                     effective_date=effective, nodes=b.nodes,
                     can_cu_lines=can_cu, text=text)


def _looks_like_phuluc_start(line: str) -> bool:
    """'Phụ lục' đứng đầu dòng như tiêu đề khối (không phải câu nhắc trong body)."""
    return bool(re.match(r"^Phụ\s*lục\b", line, re.IGNORECASE)) and len(line) < 90


def _count_level(b: _Builder, level: str) -> int:
    return sum(1 for n in b.nodes if n.level == level)


def _find_doc_key(header_lines: list[str]) -> str | None:
    for ln in header_lines:
        m = RE_SO_HIEU.search(ln)
        if m:
            return m.group(1).rstrip(".")
    return None


def _find_title(header_lines: list[str]) -> str | None:
    """Title = dòng loại văn bản (THÔNG TƯ/NGHỊ ĐỊNH/LUẬT…) + các dòng chủ đề sau nó."""
    kinds = ("THÔNG TƯ", "NGHỊ ĐỊNH", "NGHỊ QUYẾT", "LUẬT", "QUYẾT ĐỊNH", "BỘ LUẬT",
             "QUY TRÌNH", "QUY ĐỊNH", "CHÍNH SÁCH", "MẪU", "CÔNG VĂN", "VĂN BẢN HỢP NHẤT")
    for i, ln in enumerate(header_lines):
        up = ln.strip().upper()
        if any(up == k or up.startswith(k + " ") for k in kinds):
            parts = [ln.strip()]
            for nxt in header_lines[i + 1:i + 4]:
                if RE_CAN_CU.match(nxt) or RE_SO_HIEU.search(nxt) or RE_DATE.search(nxt):
                    break
                parts.append(nxt.strip())
            return " ".join(parts)[:500]
    return None


def _find_issued_date(header_lines: list[str]) -> date | None:
    for ln in header_lines:
        if RE_CAN_CU.match(ln):
            continue                      # 'Căn cứ Luật … ngày 16 tháng 6 năm 2010' KHÔNG phải ngày ban hành
        d = parse_vn_date(ln)
        if d:
            return d
    return None


def _find_effective_date(nodes: list[ParsedNode], issued: date | None) -> date | None:
    """Ngày hiệu lực từ điều 'Hiệu lực thi hành' (thường điều áp chót/chót — 02§1):
    câu 'có hiệu lực (thi hành)? (kể )?từ ngày …'; 'kể từ ngày ký' → ngày ban hành."""
    for n in nodes:
        if n.level != "dieu":
            continue
        head = (n.heading or "")
        if not RE_EFFECT_HEADING.search(head):
            continue
        blob = n.full_text() + "\n" + "\n".join(
            c.body for c in nodes if c.parent_path == n.path)
        m = re.search(r"có hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+(ngày[^,;.]*)", blob)
        if m:
            if "ngày ký" in m.group(1):
                return issued
            d = parse_vn_date(m.group(1))
            if d:
                return d
    # fallback: câu hiệu lực nằm ngoài điều có heading chuẩn
    for n in nodes:
        m = re.search(r"(?:Thông tư|Nghị định|Luật|Quyết định|Nghị quyết|Văn bản)\s+này\s+"
                      r"có hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+(ngày[^,;.]*)", n.full_text())
        if m:
            if "ngày ký" in m.group(1):
                return issued
            d = parse_vn_date(m.group(1))
            if d:
                return d
    return None
