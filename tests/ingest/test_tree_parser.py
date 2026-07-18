"""tree_parser — D-16 state machine: đủ tầng, heading/body, quote suppression, ngày."""
from datetime import date

from ingest.normalize import normalize
from ingest.tree_parser import parse_document, strip_quoted_new_text

from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts


def _parse(doc_key: str):
    return parse_document(normalize(fixture_texts()[doc_key]))


# ---- exit-style: đếm node khớp counts đếm tay của TỪNG fixture ----------------

def test_counts_match_hand_counted_all_fixtures():
    texts = fixture_texts()
    mismatches = []
    for entry in FIXTURE_ENTRIES:
        doc = parse_document(normalize(texts[entry["doc_key"]]))
        got = doc.counts()
        if got != entry["counts"]:
            mismatches.append((entry["doc_key"], entry["counts"], got))
    assert not mismatches, "Parser đếm lệch counts đếm tay:\n" + "\n".join(
        f"  {k}: expected={e} got={g}" for k, e, g in mismatches)


# ---- cấu trúc chi tiết -------------------------------------------------------

def test_heading_body_split():
    doc = _parse("39/2016/TT-NHNN")
    d8 = doc.node_at("dieu:8")
    assert d8.heading == "Những nhu cầu vốn không được cho vay"
    assert "không được cho vay đối với các nhu cầu vốn" in d8.body
    # thân của khoản KHÔNG nằm trong body của điều (chunk = node — D-17)
    assert "vàng miếng" not in d8.body
    assert doc.node_at("dieu:8/khoan:4").body == "Để mua vàng miếng."


def test_diem_vietnamese_alphabet_and_tiet():
    doc = _parse("39/2016/TT-NHNN")
    assert doc.node_at("dieu:13/khoan:2/diem:đ") is not None       # đ trong bảng chữ VN
    assert doc.node_at("dieu:31/khoan:1/diem:a/tiet:i") is not None
    assert doc.node_at("dieu:31/khoan:1/diem:a/tiet:ii") is not None
    # điểm b đứng SAU tiết — phải thoát về đúng cấp điểm
    assert doc.node_at("dieu:31/khoan:1/diem:b") is not None


def test_phuluc_first_class_node():
    doc = _parse("39/2016/TT-NHNN")
    pl = doc.node_at("phuluc:01")
    assert pl is not None and pl.level == "phuluc"
    assert "BẢNG KÊ" in (pl.heading or "") or "BẢNG KÊ" in pl.body


def test_quoted_text_does_not_create_nodes():
    doc = _parse("06/2023/TT-NHNN")
    # quote chứa "8." "9." "10." và "a)" "b)" — KHÔNG được thành node
    assert doc.node_at("dieu:8") is None
    assert all(n.path.split("/")[0] in ("dieu:1", "dieu:2", "dieu:3", "dieu:4", "preamble")
               for n in doc.nodes)
    k2 = doc.node_at("dieu:1/khoan:2")
    assert "Để gửi tiền" in k2.body                    # text quote nằm trong body node amending


def test_heading_only_dieu_op_in_heading():
    doc = _parse("08/2026/TT-NHNN")
    d2 = doc.node_at("dieu:2")
    assert d2.heading.startswith("Bãi bỏ khoản 2 Điều 1")
    assert d2.body == ""


def test_dates_issued_and_effective():
    doc = _parse("06/2023/TT-NHNN")
    assert doc.issued_date == date(2023, 6, 28)
    assert doc.effective_date == date(2023, 9, 1)
    doc39 = _parse("39/2016/TT-NHNN")
    assert doc39.issued_date == date(2016, 12, 30)
    assert doc39.effective_date == date(2017, 3, 15)


def test_effective_ngay_ky():
    doc = _parse("DC-01/2026")
    assert doc.effective_date == doc.issued_date == date(2026, 6, 20)


def test_doc_key_patched_from_broken_header():
    # header fixture cố tình vỡ: '39 /2016/TT- NHNN'
    doc = _parse("39/2016/TT-NHNN")
    assert doc.doc_key == "39/2016/TT-NHNN"


def test_can_cu_collected():
    doc = _parse("39/2016/TT-NHNN")
    assert len(doc.can_cu_lines) == 3
    assert all(ln.startswith("Căn cứ") for ln in doc.can_cu_lines)


def test_chapter_context_stack_omnibus():
    doc = _parse("11/2026/TT-NHNN")
    d1 = doc.node_at("dieu:1")
    d3 = doc.node_at("dieu:3")
    assert any("39/2016/TT-NHNN" in c for c in d1.chapter_ctx)
    assert any("22/2019/TT-NHNN" in c for c in d3.chapter_ctx)


def test_signature_block_not_in_body():
    doc = _parse("39/2016/TT-NHNN")
    last = doc.node_at("dieu:34/khoan:2")
    assert "Nơi nhận" not in last.body
    assert "THỐNG ĐỐC" not in last.body


def test_strip_quoted_new_text():
    assert strip_quoted_new_text("“8. Để gửi tiền.”.") == "8. Để gửi tiền."
    assert strip_quoted_new_text('"văn bản".') == "văn bản"


def test_khoan_chen_1a_and_dieu_suffix():
    text = normalize("""Số: 99/2026/TT-NHNN
Hà Nội, ngày 01 tháng 01 năm 2026
THÔNG TƯ THỬ
Điều 24a. Điều chèn
1. Khoản một.
1a. Khoản chèn một a.
2. Khoản hai.
Điều 32đ. Điều chèn đ
1. Nội dung.
""")
    doc = parse_document(text)
    assert doc.node_at("dieu:24a") is not None
    assert doc.node_at("dieu:24a/khoan:1a") is not None
    assert doc.node_at("dieu:32đ") is not None


def test_ambiguous_roman_diem_sequence():
    # 'i)' sau 'h)' là ĐIỂM i; '(ii)' trong điểm là TIẾT
    text = normalize("""Số: 98/2026/TT-NHNN
Hà Nội, ngày 01 tháng 01 năm 2026
THÔNG TƯ THỬ
Điều 1. Danh sách dài
1. Khoản một:
g) điểm g;
h) điểm h;
i) điểm i;
k) điểm k.
""")
    doc = parse_document(text)
    assert doc.node_at("dieu:1/khoan:1/diem:i") is not None
    assert doc.node_at("dieu:1/khoan:1/diem:k") is not None
    assert not any(n.level == "tiet" for n in doc.nodes)
