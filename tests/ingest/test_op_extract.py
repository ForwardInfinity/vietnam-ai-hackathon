"""op_extract — R-11..R-14, bẫy #3, #4, #5, #8, #9, #10, #11, #17 + op-on-op + đính chính."""
from datetime import date

from ingest.orchestrator import ingest_corpus_pure

from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts

import pytest


@pytest.fixture(scope="module")
def corpus():
    return ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts())


def _ops(corpus, doc_key):
    return corpus[1][doc_key].ops


# ---- TT06: amend + insert enumeration + heading op + repeal ------------------

def test_tt06_enumeration_three_inserts(corpus):
    ops = [o for o in _ops(corpus, "06/2023/TT-NHNN") if o.kind == "insert"
           and o.target_path and o.target_path.startswith("dieu:8/")]
    assert {o.target_path for o in ops} == {"dieu:8/khoan:8", "dieu:8/khoan:9", "dieu:8/khoan:10"}
    by_path = {o.target_path: o for o in ops}
    assert by_path["dieu:8/khoan:8"].new_text == "Để gửi tiền."
    assert "góp vốn" in by_path["dieu:8/khoan:9"].new_text
    # điểm a)/b) của khoản 10 ở LẠI trong text khoản 10 (chỉ tách cấp marker đầu)
    assert "a) Khách hàng đã ứng vốn" in by_path["dieu:8/khoan:10"].new_text
    for o in ops:
        assert o.valid_from == date(2023, 9, 1)
        assert o.target_doc_key == "39/2016/TT-NHNN"
        assert o.target_node is not None          # node birth-id đã cấp (R-12)


def test_tt06_insert_creates_birth_nodes(corpus):
    store, bundles = corpus
    born = [n for n in bundles["06/2023/TT-NHNN"].nodes if n.born_of_op]
    assert {n.path for n in born} == {"dieu:8/khoan:8", "dieu:8/khoan:9",
                                      "dieu:8/khoan:10", "dieu:32a"}
    assert all(n.artifact_doc_key == "39/2016/TT-NHNN" for n in born)


def test_tt06_amend_khoan2_dieu2(corpus):
    op = next(o for o in _ops(corpus, "06/2023/TT-NHNN")
              if o.kind == "amend" and o.target_path == "dieu:2/khoan:2")
    assert "pháp nhân, cá nhân có nhu cầu vay vốn hợp pháp" in op.new_text
    assert op.new_text.startswith("Khách hàng")   # marker '2.' đã strip
    assert op.valid_from == date(2023, 9, 1)


def test_tt06_heading_only_op_trap11(corpus):
    op = next(o for o in _ops(corpus, "06/2023/TT-NHNN")
              if o.target_path == "dieu:13" and o.target_part == "heading")
    assert op.kind == "amend"
    assert op.new_heading == "Lãi suất, phí cho vay"
    assert op.new_text is None


def test_tt06_insert_dieu_32a_with_heading(corpus):
    op = next(o for o in _ops(corpus, "06/2023/TT-NHNN") if o.target_path == "dieu:32a")
    assert op.kind == "insert"
    assert op.new_heading == "Cho vay bằng phương tiện điện tử"
    assert "phương tiện điện tử" in op.new_text


def test_tt06_repeal_khoan2_dieu13(corpus):
    op = next(o for o in _ops(corpus, "06/2023/TT-NHNN")
              if o.kind == "repeal")
    assert op.target_path == "dieu:13/khoan:2"
    assert op.target_doc_key == "39/2016/TT-NHNN"


def test_tt06_grandfather_scope_attached(corpus):
    """Điều khoản chuyển tiếp TT06 → DSL đóng D-25 gắn vào op amend/insert."""
    ops = [o for o in _ops(corpus, "06/2023/TT-NHNN") if o.kind in ("amend", "insert")]
    assert ops
    for o in ops:
        assert o.scope_predicate == {"contract_signed_before": "2023-09-01",
                                     "not_amended_on_or_after": "2023-09-01"}


def test_tt06_seq_order_trap17(corpus):
    ops = _ops(corpus, "06/2023/TT-NHNN")
    seqs = [o.seq for o in ops]
    assert seqs == sorted(seqs)
    # khoản 1 (amend Đ2k2) trước khoản 2 (insert k8-10), trước khoản 5 (repeal)
    amend_d2 = next(o for o in ops if o.target_path == "dieu:2/khoan:2")
    ins_k8 = next(o for o in ops if o.target_path == "dieu:8/khoan:8")
    rep = next(o for o in ops if o.kind == "repeal")
    assert amend_d2.seq < ins_k8.seq < rep.seq


# ---- TT10: ngưng hiệu lực ≠ bãi bỏ + sự kiện + provenance (bẫy #3,#4,#5) -----

def test_tt10_three_suspends_not_repeal(corpus):
    ops = _ops(corpus, "10/2023/TT-NHNN")
    sus = [o for o in ops if o.kind == "suspend"]
    assert len(sus) == 3, [(o.kind, o.target_path) for o in ops]
    assert not any(o.kind == "repeal" for o in ops)               # bẫy #3
    assert {o.target_path for o in sus} == {"dieu:8/khoan:8", "dieu:8/khoan:9",
                                            "dieu:8/khoan:10"}


def test_tt10_valid_from_and_event(corpus):
    for o in [o for o in _ops(corpus, "10/2023/TT-NHNN") if o.kind == "suspend"]:
        assert o.valid_from == date(2023, 9, 1)                   # ≠ ngày ban hành 23/08
        assert o.valid_to is None
        assert o.valid_to_event is not None                       # bẫy #5: sự kiện, không phải ngày
        assert "văn bản quy phạm pháp luật mới" in o.valid_to_event


def test_tt10_targets_resolve_to_tt06_birth_nodes(corpus):
    """Bẫy #4: TT10 nhắm node do TT06 ĐỀ XUẤT tạo, chưa ratify, chưa kịp hiệu lực."""
    store, bundles = corpus
    born_ids = {n.path: n.id for n in bundles["06/2023/TT-NHNN"].nodes if n.born_of_op}
    for o in [o for o in _ops(corpus, "10/2023/TT-NHNN") if o.kind == "suspend"]:
        assert o.target_node == born_ids[o.target_path]


def test_tt10_provenance_cross_validation_passes(corpus):
    """R-13: '(đã được bổ sung theo khoản 2 Điều 1 TT06)' khớp chuỗi op thật → không cờ đỏ."""
    for o in [o for o in _ops(corpus, "10/2023/TT-NHNN") if o.kind == "suspend"]:
        assert o.provenance_mentions, "phải bắt được ngoặc provenance"
        assert "provenance_mismatch" not in o.red_flags


# ---- TT08: op-nhắm-op (D-10, R-12) ------------------------------------------

def test_tt08_repeal_of_amending_provision_becomes_target_op(corpus):
    store, bundles = corpus
    tt26_ops = bundles["26/2022/TT-NHNN"].ops
    k4_amend = next(o for o in tt26_ops if o.target_path == "dieu:20/khoan:4")
    rep = next(o for o in _ops(corpus, "08/2026/TT-NHNN") if o.kind == "repeal")
    assert rep.target_op == k4_amend.id           # nhắm OP, không nhắm node
    assert rep.target_node is None                # không viết lại lịch sử node
    assert rep.valid_from == date(2026, 2, 1)


def test_tt08_amend_diem_a(corpus):
    op = next(o for o in _ops(corpus, "08/2026/TT-NHNN") if o.kind == "amend")
    assert op.target_path == "dieu:20/khoan:2/diem:a"
    assert op.target_doc_key == "22/2019/TT-NHNN"
    assert op.new_text.startswith("Dư nợ cho vay đối với cá nhân")


# ---- TT11 omnibus: context-stack + phân kỳ + Phụ lục (bẫy #9,#10,#11) --------

def test_tt11_chapter_context_resolves_targets(corpus):
    ops = _ops(corpus, "11/2026/TT-NHNN")
    d31 = next(o for o in ops if o.target_path == "dieu:31/khoan:1/diem:b")
    assert d31.target_doc_key == "39/2016/TT-NHNN"                # Chương I
    d20 = next(o for o in ops if o.target_path == "dieu:20/khoan:1")
    assert d20.target_doc_key == "22/2019/TT-NHNN"                # Chương II — bẫy #9


def test_tt11_phuluc_op(corpus):
    op = next(o for o in _ops(corpus, "11/2026/TT-NHNN") if o.target_path == "phuluc:01")
    assert op.kind == "amend"
    assert "Phiếu lý lịch tư pháp" in op.new_text
    assert op.target_doc_key == "39/2016/TT-NHNN"


def test_tt11_divergent_effective_date_trap10(corpus):
    ops = _ops(corpus, "11/2026/TT-NHNN")
    pl = next(o for o in ops if o.target_path == "phuluc:01")
    assert pl.valid_from == date(2026, 7, 1)                      # ≠ 01/03 chung
    assert "divergent_effective_date" in pl.red_flags
    d31 = next(o for o in ops if o.target_path == "dieu:31/khoan:1/diem:b")
    assert d31.valid_from == date(2026, 3, 1)                     # ngày chung


def test_tt11_mass_repeal_expanded(corpus):
    reps = [o for o in _ops(corpus, "11/2026/TT-NHNN") if o.kind == "repeal"]
    assert {o.target_path for o in reps} == {"dieu:13/khoan:2/diem:c", "dieu:13/khoan:2/diem:d"}


# ---- TT28: binding trong quote (#8) + thay-cụm-từ (D-21/R-14) ----------------

def test_tt28_insert_dieu7a_new_text_keeps_quoted_binding(corpus):
    op = next(o for o in _ops(corpus, "28/2026/TT-NHNN") if o.kind == "insert")
    assert op.target_path == "dieu:7a"
    assert op.target_doc_key == "39/2016/TT-NHNN"
    assert "Thông tư này" in op.new_text          # giữ nguyên văn — bind về TT39 khi render


def test_tt28_phrase_replace_materialized(corpus):
    """D-21: thay-cụm-từ KHÔNG vào enum op — materialize amend node-level."""
    phr = [o for o in _ops(corpus, "28/2026/TT-NHNN") if o.phrase_from]
    assert {o.target_path for o in phr} == {"dieu:7/khoan:3", "dieu:13/khoan:2/diem:b"}
    for o in phr:
        assert o.kind == "amend"
        assert o.phrase_from == "phương án sử dụng vốn khả thi"
        assert o.phrase_to == "phương án sử dụng vốn khả thi, hợp pháp"
        assert o.target_node is not None


# ---- norm_decl + blanket (TT32, TT39Đ34) ------------------------------------

def test_tt32_norm_decl_and_blanket(corpus):
    ops = _ops(corpus, "32/2026/TT-NHNN")
    nd = next(o for o in ops if o.kind == "norm_decl")
    assert "22/2019/TT-NHNN" in nd.target_surface
    assert nd.target_norm is not None
    bl = next(o for o in ops if o.kind == "blanket_derogation")
    assert bl.target_node is None and bl.target_op is None and bl.target_norm is None
    assert bl.check_ok()


def test_tt39_norm_decl_from_effectivity_clause(corpus):
    """Op nấp ở điều 'Hiệu lực thi hành' (R-11): QĐ 1627 hết hiệu lực."""
    ops = _ops(corpus, "39/2016/TT-NHNN")
    nd = [o for o in ops if o.kind == "norm_decl"]
    assert len(nd) == 1
    assert "1627/2001/QĐ-NHNN" in nd[0].target_surface


# ---- đính chính (D-12) -------------------------------------------------------

def test_dc01_dinh_chinh(corpus):
    ops = _ops(corpus, "DC-01/2026")
    dc = next(o for o in ops if o.kind == "dinh_chinh")
    assert dc.target_path == "dieu:13/khoan:2/diem:b"
    assert dc.target_doc_key == "39/2016/TT-NHNN"
    assert "xuất khẩu, nhập khẩu" in dc.new_text
    assert "provenance_mismatch" not in dc.red_flags   # khớp op TT28 (R-13)


def test_dc01_provenance_mismatch_flags_when_wrong(corpus):
    """R-13 chiều âm: mention chỉ sai nguồn → cờ đỏ provenance_mismatch."""
    from ingest.op_extract import ExtractionContext, _cross_validate_provenance
    from ingest.model import ProposedOp
    store, bundles = corpus
    dc_bundle = bundles["DC-01/2026"]
    real = next(o for o in dc_bundle.ops if o.kind == "dinh_chinh")
    fake = ProposedOp(kind="dinh_chinh", source_quote="x", seq=1,
                      target_node=real.target_node,
                      provenance_mentions=["khoản 1 Điều 1 Thông tư số 06/2023/TT-NHNN"])
    ctx = ExtractionContext(doc_key="DC-01/2026", issued_date=date(2026, 6, 20),
                            effective_date=date(2026, 6, 20), store=store,
                            doc=dc_bundle.doc)
    _cross_validate_provenance(fake, ctx)
    assert "provenance_mismatch" in fake.red_flags


# ---- tổng exit: expected_ops khớp từng văn bản -------------------------------

def test_expected_ops_all_fixtures(corpus):
    store, bundles = corpus
    problems = []
    for entry in FIXTURE_ENTRIES:
        ops = bundles[entry["doc_key"]].ops
        for exp in entry.get("expected_ops", []):
            if not _match_expected(exp, ops, bundles):
                problems.append((entry["doc_key"], exp))
    assert not problems, "expected_ops không khớp:\n" + "\n".join(map(str, problems))


def _match_expected(exp, ops, bundles):
    for o in ops:
        if o.kind != exp["kind"]:
            continue
        if "target" in exp:
            doc, path = exp["target"]
            if o.target_doc_key != doc or o.target_path != path:
                continue
        if "target_contains" in exp and exp["target_contains"] not in (o.target_surface or ""):
            continue
        if "target_op_from" in exp:
            doc, path = exp["target_op_from"]
            src_ops = [x for x in bundles[doc].ops if x.source_path == path]
            if not (src_ops and o.target_op == src_ops[0].id):
                continue
        if "valid_from" in exp and str(o.valid_from) != exp["valid_from"]:
            continue
        if exp.get("has_valid_to_event") and not o.valid_to_event:
            continue
        if exp.get("target_part") and o.target_part != exp["target_part"]:
            continue
        if "new_text_contains" in exp and exp["new_text_contains"] not in (o.new_text or ""):
            continue
        if "new_heading_contains" in exp and exp["new_heading_contains"] not in (o.new_heading or ""):
            continue
        if exp.get("phrase") and not o.phrase_from:
            continue
        return True
    return False


def test_no_unresolved_ops_in_fixture_corpus(corpus):
    store, bundles = corpus
    bad = []
    for dk, b in bundles.items():
        for o in b.ops:
            if not o.check_ok():
                bad.append((dk, o.kind, o.target_surface, o.red_flags))
    assert not bad, f"op không thỏa CHECK: {bad}"
