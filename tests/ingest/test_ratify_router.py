"""ratify — R-15 router hai hàng đợi, R-16 machine-verify, D-19/INV-6."""
from datetime import date
from uuid import uuid4

import pytest

from ingest.model import ProposedOp
from ingest.orchestrator import ingest_corpus_pure, route_bundle
from ingest.ratify import machine_verify_op, route_op, spot_check_ids

from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts


@pytest.fixture(scope="module")
def corpus():
    return ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts())


# ---- router R-15 -------------------------------------------------------------

def test_definitional_target_routes_per_op(corpus):
    """Op sửa node định nghĩa (Đ2 TT39 'Giải thích từ ngữ') → per-op."""
    store, bundles = corpus
    op = next(o for o in bundles["06/2023/TT-NHNN"].ops
              if o.target_path == "dieu:2/khoan:2")
    assert op.risk_class == "definitional"
    assert op.queue == "per_op"


def test_norm_decl_routes_per_op(corpus):
    store, bundles = corpus
    op = next(o for o in bundles["32/2026/TT-NHNN"].ops if o.kind == "norm_decl")
    assert op.queue == "per_op"


def test_divergent_date_routes_per_op(corpus):
    store, bundles = corpus
    op = next(o for o in bundles["11/2026/TT-NHNN"].ops if o.target_path == "phuluc:01")
    assert op.queue == "per_op"                      # ngày-cần-phân-loại (bẫy #10)
    assert not op.date_direct


def test_no_llm_means_no_batch(corpus):
    """LLM off → 'rule↔LLM khớp' bất khả → mọi op per-op (trung thực D-19)."""
    store, bundles = corpus
    for dk, b in bundles.items():
        for o in b.ops:
            assert o.queue == "per_op"


def test_batch_eligible_with_llm_agreement(corpus):
    """4 điều kiện cơ học đủ → batch: rule↔LLM khớp, target duy nhất,
    prescriptive, ngày đọc thẳng."""
    store, bundles = corpus
    op = next(o for o in bundles["06/2023/TT-NHNN"].ops
              if o.target_path == "dieu:8/khoan:8")
    op.rule_llm_agree = True                          # mô phỏng LLM đồng thuận
    decision = route_op(op, store, doc_effective=date(2023, 9, 1), llm_enabled=True)
    assert decision.queue == "batch"
    assert op.risk_class == "prescriptive"


def test_red_flag_blocks_batch(corpus):
    store, bundles = corpus
    op = next(o for o in bundles["06/2023/TT-NHNN"].ops
              if o.target_path == "dieu:8/khoan:9")
    op.rule_llm_agree = True
    op.red_flags.append("provenance_mismatch")
    decision = route_op(op, store, doc_effective=date(2023, 9, 1), llm_enabled=True)
    assert decision.queue == "per_op"
    op.red_flags.remove("provenance_mismatch")


# ---- machine-verify R-16 -----------------------------------------------------

def test_verify_phrase_replace_ok(corpus):
    store, bundles = corpus
    op = next(o for o in bundles["28/2026/TT-NHNN"].ops
              if o.phrase_from and o.target_path == "dieu:7/khoan:3")
    tpl = {"pattern": "phrase_replace",
           "from": "phương án sử dụng vốn khả thi",
           "to": "phương án sử dụng vốn khả thi, hợp pháp"}
    ok, reason = machine_verify_op(vars(op), tpl)
    assert ok, reason


def test_verify_phrase_replace_rejects_wrong_phrase(corpus):
    store, bundles = corpus
    op = next(o for o in bundles["28/2026/TT-NHNN"].ops if o.phrase_from)
    tpl = {"pattern": "phrase_replace", "from": "cụm khác", "to": "gì đó"}
    ok, reason = machine_verify_op(vars(op), tpl)
    assert not ok


def test_verify_phrase_replace_via_get_body():
    node = uuid4()
    op = {"kind": "amend", "phrase_from": None, "phrase_to": None,
          "new_text": "Có phương án sử dụng vốn khả thi, hợp pháp.",
          "target_node": node}
    tpl = {"pattern": "phrase_replace", "from": "khả thi", "to": "khả thi, hợp pháp"}
    ok, reason = machine_verify_op(op, tpl, get_body=lambda _n: "Có phương án sử dụng vốn khả thi.")
    assert ok, reason
    # old→new KHÔNG khớp phép thay → fail
    ok2, _ = machine_verify_op(op, tpl, get_body=lambda _n: "Văn bản khác hẳn khả thi.")
    assert not ok2


def test_verify_uniform_field_change():
    op = {"kind": "amend", "new_text": "trong thời hạn 07 ngày làm việc kể từ ngày nhận đủ hồ sơ"}
    tpl = {"pattern": "uniform_field_change", "field_regex": r"\d+ ngày làm việc",
           "from": "10", "to": "07"}
    ok, reason = machine_verify_op(op, tpl)
    assert ok, reason
    bad = {"kind": "amend", "new_text": "trong thời hạn 10 ngày làm việc"}
    assert not machine_verify_op(bad, tpl)[0]


def test_verify_mass_repeal(corpus):
    store, bundles = corpus
    reps = [o for o in bundles["11/2026/TT-NHNN"].ops if o.kind == "repeal"]
    tpl = {"pattern": "mass_repeal", "target_doc_keys": ["39/2016/TT-NHNN"]}
    for o in reps:
        ok, reason = machine_verify_op(vars(o), tpl)
        assert ok, reason
    tpl_wrong = {"pattern": "mass_repeal", "target_doc_keys": ["22/2019/TT-NHNN"]}
    assert not machine_verify_op(vars(reps[0]), tpl_wrong)[0]


def test_verify_kind_mismatch_fails():
    ok, reason = machine_verify_op({"kind": "repeal", "new_text": None},
                                   {"pattern": "phrase_replace", "from": "a", "to": "b"})
    assert not ok


def test_spot_check_at_least_10_percent():
    ids = [uuid4() for _ in range(25)]
    picked = spot_check_ids(ids, 0.1)
    assert len(picked) >= 3                          # ceil(25*0.1)=3
    assert set(picked) <= set(ids)
    assert spot_check_ids(ids[:1], 0.1) == ids[:1]   # luôn ≥1
