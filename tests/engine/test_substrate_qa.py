"""Substrate QA (04 §5) — falsifier trực tiếp của engine, không qua LLM, không cần Postgres.

Mỗi test là một falsifier của một lời hứa cụ thể (D-47); assertion đúng nguyên văn bảng 04 §5.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timezone

from engine.fixtures import load_dir
from engine.fold import (active_intervals, ever_active, fold_corpus, materialize_at,
                         state_digest, verify_tiling, versions_digest)
from engine.model import jsonable
from engine.scope import applicability_matches

AS_KNOWN_BEFORE_TT10 = datetime(2023, 8, 20, 23, 59, tzinfo=timezone.utc)


def _fold(corpus, ops=None, **kw):
    return fold_corpus(corpus.nodes, ops if ops is not None else corpus.ops,
                       corpus.artifacts, **kw)


# ---------------------------------------------------------------------------- INV-3
def test_determinism_permutation(corpus, folded):
    """fold sau khi ĐẢO thứ tự nạp TT06/TT10 (và toàn corpus shuffle) == kết quả chuẩn."""
    reference = state_digest(folded)

    # đảo riêng TT06 ↔ TT10 (cùng valid_from 01/09/2023, cùng hạng — bẫy 7 của 02 §7)
    swapped = [o for o in corpus.ops if o.source_artifact not in
               ("art:06/2023/TT-NHNN", "art:10/2023/TT-NHNN")]
    tt10 = [o for o in corpus.ops if o.source_artifact == "art:10/2023/TT-NHNN"]
    tt06 = [o for o in corpus.ops if o.source_artifact == "art:06/2023/TT-NHNN"]
    assert state_digest(_fold(corpus, tt10 + swapped + tt06)) == reference

    # ≥20 hoán vị toàn corpus (op lẫn node)
    for seed in range(20):
        rng = random.Random(seed)
        ops = list(corpus.ops)
        nodes = list(corpus.nodes)
        rng.shuffle(ops)
        rng.shuffle(nodes)
        assert state_digest(fold_corpus(nodes, ops, corpus.artifacts)) == reference, \
            f"hoán vị seed={seed} đổi kết quả fold — vi phạm INV-3"


# ---------------------------------------------------------------------------- k8-10 Đ8 TT39
def test_empty_interval(corpus, folded):
    """operative interval của k8–10 Đ8 TT39 = ∅; tồn tại version suspended từ 01/09/2023,
    KHÔNG tồn tại version active; 'đã từng có hiệu lực?' → chưa từng."""
    for khoan in ("dieu:8/khoan:8", "dieu:8/khoan:9", "dieu:8/khoan:10"):
        node = corpus.node("39/2016/TT-NHNN", khoan)
        versions = folded.versions[node.id]
        assert active_intervals(versions) == [], f"{khoan}: interval phải ∅"
        assert not any(v.status == "active" for v in versions), f"{khoan}: không được có active"
        suspended = [v for v in versions if v.status == "suspended"]
        assert suspended and suspended[0].valid_from == date(2023, 9, 1)
        assert suspended[0].valid_to is None            # sự kiện chưa xảy ra → treo vô thời hạn
        assert not ever_active(versions), f"{khoan}: 'đã từng?' phải là CHƯA TỪNG"
        # suspend ≠ delete (D-24): text vẫn sống trong version suspended
        assert suspended[0].body


# ---------------------------------------------------------------------------- INV-5
def test_window_inviolability(corpus):
    """sau ratify repeal-op TT08/2026: mọi version có valid_to <= 2026-01-01 bit-identical
    trước/sau; materialize tại mọi t < 2026-01-01 không đổi (cửa sổ đã qua bất khả xâm phạm)."""
    repeal = corpus.op("op:tt08-repeal-tt26op")
    before = _fold(corpus, [o for o in corpus.ops if o.id != repeal.id])
    after = _fold(corpus)
    cutoff = date(2026, 1, 1)

    def past(cf):
        return {(str(nid), v.valid_from.isoformat(), v.scope_hash, v.status):
                jsonable((v.heading, v.body, v.valid_to, v.provenance))
                for nid, vs in cf.versions.items() for v in vs
                if v.valid_to is not None and v.valid_to <= cutoff}

    b, a = past(before), past(after)
    for key, payload in b.items():
        assert a.get(key) == payload, f"version quá khứ {key} bị viết lại — vi phạm INV-5"

    ldr = corpus.node("22/2019/TT-NHNN", "dieu:20/khoan:2")
    for t in (date(2023, 1, 1), date(2024, 3, 1), date(2025, 12, 31)):
        tb = [(v.body, v.status) for v in materialize_at(before.versions[ldr.id], t)]
        ta = [(v.body, v.status) for v in materialize_at(after.versions[ldr.id], t)]
        assert tb == ta, f"text tại {t} đổi sau repeal-op — lịch sử bị viết lại"
    # còn từ 2026-01-01: hiệu lực của op TT26 chấm dứt (forward-only)
    at_2026 = materialize_at(after.versions[ldr.id], date(2026, 6, 1))
    assert all("(bản TT26/2022)" not in (v.body or "") for v in at_2026)


# ---------------------------------------------------------------------------- INV-4
def test_tiling(folded):
    """INV-4 trên toàn corpus, mọi (node, scope_hash): không chồng lấn, phủ liên tục."""
    assert verify_tiling(folded.versions) == []


# ---------------------------------------------------------------------------- D-25/D-04
def test_scope_split(corpus, folded):
    """TT32/2026: hai version cùng cửa sổ, khác scope_hash, cùng tồn tại;
    applicability_matches đúng bảng chân trị (cohort thiếu ⇒ match cả hai)."""
    d7 = corpus.node("39/2016/TT-NHNN", "dieu:7")
    at = materialize_at(folded.versions[d7.id], date(2026, 8, 1))
    assert len(at) == 2
    assert len({v.scope_hash for v in at}) == 2
    assert len({v.valid_from for v in at}) == 1          # cùng cửa sổ
    old = next(v for v in at if "(bản TT12/2024)" in v.body)
    new = next(v for v in at if "(bản TT32/2026)" in v.body)
    assert old.scope_predicate == {"contract_signed_before": "2026-07-01",
                                   "not_amended_on_or_after": "2026-07-01"}
    assert new.scope_predicate == {"complement_of": old.scope_predicate}

    D = "2026-07-01"
    truth_table = [
        # (cohort, khớp nhánh cũ?, khớp nhánh mới?)
        ({}, True, True),                                              # thiếu hết ⇒ CẢ HAI
        (None, True, True),
        ({"contract_signed_before": "2026-06-01",
          "not_amended_on_or_after": D}, True, False),                 # grandfather đủ 2 tầng
        ({"contract_signed_before": D,
          "not_amended_on_or_after": "2026-01-01"}, True, False),      # cận đúng biên
        ({"contract_signed_before": "2026-08-01"}, False, True),       # ký sau ⇒ chỉ nhánh mới
        ({"contract_signed_before": "2026-08-01",
          "not_amended_on_or_after": D}, False, True),
        ({"contract_signed_before": "2026-06-01"}, True, True),        # thiếu tầng 2 ⇒ CẢ HAI
        ({"not_amended_on_or_after": D}, True, True),                  # thiếu tầng 1 ⇒ CẢ HAI
        ({"contract_signed_before": "2026-06-01",
          "not_amended_on_or_after": "2026-09-01"}, True, True),       # tầng 2 không đảm bảo ⇒ CẢ HAI
        ({"entity_class": "ca_nhan"}, True, True),                     # field ngoài predicate ⇒ CẢ HAI
    ]
    for cohort, want_old, want_new in truth_table:
        assert applicability_matches(old.scope_predicate, cohort) is want_old, \
            f"nhánh cũ với cohort {cohort}"
        assert applicability_matches(new.scope_predicate, cohort) is want_new, \
            f"nhánh mới với cohort {cohort}"


# ---------------------------------------------------------------------------- D-12
def test_dinh_chinh_retroactive(corpus, folded):
    """DC-01: text sau đính chính áp từ ĐẦU cửa sổ, provenance chứa op dinh_chinh."""
    d7a = corpus.node("39/2016/TT-NHNN", "dieu:7a")
    dc = corpus.op("op:dc01-fix-d7a")
    versions = folded.versions[d7a.id]
    assert len(versions) == 1                            # không tách version mới tại ngày đính chính
    v = versions[0]
    assert v.valid_from == date(2026, 1, 15)             # ĐẦU cửa sổ của version bị đính chính
    assert "10 ngày làm việc" in v.body and "07 ngày" not in v.body
    assert dc.id in v.provenance
    # as-of TRƯỚC ngày đính chính (05/02/2026) vẫn thấy số đã đính chính (hồi tố)
    at = materialize_at(versions, date(2026, 2, 1), status="active")
    assert len(at) == 1 and "10 ngày làm việc" in at[0].body


# ---------------------------------------------------------------------------- R-21/D-11
def test_pending_sweep(corpus, folded):
    """nạp fixture 'văn bản QPPL mới' → xuất hiện ĐỀ XUẤT close_window trong queue
    (không tự đóng); ratify → k8–10 hồi sinh active."""
    from engine.sweep import sweep_pending
    from tests.engine.conftest import ratified_copy

    new_doc = corpus.artifacts_by_id["art:05/2027/TT-NHNN"]
    ops_by_id = {o.id: o for o in corpus.ops}
    proposals = sweep_pending(folded.open_suspensions, ops_by_id=ops_by_id,
                              artifact=new_doc, artifacts=corpus.artifacts_by_id)
    assert len(proposals) == 3                           # một đề xuất mỗi op suspend đang treo
    for p in proposals:
        assert str(p.op.kind.value) == "close_window"
        assert str(p.op.status.value) == "proposed"      # MÁY KHÔNG TỰ ĐÓNG
        assert p.op.valid_from == date(2027, 1, 1)       # ngày văn bản QPPL mới có hiệu lực
        assert p.op.target_op in {o.id for o in corpus.ops if o.valid_to_event}

    # chưa ratify → fold KHÔNG đổi (đề xuất không được chạm effective state — D-03)
    with_proposed = _fold(corpus, corpus.ops + [p.op for p in proposals])
    assert state_digest(with_proposed) == state_digest(folded)
    assert len(with_proposed.open_suspensions) == 3

    # người phê chuẩn → k8-10 hồi sinh từ 01/01/2027
    ratified = [ratified_copy(p.op) for p in proposals]
    cf2 = _fold(corpus, corpus.ops + ratified)
    assert cf2.open_suspensions == ()                    # pending đã đóng
    for khoan in ("dieu:8/khoan:8", "dieu:8/khoan:9", "dieu:8/khoan:10"):
        node = corpus.node("39/2016/TT-NHNN", khoan)
        vs = cf2.versions[node.id]
        assert [(v.status, v.valid_from, v.valid_to) for v in vs] == [
            ("suspended", date(2023, 9, 1), date(2027, 1, 1)),
            ("active", date(2027, 1, 1), None),
        ], f"{khoan} phải hồi sinh active từ 01/01/2027"
        assert ever_active(vs)


# ---------------------------------------------------------------------------- INV-9
def test_rebuild_bitexact(corpus, folded):
    """INV-9: dựng lại toàn bộ từ artifact+op (load lại từ đĩa, hoán vị) — bit-exact."""
    fresh = load_dir()                                   # object graph mới hoàn toàn
    ops = list(fresh.ops)
    random.Random(99).shuffle(ops)
    rebuilt = fold_corpus(fresh.nodes, ops, fresh.artifacts)
    assert state_digest(rebuilt) == state_digest(folded)
    assert jsonable(rebuilt.versions) == jsonable(folded.versions)


# ---------------------------------------------------------------------------- R-22/D-22
def test_oracle_diff(corpus, folded):
    """diff snapshot vs VBHN TT39 = 0 mismatch chưa phân xử; VBHN lệch → chuông kêu."""
    from engine.oracle_diff import materialize_doc, oracle_diff

    as_of = date(2024, 3, 1)                             # sau TT06, trước TT12
    snap = materialize_doc(corpus.nodes, folded.versions, "39/2016/TT-NHNN", as_of)
    assert "dieu:7" in snap and "(bản TT06/2023)" in snap["dieu:7"]
    assert "dieu:8/khoan:8" not in snap                  # đang treo → không có text active

    vbhn = dict(snap)                                    # VBHN khớp hoàn toàn
    assert oracle_diff(snap, vbhn, "39/2016/TT-NHNN") == []

    vbhn_sai = dict(snap)
    vbhn_sai["dieu:7"] = vbhn_sai["dieu:7"].replace("18 tuổi", "16 tuổi")
    del vbhn_sai["dieu:13"]
    mismatches = oracle_diff(snap, vbhn_sai, "39/2016/TT-NHNN")
    kinds = {(m.path, m.kind) for m in mismatches}
    assert ("dieu:7", "text_mismatch") in kinds
    assert ("dieu:13", "missing_in_oracle") in kinds
    assert len(mismatches) == 2


# ---------------------------------------------------------------------------- D-02/R-2
def test_k_cutoff(corpus):
    """K=2023-08-20: chưa thấy TT10 (ingested 25/08) → k8 ACTIVE từ 01/09/2023 —
    'lúc đó ngân hàng có thể biết gì' (trục K)."""
    cf = _fold(corpus, k_cutoff=AS_KNOWN_BEFORE_TT10)
    k8 = corpus.node("39/2016/TT-NHNN", "dieu:8/khoan:8")
    versions = cf.versions[k8.id]
    assert [(v.status, v.valid_from, v.valid_to) for v in versions] == [
        ("active", date(2023, 9, 1), None)]              # theo hiểu biết tại K: sẽ có hiệu lực
    assert cf.open_suspensions == ()                     # TT10 chưa được biết đến
    # còn hiện tại (K=None): đang treo
    now = _fold(corpus)
    assert [v.status for v in now.versions[k8.id]] == ["suspended"]
    # các op ingest sau K cũng vô hình: Đ7 chỉ có bản gốc + TT06
    d7 = corpus.node("39/2016/TT-NHNN", "dieu:7")
    assert [(v.valid_from, v.valid_to) for v in cf.versions[d7.id]] == [
        (date(2017, 3, 15), date(2023, 9, 1)), (date(2023, 9, 1), None)]


# ---------------------------------------------------------------------------- bẫy 7 (02 §7)
def test_same_day_tiebreak(corpus, folded):
    """TT06+TT10 cùng valid_from 01/09/2023 cùng hạng: tie-break canonical
    (issued_date, seq) — đổi thứ tự nạp không đổi kết quả."""
    k8 = corpus.node("39/2016/TT-NHNN", "dieu:8/khoan:8")
    v = folded.versions[k8.id][0]
    ins, sus = corpus.op("op:tt06-insert-k8"), corpus.op("op:tt10-suspend-k8")
    # canonical: TT06 (issued 28/06) áp trước TT10 (issued 23/08) → suspend đè lên insert
    assert v.provenance == (ins.id, sus.id)
    assert v.status == "suspended" and v.body == "Để gửi tiền."

    reversed_ops = list(reversed(corpus.ops))
    assert state_digest(_fold(corpus, reversed_ops)) == state_digest(folded)


# ---------------------------------------------------------------------------- D-14
def test_blanket_no_mutation(corpus, folded):
    """blanket_derogation KHÔNG mutate state — chỉ seed conflict screening."""
    blanket = corpus.op("op:tt06-blanket")
    without = _fold(corpus, [o for o in corpus.ops if o.id != blanket.id])
    assert versions_digest(without) == versions_digest(folded)   # effective state y hệt
    assert folded.screening_seeds and any(s.op_id == blanket.id
                                          for s in folded.screening_seeds)
    assert all(blanket.id not in v.provenance
               for vs in folded.versions.values() for v in vs)
