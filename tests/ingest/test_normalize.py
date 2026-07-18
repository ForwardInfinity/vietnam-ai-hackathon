"""normalize.py — bẫy #1 (NFC), #2 (số hiệu vỡ), gộp header (R-3)."""
import unicodedata

from ingest.normalize import fix_docno_whitespace, merge_broken_headers, nfc, normalize


def test_nfc_normalizes_nfd_input():
    # 'Điều' ở dạng NFD (ký tự tổ hợp) phải về NFC (bẫy #1)
    nfd = unicodedata.normalize("NFD", "Điều 8. Những nhu cầu vốn")
    assert nfd != "Điều 8. Những nhu cầu vốn"
    assert nfc(nfd) == "Điều 8. Những nhu cầu vốn"


def test_docno_whitespace_patched_exact_case_from_spec():
    # ví dụ NGUYÊN VĂN trong 02§1: `32 /2026/TT- NHNN`
    assert fix_docno_whitespace("Số: 32 /2026/TT- NHNN") == "Số: 32/2026/TT-NHNN"


def test_docno_variants():
    assert fix_docno_whitespace("39 /2016/TT- NHNN") == "39/2016/TT-NHNN"
    assert fix_docno_whitespace("34/2016/NĐ-CP") == "34/2016/NĐ-CP"
    assert fix_docno_whitespace("32/2024/QH15") == "32/2024/QH15"
    assert fix_docno_whitespace("32 / 2024 / QH15") == "32/2024/QH15"
    assert fix_docno_whitespace("01/2019/NQ-HĐTP") == "01/2019/NQ-HĐTP"


def test_dates_not_mangled():
    # 'ngày 16/6/2010' KHÔNG phải số hiệu — không được vá
    s = "Luật Các tổ chức tín dụng ngày 16/6/2010 và tỷ lệ 30/80/2016"
    assert "16/6/2010" in fix_docno_whitespace(s)


def test_docno_broken_across_newline():
    s = "Số: 39/2016/TT-\nNHNN\nHà Nội"
    out = normalize(s)
    assert "39/2016/TT-NHNN" in out


def test_merge_broken_header_so_line():
    s = "Số: 39/2016/\nTT-NHNN\nkhác"
    assert "Số: 39/2016/TT-NHNN" in merge_broken_headers(s)


def test_normalize_idempotent():
    s = "Số: 39 /2016/TT- NHNN\r\nĐiều 1. Phạm vi"
    once = normalize(s)
    assert normalize(once) == once
