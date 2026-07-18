"""Verification nhóm 1 — tokenizer: số hiệu văn bản thành MỘT token (bẫy 02 §7.2)."""
import time

import pytest

from retrieval.bm25 import BM25Index, canonical_doc_num, extract_doc_numbers, tokenize

# Bảng test: (input, token canonical kỳ vọng)
DOC_NUM_TABLE = [
    ("39/2016/TT-NHNN", "39/2016/TT-NHNN"),
    ("34/2016/NĐ-CP", "34/2016/NĐ-CP"),
    ("32/2024/QH15", "32/2024/QH15"),
    ("01/2019/NQ-HĐTP", "01/2019/NQ-HĐTP"),
    # dạng LỖI khoảng trắng ngay trong bản gốc — phải vá thành 1 token
    ("32 /2026/TT- NHNN", "32/2026/TT-NHNN"),
    ("39/2016/TT -NHNN", "39/2016/TT-NHNN"),
    ("39 / 2016 / TT - NHNN", "39/2016/TT-NHNN"),
    # câu hỏi viết thường
    ("39/2016/tt-nhnn", "39/2016/TT-NHNN"),
    ("06/2023/tt-nhnn", "06/2023/TT-NHNN"),
]


@pytest.mark.parametrize("raw,canon", DOC_NUM_TABLE)
def test_doc_number_one_token(raw, canon):
    text = f"theo quy định tại Thông tư {raw} về hoạt động cho vay"
    tokens = tokenize(text)
    assert canon.lower() in tokens, f"{raw!r} → tokens {tokens}"
    # số hiệu KHÔNG bị vỡ thành mảnh
    assert not any(t in ("39", "2016", "tt", "nhnn", "nđ", "cp") for t in tokens)


@pytest.mark.parametrize("raw,canon", DOC_NUM_TABLE)
def test_extract_doc_numbers_removes_from_text(raw, canon):
    rest, found = extract_doc_numbers(f"xem {raw} nhé")
    assert found == [canon]
    assert raw not in rest


def test_canonical_doc_num():
    assert canonical_doc_num("32 /2026/TT- NHNN") == "32/2026/TT-NHNN"


def test_date_is_not_doc_number():
    # 'Luật ... ngày 16/6/2010' — ngày KHÔNG phải số hiệu (năm không ở vị trí 2)
    _, found = extract_doc_numbers("Luật Các TCTD ngày 16/6/2010")
    assert found == []


def test_plain_words_segmented_lowercase():
    tokens = tokenize("Tổ chức tín dụng KHÔNG được cho vay")
    assert all(t == t.lower() for t in tokens)
    assert "không" in tokens


def test_bm25_broken_docnum_query_hits_clean_doc():
    idx = BM25Index([
        ("d1", "Thông tư 32/2026/TT-NHNN quy định về tỷ lệ an toàn"),
        ("d2", "Thông tư 39/2016/TT-NHNN quy định hoạt động cho vay"),
    ])
    hits = idx.search("nội dung 32 /2026/TT- NHNN")  # dạng lỗi khoảng trắng
    assert hits and hits[0][0] == "d1"


def test_bm25_zero_overlap_returns_empty():
    idx = BM25Index([("d1", "cho vay ngắn hạn tối đa 01 năm")])
    assert idx.search("blockchain khủng long bạo chúa") == []


def test_bm25_empty_corpus():
    assert BM25Index([]).search("cho vay") == []


def test_rebuild_under_1s_on_seed_corpus():
    from answer.demo_seed import mem_store
    rows = mem_store()._rows  # toàn bộ row seed
    entries = [(r.key, r.text) for r in rows]
    t0 = time.monotonic()
    BM25Index(entries)
    assert time.monotonic() - t0 < 1.0  # D-39: rebuild từ snapshot <1s
