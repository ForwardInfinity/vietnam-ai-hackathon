"""Question compiler (S5.1, R-27, D-26) — phần không-commodity.

Câu hỏi tiếng Việt → CompiledQuestion{topic_terms, as_of, as_known, cohort,
audience, mode, pinpoint}. Thuần rule tất định (không LLM — lỗi demo phải debug
được từng regex):

  - Cụm thời gian ("năm 2022", "ngày 01/03/2024", "tại thời điểm giải ngân
    15/06/2023") → as_of + mode point_in_time; "hiện nay/hôm nay" → current.
  - "sắp tới / từ tháng sau / sắp có hiệu lực" → mode pending.
  - Địa chỉ cụ thể ("khoản 8 Điều 8 TT 39/2016/TT-NHNN") → pinpoint; "đã từng /
    trước đây" → mode history. Cả hai đi đường alias→timeline (D-27).
  - "hợp đồng ký <mốc>" / "chưa sửa đổi" / "khách hàng cá nhân" → cohort (DSL
    đóng D-25). KHÔNG BAO GIỜ chọn thầm nhánh — thiếu cohort thì tầng compose
    trả piecewise (D-04); compiler chỉ trích dữ kiện, không đoán.
  - Hỗ trợ câu KHÔNG DẤU (khách gõ "dieu kien vay von nam 2022").

Ưu tiên as_of: mốc trong câu hỏi > ctx.as_of (UI control) > hôm nay.
Audience đến từ session (không bao giờ từ text).
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from api.schemas import CompiledQuestion, Cohort
from retrieval.bm25 import DOC_NUM_RE, canonical_doc_num, tokenize

# ---------------------------------------------------------------------------
# Chuẩn hóa & helpers
# ---------------------------------------------------------------------------


def strip_diacritics(s: str) -> str:
    """'điều kiện' → 'dieu kien' (đ→d) — pattern matching cho câu không dấu."""
    s = s.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfd if not unicodedata.combining(ch))


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass
class SessionCtx:
    """Ngữ cảnh session do F6/API cấp — audience là quyền, không phải text."""
    audience: str = "employee"
    as_of: date | None = None
    as_known: datetime | None = None
    cohort: Cohort | None = None
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Patterns (soạn cả hai dạng: có dấu match trên lowercase, và match trên bản
# strip dấu). \b không ăn với tiếng Việt unicode ranh giới chữ 'đ' → dùng lookaround.
# ---------------------------------------------------------------------------

_D = r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})"          # dd/mm/yyyy
_D2 = r"(\d{1,2})-(\d{1,2})-(\d{4})"                       # dd-mm-yyyy
_DLONG = r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})"

RE_DATE_SLASH = re.compile(rf"(?:ngay\s+)?{_D}")
RE_DATE_DASH = re.compile(rf"(?:ngay\s+)?{_D2}")
RE_DATE_LONG = re.compile(_DLONG)
RE_MONTH = re.compile(r"thang\s+(\d{1,2})\s*(?:/|nam\s+)(\d{4})")
RE_YEAR = re.compile(r"nam\s+(\d{4})")

RE_CURRENT = re.compile(r"hien\s+nay|hien\s+tai|bay\s+gio|hom\s+nay|dang\s+ap\s+dung|moi\s+nhat")
RE_PENDING = re.compile(
    r"sap\s+toi|sap\s+co\s+hieu\s+luc|tu\s+thang\s+sau|thoi\s+gian\s+toi|"
    r"chuan\s+bi\s+co\s+hieu\s+luc|sap\s+thay\s+doi|se\s+thay\s+doi|sap\s+ban\s+hanh")
RE_HISTORY = re.compile(
    r"da\s+tung|tung\s+co\s+hieu\s+luc|da\s+bao\s+gio|co\s+bao\s+gio|"
    r"lich\s+su(?:\s+hieu\s+luc)?|truoc\s+day\s+(?:co|da)|qua\s+cac\s+thoi\s+ky")

# Cohort — neo vào 'ký' để không nuốt nhầm mốc thời gian của câu hỏi
_KY = r"ky(?:\s+ket)?"
RE_COHORT_SIGNED_BEFORE = re.compile(rf"{_KY}\s+truoc\s+(?:ngay\s+)?{_D}")
RE_COHORT_SIGNED_DATE = re.compile(rf"{_KY}\s+(?:ngay\s+)?{_D}")
RE_COHORT_SIGNED_MONTH = re.compile(rf"{_KY}\s+(?:trong\s+)?thang\s+(\d{{1,2}})\s*(?:/|nam\s+)(\d{{4}})")
RE_COHORT_SIGNED_YEAR = re.compile(rf"{_KY}\s+(?:trong\s+)?nam\s+(\d{{4}})")
RE_COHORT_NOT_AMENDED = re.compile(
    rf"(?:chua|khong)\s+(?:duoc\s+)?sua\s+doi(?:[,\s]+bo\s+sung)?(?:\s+(?:gi\s+)?(?:tu|sau)\s+(?:ngay\s+)?{_D})?")
RE_ENTITY_CA_NHAN = re.compile(r"khach\s+hang\s+(?:la\s+)?ca\s+nhan|ca\s+nhan\s+vay")
RE_ENTITY_PHAP_NHAN = re.compile(
    r"khach\s+hang\s+(?:la\s+)?(?:phap\s+nhan|doanh\s+nghiep|to\s+chuc)|doanh\s+nghiep\s+vay")

# Pinpoint address (chạy trên bản strip dấu; số hiệu đã canonical hóa trước)
_DOCREF = r"(?:cua\s+)?(?:thong\s+tu|nghi\s+dinh|luat|quyet\s+dinh|nghi\s+quyet|tt|nd|qd|nq)?\s*(?:so\s*)?"
RE_PINPOINT = re.compile(
    r"(?:(?:tiet\s+(?P<tiet>[a-z0-9()]+)\s+)?diem\s+(?P<diem>[a-z][0-9]?)\s+)?"
    r"(?:khoan\s+(?P<khoan>\d{1,2}[a-z]?)\s+)?"
    r"dieu\s+(?P<dieu>\d{1,3}[a-z]?)\s+"
    + _DOCREF + r"(?P<doc>docnum\d+|\d{1,4}(?![\d/]))")
RE_PINPOINT_PHULUC = re.compile(r"phu\s+luc\s+(?P<phuluc>[0-9ivx]+)\s+" + _DOCREF + r"(?P<doc>docnum\d+)")

_STOPWORDS = {
    "la", "gi", "the", "nao", "co", "khong", "duoc", "cua", "cho", "va", "hay",
    "hoac", "voi", "ve", "tai", "theo", "trong", "khi", "nhu", "den", "tu", "mot",
    "cac", "nhung", "toi", "anh", "chi", "em", "minh", "xin", "hoi", "cau", "muon",
    "biet", "nay", "do", "a", "o", "bao", "nhieu", "neu", "thi", "se", "van",
    "con", "hien", "ngay", "thang", "nam", "hom", "qua", "truoc", "sau",
    # LƯU Ý: KHÔNG đưa 'vay' vào đây — 'vậy' strip dấu trùng 'vay' (content word)
}


# ---------------------------------------------------------------------------
# Compile
# ---------------------------------------------------------------------------

def compile_question(question: str, ctx: SessionCtx | None = None,
                     known_doc_keys: list[str] | None = None,
                     today: date | None = None) -> CompiledQuestion:
    ctx = ctx or SessionCtx()
    today = today or date.today()

    q_nfc = unicodedata.normalize("NFC", question or "").strip()

    # 1) Bảo vệ số hiệu văn bản thành placeholder (trước MỌI pattern ngày/năm —
    #    "06/2023" trong "06/2023/TT-NHNN" không phải mốc thời gian).
    doc_nums: list[str] = []

    def _protect(m: re.Match[str]) -> str:
        doc_nums.append(canonical_doc_num(m.group(0)))
        return f" DOCNUM{len(doc_nums) - 1} "

    protected = DOC_NUM_RE.sub(_protect, q_nfc)
    low = strip_diacritics(protected).lower()

    # 2) Pinpoint address → alias path (D-27)
    pinpoint, low = _extract_pinpoint(low, doc_nums, known_doc_keys or [])

    # 3) Cohort (neo 'ký'/'sửa đổi'/'khách hàng …') — trích rồi CẮT khỏi text
    cohort, low = _extract_cohort(low, ctx.cohort)

    # 4) Thời gian & mode
    as_of, mode, low = _extract_time(low, ctx, today)

    # 5) History phrases thắng mode thời gian (đi đường timeline)
    if RE_HISTORY.search(low):
        mode = "history"
        low = RE_HISTORY.sub(" ", low)

    # 6) Topic terms: token hóa câu gốc (giữ dấu — BM25 index có dấu), loại
    #    stopword theo bản strip dấu, loại token thời gian đã tiêu thụ.
    topic_terms = _topic_terms(q_nfc, low)

    return CompiledQuestion(
        topic_terms=topic_terms,
        as_of=as_of,
        as_known=ctx.as_known,
        cohort=cohort,
        audience=ctx.audience,  # từ session — không bao giờ từ text
        mode=mode,
        pinpoint=pinpoint,
    )


# ---------------------------------------------------------------------------
# Từng tầng trích
# ---------------------------------------------------------------------------

def _resolve_shorthand(num: str, known_doc_keys: list[str]) -> str | None:
    """'thông tư 39' → '39/2016/TT-NHNN' nếu duy nhất trong kho nhìn thấy được."""
    hits = [dk for dk in known_doc_keys if dk.split("/")[0].lstrip("0") == num.lstrip("0")]
    return hits[0] if len(hits) == 1 else None


def _extract_pinpoint(low: str, doc_nums: list[str],
                      known_doc_keys: list[str]) -> tuple[str | None, str]:
    for rx in (RE_PINPOINT_PHULUC, RE_PINPOINT):
        m = rx.search(low)
        if not m:
            continue
        g = m.groupdict()
        doc = g.get("doc") or ""
        if doc.startswith("docnum"):
            doc_key = doc_nums[int(doc[len("docnum"):])]
        else:
            doc_key = _resolve_shorthand(doc, known_doc_keys)  # 'thông tư 39' trần
            if doc_key is None:
                continue  # không resolve được shorthand → không phải pinpoint chắc chắn
        if g.get("phuluc"):
            path = f"phuluc:{g['phuluc'].upper()}"
        else:
            path = f"dieu:{g['dieu']}"
            if g.get("khoan"):
                path += f"/khoan:{g['khoan']}"
            if g.get("diem"):
                path += f"/diem:{g['diem']}"
            if g.get("tiet"):
                path += f"/tiet:{g['tiet']}"
        low = low[: m.start()] + " " + low[m.end():]
        return f"{doc_key}#{path}", low
    return None, low


def _extract_cohort(low: str, override: Cohort | None) -> tuple[Cohort, str]:
    csb: date | None = None
    naooa: date | None = None
    entity: str | None = None

    m = RE_COHORT_SIGNED_BEFORE.search(low)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        csb = date(y, mo, d)  # 'ký trước X' — cận trên chính là X
        low = low.replace(m.group(0), " ")
    else:
        m = RE_COHORT_SIGNED_DATE.search(low)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            csb = date(y, mo, d) + timedelta(days=1)  # ký ĐÚNG ngày d ⇒ trước d+1
            low = low.replace(m.group(0), " ")
        else:
            m = RE_COHORT_SIGNED_MONTH.search(low)
            if m:
                mo, y = int(m.group(1)), int(m.group(2))
                nxt = date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)
                csb = nxt
                low = low.replace(m.group(0), " ")
            else:
                m = RE_COHORT_SIGNED_YEAR.search(low)
                if m:
                    csb = date(int(m.group(1)) + 1, 1, 1)
                    low = low.replace(m.group(0), " ")

    m = RE_COHORT_NOT_AMENDED.search(low)
    if m:
        if m.group(1):  # có mốc tường minh 'chưa sửa đổi từ ngày X'
            naooa = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        else:
            # 'chưa sửa đổi' không mốc = chưa từng sửa ⇒ thỏa MỌI scope
            # not_amended_on_or_after X (vì [X,∞) ⊆ [1900,∞) không có sửa đổi nào)
            naooa = date(1900, 1, 1)
        low = low.replace(m.group(0), " ")

    if RE_ENTITY_CA_NHAN.search(low):
        entity = "ca_nhan"
    elif RE_ENTITY_PHAP_NHAN.search(low):
        entity = "phap_nhan"

    cohort = Cohort(contract_signed_before=csb, not_amended_on_or_after=naooa,
                    entity_class=entity)
    if override is not None:  # session cohort override (form UI) thắng text
        merged = override.model_dump()
        for k, v in cohort.model_dump().items():
            if merged.get(k) is None and v is not None:
                merged[k] = v
        cohort = Cohort(**merged)
    return cohort, low


def _extract_time(low: str, ctx: SessionCtx, today: date) -> tuple[date, str, str]:
    """→ (as_of, mode, low đã cắt cụm thời gian). Ưu tiên: pending phrase >
    mốc trong câu > 'hiện nay' > ctx.as_of > today."""
    if RE_PENDING.search(low):
        low = RE_PENDING.sub(" ", low)
        return (ctx.as_of or today), "pending", low

    for rx, kind in ((RE_DATE_LONG, "dmy"), (RE_DATE_SLASH, "dmy"), (RE_DATE_DASH, "dmy")):
        m = rx.search(low)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            try:
                as_of = date(y, mo, d)
            except ValueError:
                continue
            low = low.replace(m.group(0), " ")
            return as_of, ("current" if as_of == today else "point_in_time"), low

    m = RE_MONTH.search(low)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            low = low.replace(m.group(0), " ")
            return _last_day(y, mo), "point_in_time", low

    m = RE_YEAR.search(low)
    if m:
        y = int(m.group(1))
        low = low.replace(m.group(0), " ")
        return date(y, 12, 31), "point_in_time", low

    if RE_CURRENT.search(low):
        # 'hiện nay' = “bây giờ” của phiên — as-of control (ctx) định nghĩa bây giờ ở đâu
        low = RE_CURRENT.sub(" ", low)
        as_of = ctx.as_of or today
        return as_of, ("current" if as_of == today else "point_in_time"), low

    if ctx.as_of is not None:
        return ctx.as_of, ("current" if ctx.as_of == today else "point_in_time"), low

    return today, "current", low


def _topic_terms(original: str, low_consumed: str) -> list[str]:
    """Token content words: bỏ stopword, bỏ token thời gian đã tiêu thụ, giữ số hiệu."""
    surviving = set(strip_diacritics(low_consumed).split())
    terms: list[str] = []
    for tok in tokenize(original):
        plain = strip_diacritics(tok).lower()
        if DOC_NUM_RE.fullmatch(tok.upper().replace("_", " ")) or "/" in tok:
            terms.append(tok)
            continue
        if plain in _STOPWORDS:
            continue
        # token thời gian/cohort đã bị cắt khỏi low_consumed → mọi mảnh của nó biến mất
        pieces = plain.split("_")
        if pieces and not any(p in surviving for p in pieces):
            continue
        if plain.isdigit() and plain not in surviving:
            continue
        terms.append(tok)
    # khử trùng lặp giữ thứ tự
    seen: set[str] = set()
    out = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
