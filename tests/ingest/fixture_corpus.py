"""Fixture mini-corpus của F3 (KHÔNG phải corpus/ — F2 sở hữu corpus thật).

Mỗi văn bản mini được thiết kế để đâm trúng các bẫy 02§7 thuộc tầng ingest:
#1 NFC · #2 số hiệu vỡ ("39 /2016/TT- NHNN") · #3 ngưng≠bãi bỏ (TT10) · #4 target
chưa hiệu lực (TT10×TT06) · #5 valid_to theo sự kiện · #8 binding trong quote (TT28)
· #9 omnibus theo Chương (TT11) · #10 hiệu lực phân kỳ (TT11) · #11 op heading/Phụ lục
(TT06/TT11) · #14 amending-role vs transition/effectivity (TT06) · #15-alias (TT28 Đ7a)
· #16 VBHN oracle · #17 seq trong artifact (TT28).

`counts` là số ĐẾM TAY — exit test tầng fixture (mirror giao thức R-4).
"""
from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

FIXTURE_ENTRIES: list[dict] = [
    {
        "doc_key": "39/2016/TT-NHNN", "file": "tt39_2016_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2016-12-30", "effective_date": "2017-03-15", "synthetic": True,
        "counts": {"dieu": 7, "khoan": 19, "diem": 7, "tiet": 2, "phuluc": 1},
        "amending_nodes": [],
        "expected_ops": [
            {"kind": "repeal", "target_contains": "1627/2001/QĐ-NHNN",
             "valid_from": "2017-03-15"},          # repeal toàn văn bản → nhắm Norm
            {"kind": "norm_decl", "valid_from": "2017-03-15"},   # kế vị (D-09)
        ],
        "expected_edges_sample": [
            {"src": "preamble", "kind": "tham_quyen"},
            {"src": "dieu:7/khoan:1", "kind": "dinh_nghia", "dst": "dieu:2/khoan:2"},
            {"src": "dieu:7/khoan:2", "kind": "ngoai_le", "dst": "dieu:8"},
            {"src": "dieu:8/khoan:6", "kind": "ngoai_le", "dst": "dieu:8/khoan:5"},
            {"src": "dieu:13/khoan:1", "kind": "ngoai_le", "dst": "dieu:13/khoan:2"},
            {"src": "dieu:31/khoan:2", "kind": "chu_de"},
        ],
    },
    {
        "doc_key": "22/2019/TT-NHNN", "file": "tt22_2019_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2019-11-15", "effective_date": "2020-01-01", "synthetic": True,
        "counts": {"dieu": 2, "khoan": 4, "diem": 4, "tiet": 0, "phuluc": 0},
        "amending_nodes": [],
        "expected_ops": [],
        "expected_edges_sample": [{"src": "preamble", "kind": "tham_quyen"}],
    },
    {
        "doc_key": "26/2022/TT-NHNN", "file": "tt26_2022_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2022-12-31", "effective_date": "2022-12-31", "synthetic": True,
        "counts": {"dieu": 2, "khoan": 2, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": ["dieu:1/khoan:1", "dieu:1/khoan:2"],
        "expected_ops": [
            {"kind": "amend", "target": ("22/2019/TT-NHNN", "dieu:20/khoan:3"),
             "valid_from": "2022-12-31"},
            {"kind": "amend", "target": ("22/2019/TT-NHNN", "dieu:20/khoan:4"),
             "valid_from": "2022-12-31"},
        ],
        "expected_edges_sample": [],
    },
    {
        "doc_key": "06/2023/TT-NHNN", "file": "tt06_2023_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2023-06-28", "effective_date": "2023-09-01", "synthetic": True,
        "counts": {"dieu": 4, "khoan": 5, "diem": 0, "tiet": 0, "phuluc": 0},
        # dieu:1 = container "một số điều" → KHÔNG amending; khoan:5 "Bãi bỏ …" không
        # quote → KHÔNG amending (R-3: động-từ-hiệu-lực + QUOTE; khớp quy ước manifest F2)
        "amending_nodes": ["dieu:1/khoan:1", "dieu:1/khoan:2", "dieu:1/khoan:3",
                           "dieu:1/khoan:4"],
        "non_amending_nodes": ["dieu:2", "dieu:3", "dieu:4"],   # bẫy #14
        "expected_ops": [
            {"kind": "amend", "target": ("39/2016/TT-NHNN", "dieu:2/khoan:2"),
             "valid_from": "2023-09-01"},
            {"kind": "insert", "target": ("39/2016/TT-NHNN", "dieu:8/khoan:8"),
             "valid_from": "2023-09-01", "new_text_contains": "gửi tiền"},
            {"kind": "insert", "target": ("39/2016/TT-NHNN", "dieu:8/khoan:9"),
             "valid_from": "2023-09-01", "new_text_contains": "góp vốn"},
            {"kind": "insert", "target": ("39/2016/TT-NHNN", "dieu:8/khoan:10"),
             "valid_from": "2023-09-01", "new_text_contains": "bù đắp tài chính"},
            {"kind": "amend", "target": ("39/2016/TT-NHNN", "dieu:13"),
             "target_part": "heading", "new_heading_contains": "Lãi suất, phí cho vay"},
            {"kind": "insert", "target": ("39/2016/TT-NHNN", "dieu:32a"),
             "new_text_contains": "phương tiện điện tử"},
            {"kind": "repeal", "target": ("39/2016/TT-NHNN", "dieu:13/khoan:2"),
             "valid_from": "2023-09-01"},
        ],
        "expected_scope_predicate": {"contract_signed_before": "2023-09-01",
                                     "not_amended_on_or_after": "2023-09-01"},
        "expected_edges_sample": [{"src": "preamble", "kind": "tham_quyen"}],
    },
    {
        "doc_key": "10/2023/TT-NHNN", "file": "tt10_2023_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2023-08-23", "effective_date": "2023-09-01", "synthetic": True,
        "counts": {"dieu": 3, "khoan": 0, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": [],                      # không quote → không contaminate → retrievable
        "non_amending_nodes": ["dieu:1", "dieu:2", "dieu:3"],
        "expected_ops": [
            {"kind": "suspend", "target": ("39/2016/TT-NHNN", "dieu:8/khoan:8"),
             "valid_from": "2023-09-01", "has_valid_to_event": True},
            {"kind": "suspend", "target": ("39/2016/TT-NHNN", "dieu:8/khoan:9"),
             "valid_from": "2023-09-01", "has_valid_to_event": True},
            {"kind": "suspend", "target": ("39/2016/TT-NHNN", "dieu:8/khoan:10"),
             "valid_from": "2023-09-01", "has_valid_to_event": True},
        ],
        "expected_edges_sample": [{"src": "preamble", "kind": "tham_quyen"}],
    },
    {
        "doc_key": "08/2026/TT-NHNN", "file": "tt08_2026_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2026-01-05", "effective_date": "2026-02-01", "synthetic": True,
        "counts": {"dieu": 3, "khoan": 0, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": ["dieu:1"],              # dieu:2 "Bãi bỏ…" không quote
        "expected_ops": [
            {"kind": "amend", "target": ("22/2019/TT-NHNN", "dieu:20/khoan:2/diem:a"),
             "valid_from": "2026-02-01"},
            {"kind": "repeal", "target_op_from": ("26/2022/TT-NHNN", "dieu:1/khoan:2"),
             "valid_from": "2026-02-01"},          # op-nhắm-op (D-10, R-12)
        ],
        "expected_edges_sample": [],
    },
    {
        "doc_key": "11/2026/TT-NHNN", "file": "tt11_2026_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2026-01-15", "effective_date": "2026-03-01", "synthetic": True,
        "counts": {"dieu": 5, "khoan": 2, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": ["dieu:1", "dieu:2", "dieu:3"],   # dieu:4 "Bãi bỏ…" không quote
        "non_amending_nodes": ["dieu:4", "dieu:5"],
        "expected_ops": [
            {"kind": "amend", "target": ("39/2016/TT-NHNN", "dieu:31/khoan:1/diem:b"),
             "valid_from": "2026-03-01"},                       # Chương I → TT39 (bẫy #9)
            {"kind": "amend", "target": ("39/2016/TT-NHNN", "phuluc:01"),
             "valid_from": "2026-07-01"},                       # op nhắm Phụ lục + phân kỳ (#10, #11)
            {"kind": "amend", "target": ("22/2019/TT-NHNN", "dieu:20/khoan:1"),
             "valid_from": "2026-03-01"},                       # Chương II → TT22 (bẫy #9)
            {"kind": "repeal", "target": ("39/2016/TT-NHNN", "dieu:13/khoan:2/diem:c"),
             "valid_from": "2026-03-01"},
            {"kind": "repeal", "target": ("39/2016/TT-NHNN", "dieu:13/khoan:2/diem:d"),
             "valid_from": "2026-03-01"},
        ],
        "expected_edges_sample": [],
    },
    {
        "doc_key": "32/2026/TT-NHNN", "file": "tt32_2026_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2026-02-01", "effective_date": "2026-06-01", "synthetic": True,
        "counts": {"dieu": 4, "khoan": 3, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": [],
        "expected_ops": [
            {"kind": "repeal", "target_contains": "22/2019/TT-NHNN",
             "valid_from": "2026-06-01"},          # thay thế → repeal toàn văn bản cũ
            {"kind": "norm_decl", "valid_from": "2026-06-01"},   # + kế vị norm
            {"kind": "blanket_derogation", "valid_from": "2026-06-01"},
        ],
        "expected_scope_predicate": {"contract_signed_before": "2026-06-01",
                                     "not_amended_on_or_after": "2026-06-01"},
        "expected_edges_sample": [{"src": "dieu:2", "kind": "chu_de"}],
    },
    {
        "doc_key": "28/2026/TT-NHNN", "file": "tt28_2026_mini.txt",
        "doc_type": "thong_tu", "issuer": "NHNN", "audience": "public",
        "issued_date": "2026-04-15", "effective_date": "2026-06-01", "synthetic": True,
        "counts": {"dieu": 2, "khoan": 2, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": ["dieu:1/khoan:1", "dieu:1/khoan:2"],   # dieu:1 = container
        "expected_ops": [
            {"kind": "insert", "target": ("39/2016/TT-NHNN", "dieu:7a"),
             "valid_from": "2026-06-01", "new_text_contains": "Thông tư này"},  # binding #8
            {"kind": "amend", "target": ("39/2016/TT-NHNN", "dieu:7/khoan:3"),
             "phrase": True},                                   # D-21 materialize
            {"kind": "amend", "target": ("39/2016/TT-NHNN", "dieu:13/khoan:2/diem:b"),
             "phrase": True},
        ],
        "expected_edges_sample": [],
    },
    {
        "doc_key": "DC-01/2026", "file": "dc01_2026_mini.txt",
        "doc_type": "quyet_dinh", "issuer": "NHNN", "audience": "public",
        "issued_date": "2026-06-20", "effective_date": "2026-06-20", "synthetic": True,
        "counts": {"dieu": 2, "khoan": 0, "diem": 0, "tiet": 0, "phuluc": 0},
        "amending_nodes": [],   # đính chính quote cụm từ lỗi in — không phải norm text
        "expected_ops": [
            {"kind": "dinh_chinh", "target": ("39/2016/TT-NHNN", "dieu:13/khoan:2/diem:b"),
             "new_text_contains": "xuất khẩu, nhập khẩu"},
        ],
        "expected_edges_sample": [],
    },
    {
        "doc_key": "20/VBHN-NHNN", "file": "vbhn_tt39_mini.txt",
        "doc_type": "vbhn", "issuer": "NHNN", "audience": "public", "is_oracle": True,
        "issued_date": "2023-09-12", "effective_date": None, "synthetic": True,
        "counts": {"dieu": 1, "khoan": 10, "diem": 2, "tiet": 0, "phuluc": 0},
        "amending_nodes": [],
        "expected_ops": [],                       # R-7: oracle không sinh op
        "expected_edges_sample": [],
    },
]


def fixture_texts() -> dict[str, str]:
    out = {}
    for e in FIXTURE_ENTRIES:
        p = FIXTURE_DIR / e["file"]
        out[e["doc_key"]] = p.read_text(encoding="utf-8")
    return out
