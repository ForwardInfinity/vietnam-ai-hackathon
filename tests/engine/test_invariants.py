"""Registry invariant compliance (R-24, D-37b): chạy trên effective state sau mỗi run;
INV-COMP-01 trần lãi suất; INV-COMP-02 ngày LLTP (fixture TT11); enable/disable."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import engine.invariants as inv


def _state(corpus, folded, as_of=date(2026, 8, 1)):
    return inv.effective_state(folded, corpus.nodes, corpus.artifacts_by_id, as_of)


def test_registry_registered_and_clean_on_fixture(corpus, folded):
    assert set(inv.registered()) == {"INV-COMP-01", "INV-COMP-02"}
    assert inv.run_all(_state(corpus, folded)) == []     # fixture chuẩn: nhất quán


def test_inv_comp_01_tran_lai_suat(corpus, folded):
    """Nội bộ SHB nêu trần CAO hơn trần pháp quy cùng phân loại → violation tier-3;
    nội bộ THẤP hơn (siết nghĩa vụ của mình) → tuân thủ, không bắn (D-34)."""
    cs = corpus.node("CS-LS-01/SHB", "muc:2")
    state = _state(corpus, folded)

    bad_versions = dict(folded.versions)
    (v,) = bad_versions[cs.id]
    bad_versions[cs.id] = (replace(v, body=v.body.replace("tối đa 4%/năm",
                                                          "tối đa 5%/năm")),)
    bad_state = replace(state, versions=bad_versions)
    violations = inv.run_all(bad_state)
    assert len(violations) == 1
    assert violations[0].invariant_id == "INV-COMP-01"
    assert "5%/năm" in violations[0].reason and "4%/năm" in violations[0].reason
    assert (cs.id, 1) in violations[0].members

    lower = dict(folded.versions)
    lower[cs.id] = (replace(v, body=v.body.replace("tối đa 4%/năm", "tối đa 3%/năm")),)
    assert inv.run_all(replace(state, versions=lower)) == []


def test_inv_comp_02_ngay_lltp(corpus, folded):
    """TT11: hai node cùng nêu 01/07/2026 → sạch; một node lệch ngày → violation."""
    d5 = corpus.node("11/2026/TT-NHNN", "dieu:5")
    state = _state(corpus, folded)
    assert inv.run_all(state) == []

    bad = dict(folded.versions)
    (v,) = bad[d5.id]
    bad[d5.id] = (replace(v, body=v.body.replace("01/07/2026", "01/03/2026")),)
    violations = inv.run_all(replace(state, versions=bad))
    assert [x.invariant_id for x in violations] == ["INV-COMP-02"]
    assert "01/03/2026" in violations[0].reason.replace("2026-03-01", "01/03/2026") or \
        "2026-03-01" in violations[0].reason


def test_enable_disable(corpus, folded):
    d5 = corpus.node("11/2026/TT-NHNN", "dieu:5")
    state = _state(corpus, folded)
    bad = dict(folded.versions)
    (v,) = bad[d5.id]
    bad[d5.id] = (replace(v, body=v.body.replace("01/07/2026", "01/01/2027")),)
    bad_state = replace(state, versions=bad)
    assert inv.run_all(bad_state) != []
    inv.set_enabled("INV-COMP-02", False)
    try:
        assert inv.run_all(bad_state) == []
    finally:
        inv.set_enabled("INV-COMP-02", True)
