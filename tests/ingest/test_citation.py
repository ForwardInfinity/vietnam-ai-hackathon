"""citation — R-8..R-10: 3 tầng, kiểu edge, unresolved backlog, skip amending."""
from datetime import date

from ingest.alias import MemoryStore
from ingest.citation import CitationContext, extract_edges
from ingest.normalize import normalize
from ingest.roles import assign_roles
from ingest.tree_parser import parse_document

from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts
from ingest.orchestrator import ingest_corpus_pure


def _edges(doc_key: str, store=None):
    doc = parse_document(normalize(fixture_texts()[doc_key]))
    entry = next(e for e in FIXTURE_ENTRIES if e["doc_key"] == doc_key)
    assign_roles(doc, entry.get("doc_type", "thong_tu"))
    ctx = CitationContext(doc_key=doc_key,
                          issued_date=date.fromisoformat(entry["issued_date"]),
                          store=store or MemoryStore())
    return extract_edges(doc, ctx), doc


def test_can_cu_free_tham_quyen():
    edges, _ = _edges("39/2016/TT-NHNN")
    tq = [e for e in edges if e.kind == "tham_quyen"]
    assert len(tq) == 3                       # 3 dòng Căn cứ
    assert all(e.src_path == "preamble" for e in tq)
    assert all(e.raw_citation.startswith("Căn cứ") for e in tq)
    # văn bản căn cứ không có trong kho → unresolved (3 đích NULL) conf 0 — backlog R-10
    assert all(not e.resolved and e.confidence == 0.0 for e in tq)


def test_pinpoint_expansion_and_kinds():
    edges, doc = _edges("39/2016/TT-NHNN")
    by = {(e.src_path, e.kind, e.dst_path) for e in edges}
    # dinh_nghia: Đ7k1 → khoản 2 Điều 2 ("theo quy định tại")
    assert ("dieu:7/khoan:1", "dinh_nghia", "dieu:2/khoan:2") in by
    # ngoai_le: Đ7k2 → Điều 8 ("trừ trường hợp quy định tại")
    assert ("dieu:7/khoan:2", "ngoai_le", "dieu:8") in by
    # ngoai_le tương đối: Đ8k6 → khoản 5 Điều này
    assert ("dieu:8/khoan:6", "ngoai_le", "dieu:8/khoan:5") in by
    assert ("dieu:13/khoan:1", "ngoai_le", "dieu:13/khoan:2") in by


def test_self_doc_refs_resolve_to_local_nodes():
    edges, doc = _edges("39/2016/TT-NHNN")
    e = next(e for e in edges if e.src_path == "dieu:7/khoan:1" and e.kind == "dinh_nghia")
    assert e.dst_node == doc.node_at("dieu:2/khoan:2").id
    assert e.resolved


def test_chu_de_array_ref_points_norm_not_unit():
    edges, _ = _edges("39/2016/TT-NHNN")
    cd = [e for e in edges if e.kind == "chu_de"]
    # Đ31k2 "theo quy định của NHNN về..." + Đ13k2a "theo quy định của Chính phủ về..."
    assert {e.src_path for e in cd} >= {"dieu:31/khoan:2", "dieu:13/khoan:2/diem:a"}
    for e in cd:
        assert e.dst_path is None            # KHÔNG cưỡng ép về unit (R-10)
        assert e.dst_node is None
        # norm chưa tồn tại (chưa ratify norm_decl nào) → unresolved backlog conf 0
        assert e.dst_norm is None and e.confidence == 0.0


def test_amending_node_inquote_refs_are_not_citation_edges():
    """D-05: ref nằm TRONG text được quote của node amending KHÔNG thành edge
    (nội dung đó chỉ sống qua op; F4 re-derive sau ratify). Ref NGOÀI quote
    (đích mệnh lệnh) được phép — where-used/blast-radius cần."""
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts())
    edges = bundles["06/2023/TT-NHNN"].edges
    # TT06-mini Đ1k4 quote chứa "quy định tại Thông tư này" (Điều 32a mới) — KHÔNG edge
    in_quote_refs = [e for e in edges
                     if e.src_path == "dieu:1/khoan:4" and "Thông tư này" in e.raw_citation]
    assert not in_quote_refs
    # ref ngoài quote (đích op "khoản 8, khoản 9 và khoản 10") được phép tồn tại
    assert any(e.src_path == "dieu:1/khoan:2" for e in edges)


def test_cross_doc_resolution_via_store():
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts())
    # TT32 Đ2 chu_de tồn tại; căn cứ TT06 → tham_quyen; kiểm cạnh cross-doc bằng op resolve đã đủ
    e32 = bundles["32/2026/TT-NHNN"].edges
    assert any(e.kind == "chu_de" and e.src_path == "dieu:2" for e in e32)


def test_expected_edges_sample_superset():
    """Edge sinh ra ⊇ expected_edges_sample từng văn bản, đúng kiểu."""
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts())
    missing = []
    for entry in FIXTURE_ENTRIES:
        got = {(e.src_path, e.kind, e.dst_path) for e in bundles[entry["doc_key"]].edges}
        got_loose = {(s, k) for s, k, _ in got}
        for exp in entry.get("expected_edges_sample", []):
            if "dst" in exp:
                if (exp["src"], exp["kind"], exp["dst"]) not in got:
                    missing.append((entry["doc_key"], exp))
            elif (exp["src"], exp["kind"]) not in got_loose:
                missing.append((entry["doc_key"], exp))
    assert not missing, f"thiếu edge kỳ vọng: {missing}"


def test_vbhn_oracle_no_edges_no_ops():
    """R-7: VBHN chỉ parse để diff."""
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts())
    vbhn = bundles["20/VBHN-NHNN"]
    assert vbhn.edges == [] and vbhn.ops == []
    assert vbhn.doc.counts()["khoan"] == 10   # vẫn parse đủ cây để diff


def test_term_definition_edges():
    """02§5.2: term 'Phương án sử dụng vốn' (định nghĩa Đ2k3) có mặt ở Đ7k3
    → edge dinh_nghia same-doc (input closure D-29)."""
    edges, doc = _edges("39/2016/TT-NHNN")
    term_edges = [e for e in edges if e.raw_citation.startswith("term:")]
    assert ("dieu:7/khoan:3", "dieu:2/khoan:3") in {(e.src_path, e.dst_path) for e in term_edges}
    # node định nghĩa/amending KHÔNG là src của term edge
    assert all(not e.src_path.startswith("dieu:2") for e in term_edges)
