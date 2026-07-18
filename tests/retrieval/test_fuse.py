"""RRF fuse (R-28): BM25 ∪ dense → RRF k=60 → top-12, tất định."""
from datetime import date

from retrieval.fuse import hybrid_search, rrf_fuse
from retrieval.query_builder import SnapshotRow


def _row(i: int, body: str) -> SnapshotRow:
    return SnapshotRow(
        node_id=f"n{i}", version=1, heading=None, body=body, status="active",
        valid_from=date(2020, 1, 1), valid_to=None, scope_predicate=None, scope_hash="",
        provenance=(), run_id="r", path=f"dieu:{i}", role="rule", artifact_id="a",
        doc_key="39/2016/TT-NHNN", audience="public")


def test_rrf_math_k60():
    fused = rrf_fuse([["a", "b"], ["b", "c"]], k=60)
    scores = dict(fused)
    assert abs(scores["b"] - (1 / 62 + 1 / 61)) < 1e-12
    assert abs(scores["a"] - 1 / 61) < 1e-12
    assert abs(scores["c"] - 1 / 62) < 1e-12
    assert [k for k, _ in fused][0] == "b"  # có mặt cả hai list → thắng


def test_rrf_deterministic_tie_break():
    # a và b cùng score → tie-break theo repr, bất biến với hoán vị input
    f1 = rrf_fuse([["a"], ["b"]])
    f2 = rrf_fuse([["b"], ["a"]])
    assert [k for k, _ in f1] == [k for k, _ in f2]


def test_hybrid_top12_cap_and_union():
    rows = [_row(i, f"cho vay điều khoản số {i} " + "nội dung " * i) for i in range(1, 20)]
    out = hybrid_search(rows, "cho vay")
    assert len(out) <= 12
    assert all(isinstance(r, SnapshotRow) for r in out)


def test_hybrid_docnum_query():
    rows = [_row(1, "quy định chung"), _row(2, "hoạt động cho vay")]
    # doc_key nằm trong index_text → query số hiệu (kể cả dạng lỗi) phải khớp
    out = hybrid_search(rows, "39 /2016/TT- NHNN cho vay")
    assert out, "số hiệu phải kéo được row của văn bản đó"


def test_hybrid_empty_rows():
    assert hybrid_search([], "cho vay") == []


def test_hybrid_no_match_returns_empty():
    rows = [_row(1, "cho vay ngắn hạn tối đa 01 năm")]
    assert hybrid_search(rows, "xyzabc qwerty đà điểu vũ trụ") == []
