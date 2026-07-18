"""Closure gate (R-29, D-29) — verification nhóm 4, trên MemStore thuần."""
from datetime import date

import pytest

from retrieval.closure import close_over
from retrieval.query_builder import EdgeRow, MemStore, RunInfo, SnapshotRow

AS_OF = date(2024, 3, 1)
ENT = ("public", "internal")


def _row(nid, body="nội dung", audience="public", status="active", version=1,
         scope=None, shash=""):
    return SnapshotRow(
        node_id=nid, version=version, heading=None, body=body, status=status,
        valid_from=date(2020, 1, 1), valid_to=None, scope_predicate=scope,
        scope_hash=shash, provenance=(), run_id="r1", path=f"dieu:{nid}", role="rule",
        artifact_id="a", doc_key="39/2016/TT-NHNN", audience=audience)


def _store(rows, edges, **kw):
    return MemStore(rows, edges=edges, run=RunInfo(run_id="r1"), **kw)


def test_ngoai_le_pulled_both_directions():
    rows = [_row("rule"), _row("exc_out"), _row("exc_in")]
    edges = [
        EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc_out"),
        EdgeRow(src_node="exc_in", src_version=1, kind="ngoai_le", dst_node="rule"),
    ]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    ids = {n.row.node_id for n in res.nodes}
    assert res.complete and {"rule", "exc_out", "exc_in"} <= ids


def test_unresolved_mandatory_ngoai_le_incomplete():
    rows = [_row("rule")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node=None,
                     raw_citation="trừ trường hợp X", confidence=0.0)]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert not res.complete
    assert any(r.startswith("unresolved:ngoai_le") for r in res.reasons)


def test_resolved_mandatory_complete():
    rows = [_row("rule"), _row("exc")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert res.complete and res.reasons == []


def test_budget_drop_mandatory_incomplete():
    rows = [_row("rule"), _row("exc", body="dài " * 50)]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT, max_nodes=1)
    assert not res.complete
    assert any(r.startswith("budget_drop:ngoai_le") for r in res.reasons)


def test_budget_drop_by_tokens_incomplete():
    rows = [_row("rule"), _row("exc", body="từ " * 200)]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT, max_tokens=50)
    assert not res.complete


def test_chu_de_never_gates_nor_pulls():
    rows = [_row("rule"), _row("other")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="chu_de", dst_norm="norm-1",
                     confidence=0.0)]  # kể cả unresolved-ish chu_de
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert res.complete
    assert {n.row.node_id for n in res.nodes} == {"rule"}


def test_dinh_nghia_pulled_when_term_present():
    rows = [_row("rule", body="áp dụng cho khách hàng vay vốn"), _row("def")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="dinh_nghia", dst_node="def",
                     raw_citation="khách hàng")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert "def" in {n.row.node_id for n in res.nodes}


def test_dinh_nghia_skipped_when_term_absent():
    rows = [_row("rule", body="quy định về phí trả nợ"), _row("def")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="dinh_nghia", dst_node="def",
                     raw_citation="tài sản bảo đảm")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert res.complete
    assert "def" not in {n.row.node_id for n in res.nodes}


def test_dinh_nghia_unresolved_gates_only_if_term_present():
    rows = [_row("rule", body="áp dụng cho khách hàng")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="dinh_nghia", dst_node=None,
                     raw_citation="khách hàng", confidence=0.0)]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert not res.complete


def test_chuyen_tiep_unknown_cohort_pull_and_flag():
    rows = [_row("rule"), _row("trans")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="chuyen_tiep", dst_node="trans")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert "trans" in {n.row.node_id for n in res.nodes}
    assert "cohort_ambiguous" in res.flags


def test_chuyen_tiep_known_cohort_no_flag():
    rows = [_row("rule"), _row("trans")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="chuyen_tiep", dst_node="trans")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF,
                     {"contract_signed_before": date(2021, 7, 1)}, ENT)
    assert "cohort_ambiguous" not in res.flags


def test_audience_hidden_mandatory_target_incomplete():
    """ngoai_le trỏ tài liệu nội bộ, người hỏi là customer → degrade an toàn Tier D,
    KHÔNG leak byte (INV-12)."""
    rows = [_row("rule"), _row("exc_int", audience="internal")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc_int")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ("public",))
    assert not res.complete
    assert any(r.startswith("audience_hidden") for r in res.reasons)
    assert "exc_int" not in {n.row.node_id for n in res.nodes}


def test_suspended_target_flags_not_incomplete():
    rows = [_row("rule"), _row("exc", status="suspended")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert res.complete                       # trạng thái treo là hợp lệ, không phải thiếu
    assert "open_suspension" in res.flags
    assert "exc" not in {n.row.node_id for n in res.nodes}  # text treo KHÔNG vào context (INV-8)


def test_depth_limit_2():
    rows = [_row("a"), _row("b"), _row("c"), _row("d")]
    edges = [EdgeRow(src_node="a", src_version=1, kind="ngoai_le", dst_node="b"),
             EdgeRow(src_node="b", src_version=1, kind="ngoai_le", dst_node="c"),
             EdgeRow(src_node="c", src_version=1, kind="ngoai_le", dst_node="d")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    ids = {n.row.node_id for n in res.nodes}
    assert "c" in ids and "d" not in ids      # depth ≤ 2


def test_edge_reprojection_by_version():
    """Edge dẫn xuất theo PHIÊN BẢN nguồn (D-13): version sống khác version mang
    edge → edge không kích hoạt."""
    rows = [_row("rule", version=2), _row("exc")]
    edges = [EdgeRow(src_node="rule", src_version=1, kind="ngoai_le", dst_node="exc")]
    res = close_over([rows[0]], _store(rows, edges), AS_OF, {}, ENT)
    assert "exc" not in {n.row.node_id for n in res.nodes}
    assert res.complete


def test_scope_branches_both_kept():
    gf = {"contract_signed_before": "2023-09-01"}
    rows = [_row("rule", version=2), _row("rule", version=3, scope=gf, shash="gf")]
    store = _store(rows, [])
    res = close_over(rows, store, AS_OF, {}, ENT)
    keys = {(n.row.node_id, n.row.version) for n in res.nodes}
    assert keys == {("rule", 2), ("rule", 3)}  # nhánh song song không bị dedup mất
