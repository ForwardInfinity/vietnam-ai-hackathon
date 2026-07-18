"""Unit thuần cho logic ratify (R-15/R-16/R-17 + spot-check D-19) — chạy trong smoke."""
import math
import random

from api.ratify_logic import (
    queue_sort_key,
    route_queue,
    spot_check_sample,
    unified_diff,
    validate_template,
    verify_op_against_template,
)

# --- R-17: sort risk → confidence tăng dần -----------------------------------

def test_sort_definitional_first_then_confidence_asc():
    ops = [
        {"id": "c", "risk_class": "prescriptive", "confidence": 0.9},
        {"id": "a", "risk_class": "definitional", "confidence": 0.8},
        {"id": "b", "risk_class": "prescriptive", "confidence": 0.2},
        {"id": "d", "risk_class": "definitional", "confidence": None},  # None = nghi nhất
    ]
    ops.sort(key=queue_sort_key)
    assert [o["id"] for o in ops] == ["d", "a", "b", "c"]


# --- R-15: router hai hàng đợi ------------------------------------------------

def _op(**kw):
    base = dict(kind="amend", risk_class="prescriptive", valid_from="2023-09-01",
                target_node="n1", target_op=None, target_norm=None,
                valid_to_event=None, confidence=0.9)
    base.update(kw)
    return base

def test_router_definitional_per_op():
    assert route_queue(_op(risk_class="definitional")) == "per_op"

def test_router_inbound_dinh_nghia_per_op():
    assert route_queue(_op(), has_dinh_nghia_inbound=True) == "per_op"

def test_router_norm_decl_and_close_window_per_op():
    assert route_queue(_op(kind="norm_decl", target_node=None, target_norm="nm")) == "per_op"
    assert route_queue(_op(kind="close_window", target_node=None, target_op="o1")) == "per_op"

def test_router_semantic_date_per_op():
    assert route_queue(_op(valid_from=None)) == "per_op"
    assert route_queue(_op(valid_to_event="văn bản mới có hiệu lực")) == "per_op"

def test_router_mechanical_batch_eligible():
    assert route_queue(_op()) == "batch_eligible"

def test_router_unclassified_risk_stays_per_op():
    assert route_queue(_op(risk_class=None)) == "per_op"


# --- R-16: machine-verify từng pattern -----------------------------------------

def test_template_validation():
    assert validate_template({"pattern": "phrase_replace", "from": "X", "to": "Y"}) is None
    assert validate_template({"pattern": "gì đó"}) is not None
    assert validate_template({"pattern": "uniform_field_change", "field_regex": "(", "from": "1", "to": "2"}) is not None
    assert validate_template({"pattern": "mass_repeal", "target_doc_keys": []}) is not None

def test_phrase_replace_strong_pass_and_fail():
    tpl = {"pattern": "phrase_replace", "from": "10 ngày", "to": "07 ngày"}
    cur = "nộp hồ sơ trong 10 ngày kể từ..."
    ok = verify_op_against_template(tpl, {"id": "1", "kind": "amend", "new_text": cur.replace("10 ngày", "07 ngày")}, cur, "DK")
    assert ok.ok and not ok.weak
    # op đổi NHIỀU HƠN cụm khai báo → fail
    bad = verify_op_against_template(tpl, {"id": "2", "kind": "amend", "new_text": "text khác hẳn 07 ngày"}, cur, "DK")
    assert not bad.ok

def test_phrase_replace_weak_without_snapshot():
    tpl = {"pattern": "phrase_replace", "from": "10 ngày", "to": "07 ngày"}
    r = verify_op_against_template(tpl, {"id": "1", "kind": "amend", "new_text": "trong 07 ngày"}, None, "DK")
    assert r.ok and r.weak

def test_uniform_field_change():
    tpl = {"pattern": "uniform_field_change", "field_regex": r"\d+ ngày làm việc", "from": "10", "to": "07"}
    cur = "trả lời trong 10 ngày làm việc"
    good = verify_op_against_template(tpl, {"id": "1", "kind": "amend", "new_text": "trả lời trong 07 ngày làm việc"}, cur, "DK")
    assert good.ok
    still_old = verify_op_against_template(tpl, {"id": "2", "kind": "amend", "new_text": "trả lời trong 10 ngày làm việc"}, cur, "DK")
    assert not still_old.ok

def test_mass_repeal_doc_key_membership():
    tpl = {"pattern": "mass_repeal", "target_doc_keys": ["01/2020/TT-NHNN"]}
    ok = verify_op_against_template(tpl, {"id": "1", "kind": "repeal", "new_text": None}, None, "01/2020/TT-NHNN")
    assert ok.ok
    out = verify_op_against_template(tpl, {"id": "2", "kind": "repeal", "new_text": None}, None, "39/2016/TT-NHNN")
    assert not out.ok


# --- spot-check ≥10% (D-19) -----------------------------------------------------

def test_spot_check_at_least_10_percent():
    for n in (1, 3, 10, 47, 100):
        ids = [str(i) for i in range(n)]
        sample = spot_check_sample(ids, 0.1, rng=random.Random(42))
        assert len(sample) >= max(1, math.ceil(n * 0.1))
        assert len(set(sample)) == len(sample) and set(sample) <= set(ids)

def test_spot_check_rate_floor():
    # khai rate 1% vẫn bị nâng sàn 10% (D-19)
    sample = spot_check_sample([str(i) for i in range(100)], 0.01, rng=random.Random(1))
    assert len(sample) >= 10


def test_unified_diff_marks_changes():
    d = unified_diff("dòng cũ 10 ngày", "dòng mới 07 ngày")
    assert "-dòng cũ 10 ngày" in d and "+dòng mới 07 ngày" in d
