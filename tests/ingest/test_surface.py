"""surface — ngữ pháp địa chỉ + expand enumeration (02§5.1)."""
from ingest.surface import parse_surface


def _paths(s: str):
    groups = parse_surface(s)
    assert groups, f"không parse được: {s!r}"
    return groups[0].paths, groups[0]


def test_spec_example_4_edges():
    # ví dụ NGUYÊN VĂN 02§5.1: "điểm a, b, c và đ khoản 1 Điều 39" → 4 ref
    paths, _ = _paths("các điểm a, b, c và đ khoản 1 Điều 39")
    assert paths == ["dieu:39/khoan:1/diem:a", "dieu:39/khoan:1/diem:b",
                     "dieu:39/khoan:1/diem:c", "dieu:39/khoan:1/diem:đ"]


def test_spec_example_3_ops():
    paths, _ = _paths("khoản 8, khoản 9 và khoản 10 Điều 8")
    assert paths == ["dieu:8/khoan:8", "dieu:8/khoan:9", "dieu:8/khoan:10"]


def test_doc_ref_by_number():
    paths, g = _paths("khoản 2 Điều 8 Thông tư số 39/2016/TT-NHNN")
    assert paths == ["dieu:8/khoan:2"]
    assert "39/2016/TT-NHNN" in g.doc_surface


def test_doc_ref_cua_form():
    paths, g = _paths("khoản 8 Điều 8 của Thông tư số 39/2016/TT-NHNN")
    assert paths == ["dieu:8/khoan:8"]
    assert g.doc_surface is not None


def test_doc_ref_by_date():
    _, g = _paths("Điều 468 Bộ luật Dân sự ngày 24 tháng 11 năm 2015")
    assert g.doc_surface is not None and "ngày 24 tháng 11 năm 2015" in g.doc_surface


def test_doc_this_binding_marker():
    _, g = _paths("khoản 2 Điều 2 Thông tư này")
    assert g.doc_this is True


def test_relative_container_dieu_nay():
    paths, g = _paths("khoản 5 Điều này")
    assert paths == ["khoan:5"]
    assert g.relative_container == "dieu"


def test_paired_diem_khoan():
    paths, _ = _paths("điểm a khoản 1, điểm b khoản 2 Điều 20")
    assert paths == ["dieu:20/khoan:1/diem:a", "dieu:20/khoan:2/diem:b"]


def test_dieu_enumeration():
    paths, _ = _paths("Điều 19, 20 và 21")
    assert paths == ["dieu:19", "dieu:20", "dieu:21"]


def test_khoan_suffix_and_diem_digit():
    paths, _ = _paths("điểm a1 khoản 1a Điều 24a")
    assert paths == ["dieu:24a/khoan:1a/diem:a1"]


def test_phu_luc():
    paths, _ = _paths("Phụ lục 01 Thông tư số 39/2016/TT-NHNN")
    assert paths == ["phuluc:01"]


def test_mixed_tiet():
    paths, _ = _paths("tiết a(iii) khoản 2 Điều 5")
    assert paths == ["dieu:5/khoan:2/diem:a/tiet:iii"]


def test_two_separate_groups():
    groups = parse_surface("quy định tại khoản 3 Điều 7 áp dụng cùng khoản 1 Điều 13")
    all_paths = [p for g in groups for p in g.paths]
    assert "dieu:7/khoan:3" in all_paths and "dieu:13/khoan:1" in all_paths


def test_diem_c_va_diem_d():
    paths, _ = _paths("điểm c và điểm d khoản 2 Điều 13 Thông tư số 39/2016/TT-NHNN")
    assert paths == ["dieu:13/khoan:2/diem:c", "dieu:13/khoan:2/diem:d"]


def test_no_false_positive_on_plain_text():
    assert parse_surface("Tổ chức tín dụng không được cho vay để mua vàng miếng.") == []
