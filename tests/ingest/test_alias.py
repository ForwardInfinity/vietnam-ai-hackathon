"""alias — D-07/INV-11: cửa sổ thời gian, trôi số, resolve future/provisional (bẫy #4, #15)."""
from datetime import date
from uuid import uuid4

from ingest.alias import MemoryStore


def test_resolve_in_window():
    st = MemoryStore()
    n1 = uuid4()
    st.add_node(n1, "39/2016/TT-NHNN", "dieu:8", "rule")
    st.add_alias("39/2016/TT-NHNN", "dieu:8", n1, date(2017, 3, 15))
    res = st.resolve("39/2016/TT-NHNN", "dieu:8", date(2020, 1, 1))
    assert res.node_id == n1 and not res.provisional and not res.future


def test_alias_drift_insert_dieu_7a_closes_nothing_but_windows_unique():
    """Bẫy #15-alias: insert Điều 7a — địa chỉ mới mở cửa sổ từ ngày hiệu lực;
    TRƯỚC ngày đó địa chỉ không resolve (trừ future-fallback có cờ)."""
    st = MemoryStore()
    n7a = uuid4()
    st.add_node(n7a, "39/2016/TT-NHNN", "dieu:7a", "rule")
    st.add_alias("39/2016/TT-NHNN", "dieu:7a", n7a, date(2026, 6, 1))
    hit = st.resolve("39/2016/TT-NHNN", "dieu:7a", date(2026, 7, 1))
    assert hit.node_id == n7a and not hit.future
    early = st.resolve("39/2016/TT-NHNN", "dieu:7a", date(2026, 1, 1))
    assert early is not None and early.future        # bẫy #4: nhắm node chưa kịp hiệu lực


def test_repoint_surface_address_closes_old_window_inv11():
    """Trôi số thật (đánh lại số): cùng địa chỉ bề mặt re-point → cửa sổ cũ ĐÓNG,
    mỗi ngày đúng MỘT node (INV-11)."""
    st = MemoryStore()
    old, new = uuid4(), uuid4()
    st.add_node(old, "X", "dieu:8", "rule")
    st.add_node(new, "X", "dieu:8", "rule")
    st.add_alias("X", "dieu:8", old, date(2017, 1, 1))
    st.add_alias("X", "dieu:8", new, date(2026, 6, 1))
    assert st.resolve("X", "dieu:8", date(2020, 1, 1)).node_id == old
    assert st.resolve("X", "dieu:8", date(2026, 6, 1)).node_id == new
    # cửa sổ không chồng lấn
    rows = [r for r in st.aliases if r.doc_key == "X" and r.path == "dieu:8"]
    old_row = next(r for r in rows if r.node_id == old)
    assert old_row.valid_to == date(2026, 6, 1)


def test_provisional_fallback_via_node_table():
    """Bẫy #4 TT10×TT06: node birth do op đề xuất tạo, CHƯA có alias (R-12) —
    resolver fallback bảng node, đánh dấu provisional."""
    st = MemoryStore()
    k8 = uuid4()
    st.add_node(k8, "39/2016/TT-NHNN", "dieu:8/khoan:8", "rule")
    res = st.resolve("39/2016/TT-NHNN", "dieu:8/khoan:8", date(2023, 8, 23))
    assert res is not None and res.provisional
