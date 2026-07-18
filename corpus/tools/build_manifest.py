#!/usr/bin/env python3
"""Build corpus/manifest.json — ground truth per 04-CORPUS-AND-EVAL §1.4.

sha256 + counts are computed live from corpus/text/*.txt (counts = count_grammar,
cross-validated by verify_counts_sequential). expected_ops / expected_transitions /
expected_norm_events / expected_edges_sample / amending_nodes are hand-curated from
the source texts; every target_surface / quote is asserted (by validate_manifest.py)
to be a literal substring of the source text.
"""
import hashlib, json, pathlib, sys, unicodedata

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent
sys.path.insert(0, str(HERE))
from count_grammar import count  # noqa: E402

META = {
    "version": "1.0",
    "generated_by": "corpus/tools/build_manifest.py",
    "conventions": {
        "path": "dieu:<n>[/khoan:<n>][/diem:<chữ>][/tiet:<roman>] | phuluc:<n>; đường dẫn trong văn bản NGUỒN của op trừ khi ghi target_doc",
        "counts": "đếm theo grammar 02 §1 trên FILE text (line-anchored, quote-depth 0, khoản/điểm/tiết chỉ trong ngữ cảnh Điều; nội dung Phụ lục là blob D-49, không đếm khoản bên trong). Hai phương pháp độc lập: tools/count_grammar.py (pattern) và tools/verify_counts_sequential.py (sequence-validated) phải khớp.",
        "op_kinds": "amend|insert|repeal|suspend|close_window|dinh_chinh|norm_decl|blanket_derogation (02 §3); suspend ≠ repeal; repeal có thể target op (target_is_op)",
        "expected_transitions": "điều khoản chuyển tiếp trích thành DSL D-25 — tách khỏi expected_ops vì transition không mutate node, nó sinh scope-split",
        "valid_from": "ngày op có hiệu lực, đọc từ chính văn bản; dinh_chinh hồi tố về ĐẦU cửa sổ của version bị đính chính (D-12)",
        "amending_nodes": "node chứa động-từ-hiệu-lực + TEXT QUOTE (role amending, D-05, loại khỏi retrieval); điều repeal thuần không quote không nằm ở đây",
        "edges": "kiểu theo 02 §5.2: tham_quyen|dinh_nghia|ngoai_le|chuyen_tiep|chu_de|frontier|pinpoint (pinpoint = trích dẫn đích danh không thuộc 5 loại mandatory)",
    },
}

T = lambda slug: (CORPUS / 'text' / f'{slug}.txt').read_text(encoding='utf-8')


def doc(**kw):
    d = {
        "doc_key": None, "slug": None, "title": None, "doc_type": None,
        "sha256": None, "issued_date": None, "issued_date_quote": None,
        "effective_date": None, "effective_date_quote": None,
        "synthetic": False, "is_oracle": False, "excerpt": False, "excerpt_spec": None,
        "audience": "public", "channel": None, "owner": None, "source_url": None,
        "transcription_notes": [], "counts": None,
        "expected_ops": [], "expected_transitions": [], "expected_norm_events": [],
        "expected_edges_sample": [], "amending_nodes": [],
    }
    d.update(kw)
    return d


def op(seq, kind, source_path, target_doc, target_surface, valid_from, **kw):
    o = {"seq": seq, "kind": kind, "source_path": source_path, "target_doc": target_doc,
         "target_surface": target_surface, "valid_from": valid_from,
         "target_part": kw.pop("target_part", "body"),
         "target_is_op": kw.pop("target_is_op", False)}
    o.update(kw)
    return o


def edge(source_path, etype, target, surface):
    return {"source_path": source_path, "type": etype, "target": target, "surface": surface}


DOCS = []

# ============================== CORPUS THẬT ==============================

DOCS.append(doc(
    doc_key="39/2016/TT-NHNN", slug="tt-39-2016-tt-nhnn",
    title="Thông tư quy định về hoạt động cho vay của tổ chức tín dụng, chi nhánh ngân hàng nước ngoài đối với khách hàng",
    doc_type="thong_tu", channel="luatvietnam",
    issued_date="2016-12-30", issued_date_quote="Hà Nội, ngày 30 tháng 12 năm 2016",
    effective_date="2017-03-15", effective_date_quote="Thông tư này có hiệu lực thi hành kể từ ngày 15 tháng 3 năm 2017.",
    transcription_notes=[
        "bản luatvietnam là bản gốc 2016 (đối chiếu Đ8 6-khoản, ngôn ngữ tiền-TT06)",
        "đã bỏ 1 dòng chú thích biên tập chèn inline (điểm c(iv) k2 Đ22 — nội dung TT12/2024) và các marker 'Bổ sung' của trang web",
        "1 dòng khoản bị tách số ('1.' đứng riêng tại k1 Đ27) đã ghép lại",
    ],
    expected_ops=[
        op(1, "repeal", "dieu:33/khoan:2/diem:a", "1627/2001/QĐ-NHNN", "Quyết định số 1627/2001/QĐ-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(2, "repeal", "dieu:33/khoan:2/diem:b", "28/2002/QĐ-NHNN", "Quyết định số 28/2002/QĐ-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(3, "repeal", "dieu:33/khoan:2/diem:c", "127/2005/QĐ-NHNN", "Quyết định số 127/2005/QĐ-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(4, "repeal", "dieu:33/khoan:2/diem:d", "783/2005/QĐ-NHNN", "Quyết định số 783/2005/QĐ-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(5, "repeal", "dieu:33/khoan:2/diem:đ", "12/2010/TT-NHNN", "Thông tư số 12/2010/TT-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(6, "repeal", "dieu:33/khoan:2/diem:e", "05/2011/TT-NHNN", "Thông tư số 05/2011/TT-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(7, "repeal", "dieu:33/khoan:2/diem:g", "33/2011/TT-NHNN", "Thông tư số 33/2011/TT-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(8, "repeal", "dieu:33/khoan:2/diem:h", "08/2014/TT-NHNN", "Thông tư số 08/2014/TT-NHNN", "2017-03-15", notes="out-of-corpus"),
        op(9, "norm_decl", "dieu:33/khoan:2", "39/2016/TT-NHNN", "các văn bản sau đây hết hiệu lực thi hành", "2017-03-15",
           notes="TT39 kế vị QĐ 1627/2001 với tư cách norm 'quy chế cho vay' (D-09)"),
    ],
    expected_transitions=[{
        "source_path": "dieu:34",
        "surface": "Đối với các hợp đồng tín dụng được ký kết trước ngày Thông tư này có hiệu lực thi hành",
        "scope_predicate": {"contract_signed_before": "2017-03-15"},
    }],
    expected_norm_events=[{"norm": "hoat-dong-cho-vay", "event": "succession",
                           "from": "1627/2001/QĐ-NHNN", "to": "39/2016/TT-NHNN", "at": "2017-03-15"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Luật Ngân hàng Nhà nước Việt Nam 2010", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam ngày 16 tháng 6 năm 2010"),
        edge("preamble", "tham_quyen", "47/2010/QH12", "Căn cứ Luật Các tổ chức tín dụng ngày 16 tháng 6 năm 2010"),
        edge("dieu:26/khoan:1", "pinpoint", "47/2010/QH12 dieu:126,127,128", "Điều 126, Điều 127, Điều 128 Luật các tổ chức tín dụng"),
        edge("dieu:26/khoan:1", "chu_de", "NORM:gioi-han-ty-le-bao-dam-an-toan", "quy định của Ngân hàng Nhà nước Việt Nam về các giới hạn, tỷ lệ bảo đảm an toàn trong hoạt động của tổ chức tín dụng"),
        edge("dieu:7/khoan:5", "dinh_nghia", "SELF dieu:13/khoan:2", "lãi suất cho vay quy định tại khoản 2 Điều 13 Thông tư này"),
        edge("dieu:25/khoan:1", "ngoai_le", "SELF dieu:13/khoan:4", "trừ trường hợp quy định tại khoản 4 Điều 13 Thông tư này"),
        edge("dieu:34", "chuyen_tiep", "COHORT:contract_signed_before=2017-03-15", "hợp đồng tín dụng được ký kết trước ngày Thông tư này có hiệu lực thi hành"),
    ],
))

DOCS.append(doc(
    doc_key="06/2023/TT-NHNN", slug="tt-06-2023-tt-nhnn",
    title="Thông tư sửa đổi, bổ sung một số điều của Thông tư số 39/2016/TT-NHNN",
    doc_type="thong_tu", channel="luatvietnam",
    issued_date="2023-06-28", issued_date_quote="Hà Nội, ngày 28 tháng 6 năm 2023",
    effective_date="2023-09-01", effective_date_quote="Thông tư này có hiệu lực thi hành từ ngày 01 tháng 9 năm 2023",
    transcription_notes=[
        "đối chiếu Công báo (congbao.chinhphu.vn 813+814): Ban hành 28/06/2023, Hiệu lực 01/09/2023 — khớp",
        "typo transcription giữ nguyên: 'Điều 32c. Dư nự cho vay', 'thiêt lập', 'phưong tiện' (trap 02 §7.18)",
    ],
    expected_ops=[
        op(1, "amend", "dieu:1/khoan:1/diem:a", "39/2016/TT-NHNN", "điểm c khoản 6", "2023-09-01", target_path="dieu:2/khoan:6/diem:c"),
        op(2, "insert", "dieu:1/khoan:1/diem:b", "39/2016/TT-NHNN", "Bổ sung khoản 12", "2023-09-01", target_path="dieu:2/khoan:12"),
        op(3, "amend", "dieu:1/khoan:2", "39/2016/TT-NHNN", "Sửa đổi, bổ sung Điều 8", "2023-09-01", target_path="dieu:8",
           notes="replace toàn Điều 8: 6 khoản → 10 khoản; khoản 8, 9, 10 là NODE MỚI (birth-id mới); con tái cấu trúc → tương chiếu non-binding D-08"),
        op(4, "amend", "dieu:1/khoan:3", "39/2016/TT-NHNN", "khoản 2 Điều 11", "2023-09-01", target_path="dieu:11/khoan:2"),
        op(5, "amend", "dieu:1/khoan:4", "39/2016/TT-NHNN", "khoản 2 Điều 13", "2023-09-01", target_path="dieu:13/khoan:2"),
        op(6, "amend", "dieu:1/khoan:5", "39/2016/TT-NHNN", "khoản 4 Điều 18", "2023-09-01", target_path="dieu:18/khoan:4"),
        op(7, "amend", "dieu:1/khoan:6/diem:a", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 1 như sau", "2023-09-01", target_path="dieu:22/khoan:1"),
        op(8, "amend", "dieu:1/khoan:6/diem:b", "39/2016/TT-NHNN", "điểm a khoản 2", "2023-09-01", target_path="dieu:22/khoan:2/diem:a"),
        op(9, "amend", "dieu:1/khoan:6/diem:c", "39/2016/TT-NHNN", "điểm b khoản 2", "2023-09-01", target_path="dieu:22/khoan:2/diem:b"),
        op(10, "amend", "dieu:1/khoan:6/diem:d", "39/2016/TT-NHNN", "điểm c khoản 2", "2023-09-01", target_path="dieu:22/khoan:2/diem:c"),
        op(11, "amend", "dieu:1/khoan:6/diem:đ", "39/2016/TT-NHNN", "điểm e khoản 2", "2023-09-01", target_path="dieu:22/khoan:2/diem:e"),
        op(12, "amend", "dieu:1/khoan:6/diem:e", "39/2016/TT-NHNN", "điểm g khoản 2", "2023-09-01", target_path="dieu:22/khoan:2/diem:g"),
        op(13, "amend", "dieu:1/khoan:7", "39/2016/TT-NHNN", "điểm b khoản 4 Điều 23", "2023-09-01", target_path="dieu:23/khoan:4/diem:b"),
        op(14, "amend", "dieu:1/khoan:8", "39/2016/TT-NHNN", "khoản 2 Điều 24", "2023-09-01", target_path="dieu:24/khoan:2",
           notes="op này bị BÃI BỎ bởi khoản 2 Điều 4 TT12/2024 từ 2024-07-01 (op-nhắm-op thật)"),
        op(15, "amend", "dieu:1/khoan:9/diem:a", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 2 như sau", "2023-09-01", target_path="dieu:26/khoan:2"),
        op(16, "insert", "dieu:1/khoan:9/diem:b", "39/2016/TT-NHNN", "Bổ sung khoản 5 như sau", "2023-09-01", target_path="dieu:26/khoan:5",
           notes="op này bị BÃI BỎ bởi khoản 2 Điều 4 TT12/2024 từ 2024-07-01"),
        op(17, "amend", "dieu:1/khoan:10/diem:a", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 1 như sau", "2023-09-01", target_path="dieu:27/khoan:1"),
        op(18, "amend", "dieu:1/khoan:10/diem:b", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 4 như sau", "2023-09-01", target_path="dieu:27/khoan:4"),
        op(19, "amend", "dieu:1/khoan:10/diem:c", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 5 như sau", "2023-09-01", target_path="dieu:27/khoan:5"),
        op(20, "insert", "dieu:1/khoan:11", "39/2016/TT-NHNN", "Bổ sung Mục 3 Chương II", "2023-09-01", target_path="chuong:II/muc:3",
           notes="sinh 8 node Điều mới: 32a, 32b, 32c, 32d, 32đ, 32e, 32g, 32h (cho vay bằng phương tiện điện tử)"),
        op(21, "repeal", "dieu:2", "39/2016/TT-NHNN", "Bãi bỏ khoản 5 Điều 7", "2023-09-01", target_path="dieu:7/khoan:5",
           notes="op nằm TRỌN trong heading — điều một dòng (trap 02 §7.11)"),
    ],
    expected_transitions=[{
        "source_path": "dieu:4/khoan:2",
        "surface": "các thỏa thuận cho vay, hợp đồng tín dụng được ký kết trước ngày Thông tư này có hiệu lực thi hành",
        "scope_predicate": {"contract_signed_before": "2023-09-01", "not_amended_on_or_after": "2023-09-01"},
    }],
    expected_norm_events=[{"norm": "cho-vay-bang-phuong-tien-dien-tu", "event": "birth",
                           "by": "06/2023/TT-NHNN dieu:1/khoan:11", "at": "2023-09-01"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Luật Ngân hàng Nhà nước Việt Nam 2010", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam ngày 16 tháng 6 năm 2010"),
        edge("preamble", "tham_quyen", "47/2010/QH12 + 17/2017/QH14", "Luật sửa đổi, bổ sung một số điều của Luật Các tổ chức tín dụng ngày 20 tháng 11 năm 2017"),
        edge("preamble", "tham_quyen", "102/2022/NĐ-CP", "Căn cứ Nghị định số 102/2022/NĐ-CP"),
        edge("dieu:4/khoan:2", "chuyen_tiep", "COHORT:contract_signed_before=2023-09-01", "tiếp tục thực hiện các nội dung trong thỏa thuận cho vay, hợp đồng tín dụng đã ký kết"),
        edge("dieu:3", "pinpoint", "SELF (thi hành)", "Chánh Văn phòng, Vụ trưởng Vụ Chính sách tiền tệ"),
    ],
    amending_nodes=["dieu:1/khoan:1", "dieu:1/khoan:2", "dieu:1/khoan:3", "dieu:1/khoan:4",
                    "dieu:1/khoan:5", "dieu:1/khoan:6", "dieu:1/khoan:7", "dieu:1/khoan:8",
                    "dieu:1/khoan:9", "dieu:1/khoan:10", "dieu:1/khoan:11"],
))

DOCS.append(doc(
    doc_key="10/2023/TT-NHNN", slug="tt-10-2023-tt-nhnn",
    title="Thông tư ngưng hiệu lực thi hành một số nội dung của Thông tư số 39/2016/TT-NHNN (đã được bổ sung tại Thông tư số 06/2023/TT-NHNN)",
    doc_type="thong_tu", channel="luatvietnam",
    issued_date="2023-08-23", issued_date_quote="Hà Nội, ngày 23 tháng 8 năm 2023",
    effective_date="2023-09-01", effective_date_quote="Thông tư này có hiệu lực thi hành từ ngày 01 tháng 9 năm 2023.",
    transcription_notes=["đối chiếu Công báo (congbao.chinhphu.vn): khớp ngày ban hành/hiệu lực"],
    expected_ops=[
        op(1, "suspend", "dieu:1", "39/2016/TT-NHNN", "khoản 8", "2023-09-01", target_path="dieu:8/khoan:8",
           valid_to_event="cho đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới quy định về các vấn đề này",
           notes="node đích được TT06 bổ sung, bị treo TRƯỚC khi kịp có hiệu lực → operative interval RỖNG"),
        op(2, "suspend", "dieu:1", "39/2016/TT-NHNN", "khoản 9", "2023-09-01", target_path="dieu:8/khoan:9",
           valid_to_event="cho đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới quy định về các vấn đề này"),
        op(3, "suspend", "dieu:1", "39/2016/TT-NHNN", "khoản 10 Điều 8", "2023-09-01", target_path="dieu:8/khoan:10",
           valid_to_event="cho đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới quy định về các vấn đề này"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Luật Ngân hàng Nhà nước Việt Nam 2010", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam ngày 16 tháng 6 năm 2010"),
        edge("preamble", "tham_quyen", "47/2010/QH12", "Căn cứ Luật Các tổ chức tín dụng ngày 16 tháng 6 năm 2010"),
        edge("preamble", "tham_quyen", "102/2022/NĐ-CP", "Căn cứ Nghị định số 102/2022/NĐ-CP"),
        edge("dieu:1", "pinpoint", "06/2023/TT-NHNN dieu:1/khoan:2", "đã được bổ sung theo khoản 2 Điều 1 Thông tư số 06/2023/TT-NHNN"),
        edge("dieu:1", "pinpoint", "39/2016/TT-NHNN dieu:8", "khoản 10 Điều 8 của Thông tư số 39/2016/TT-NHNN"),
    ],
))

DOCS.append(doc(
    doc_key="12/2024/TT-NHNN", slug="tt-12-2024-tt-nhnn",
    title="Thông tư sửa đổi, bổ sung một số điều của Thông tư số 39/2016/TT-NHNN",
    doc_type="thong_tu", channel="luatvietnam",
    issued_date="2024-06-28", issued_date_quote="Hà Nội, ngày 28 tháng 6 năm 2024",
    effective_date="2024-07-01", effective_date_quote="Thông tư này có hiệu lực từ ngày 01 tháng 7 năm 2024.",
    expected_ops=[
        op(1, "amend", "dieu:1/khoan:1/diem:a", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 1 như sau", "2024-07-01", target_path="dieu:2/khoan:1"),
        op(2, "insert", "dieu:1/khoan:1/diem:b", "39/2016/TT-NHNN", "Bổ sung khoản 13 như sau", "2024-07-01", target_path="dieu:2/khoan:13"),
        op(3, "insert", "dieu:1/khoan:1/diem:c", "39/2016/TT-NHNN", "Bổ sung khoản 14 như sau", "2024-07-01", target_path="dieu:2/khoan:14"),
        op(4, "amend", "dieu:1/khoan:2", "39/2016/TT-NHNN", "khoản 2 Điều 4", "2024-07-01", target_path="dieu:4/khoan:2"),
        op(5, "amend", "dieu:1/khoan:3", "39/2016/TT-NHNN", "khoản 3 Điều 7", "2024-07-01", target_path="dieu:7/khoan:3"),
        op(6, "amend", "dieu:1/khoan:4", "39/2016/TT-NHNN", "Sửa đổi, bổ sung Điều 9", "2024-07-01", target_path="dieu:9",
           notes="replace toàn Điều 9 → con mới (D-08)"),
        op(7, "amend", "dieu:1/khoan:5", "39/2016/TT-NHNN", "khoản 2 Điều 16", "2024-07-01", target_path="dieu:16/khoan:2"),
        op(8, "amend", "dieu:1/khoan:6/diem:a", "39/2016/TT-NHNN", "điểm b(iii) khoản 2", "2024-07-01", target_path="dieu:22/khoan:2/diem:b/tiet:iii",
           notes="target cấp TIẾT; chain-cite: Đ22 'đã được sửa đổi, bổ sung bởi điểm c, d khoản 6 Điều 1 Thông tư số 06/2023/TT-NHNN'"),
        op(9, "amend", "dieu:1/khoan:6/diem:b", "39/2016/TT-NHNN", "điểm c(iii) khoản 2", "2024-07-01", target_path="dieu:22/khoan:2/diem:c/tiet:iii"),
        op(10, "insert", "dieu:1/khoan:6/diem:c", "39/2016/TT-NHNN", "Bổ sung điểm c(iv) khoản 2", "2024-07-01", target_path="dieu:22/khoan:2/diem:c/tiet:iv"),
        op(11, "amend", "dieu:1/khoan:7", "39/2016/TT-NHNN", "Sửa đổi, bổ sung Điều 24", "2024-07-01", target_path="dieu:24",
           notes="replace toàn Điều 24 (bản đã được k8 Đ1 TT06 sửa) — chain qua op"),
        op(12, "amend", "dieu:1/khoan:8/diem:a", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 1 như sau", "2024-07-01", target_path="dieu:26/khoan:1"),
        op(13, "amend", "dieu:1/khoan:8/diem:b", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 3 như sau", "2024-07-01", target_path="dieu:26/khoan:3"),
        op(14, "insert", "dieu:1/khoan:8/diem:c", "39/2016/TT-NHNN", "Bổ sung khoản 5 như sau", "2024-07-01", target_path="dieu:26/khoan:5",
           notes="tái-sinh k5 Đ26 với text mới sau khi op TT06 (điểm b khoản 9 Đ1) bị bãi bỏ bởi chính TT12 — xem op 20"),
        op(15, "insert", "dieu:1/khoan:8/diem:d", "39/2016/TT-NHNN", "Bổ sung khoản 6 như sau", "2024-07-01", target_path="dieu:26/khoan:6"),
        op(16, "insert", "dieu:1/khoan:8/diem:đ", "39/2016/TT-NHNN", "Bổ sung khoản 7 như sau", "2024-07-01", target_path="dieu:26/khoan:7"),
        op(17, "repeal", "dieu:2", "39/2016/TT-NHNN", "Bãi bỏ Điều 29", "2024-07-01", target_path="dieu:29"),
        op(18, "repeal", "dieu:2", "39/2016/TT-NHNN", "Điều 32 Thông tư số 39/2016/TT-NHNN", "2024-07-01", target_path="dieu:32"),
        op(19, "repeal", "dieu:2", "39/2016/TT-NHNN", "Điều 32g Thông tư số 39/2016/TT-NHNN đã được sửa đổi, bổ sung bởi khoản 11 Điều 1 Thông tư số 06/2023/TT-NHNN", "2024-07-01", target_path="dieu:32g",
           notes="target là node do op TT06 k11 sinh ra"),
        op(20, "repeal", "dieu:4/khoan:2", "06/2023/TT-NHNN", "Bãi bỏ khoản 8, điểm b khoản 9 Điều 1 Thông tư số 06/2023/TT-NHNN", "2024-07-01",
           target_is_op=True, target_op={"doc": "06/2023/TT-NHNN", "paths": ["dieu:1/khoan:8", "dieu:1/khoan:9/diem:b"]},
           notes="OP-NHẮM-OP THẬT: 2 op đích (amend k2 Đ24, insert k5 Đ26 của TT06); cửa sổ 2023-09-01→2024-07-01 bất khả xâm phạm (D-10); liệt kê 1 entry vì cùng câu — extractor tách 2 op là hợp lệ"),
    ],
    expected_transitions=[{
        "source_path": "dieu:4/khoan:3",
        "surface": "các thỏa thuận cho vay, hợp đồng tín dụng được ký kết trước ngày Thông tư này có hiệu lực thi hành",
        "scope_predicate": {"contract_signed_before": "2024-07-01", "not_amended_on_or_after": "2024-07-01"},
    }],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng ngày 18 tháng 01 năm 2024"),
        edge("preamble", "tham_quyen", "102/2022/NĐ-CP", "Căn cứ Nghị định số 102/2022/NĐ-CP"),
        edge("dieu:1/khoan:1/diem:b", "pinpoint", "32/2024/QH15 dieu:102/khoan:2", "khoản 2 Điều 102 Luật Các tổ chức tín dụng"),
        edge("dieu:1/khoan:1/diem:c", "pinpoint", "32/2024/QH15 dieu:4/khoan:24", "khoản 24 Điều 4 Luật Các tổ chức tín dụng"),
        edge("dieu:4/khoan:3", "chuyen_tiep", "COHORT:contract_signed_before=2024-07-01", "tiếp tục thực hiện các nội dung trong thỏa thuận cho vay, hợp đồng tín dụng đã ký kết"),
    ],
    amending_nodes=["dieu:1/khoan:1", "dieu:1/khoan:2", "dieu:1/khoan:3", "dieu:1/khoan:4",
                    "dieu:1/khoan:5", "dieu:1/khoan:6", "dieu:1/khoan:7", "dieu:1/khoan:8"],
))

DOCS.append(doc(
    doc_key="91/2015/QH13", slug="blds-91-2015-qh13-trich",
    title="Bộ luật Dân sự (TRÍCH: Đ463–471 Mục 4 Hợp đồng vay tài sản + Đ688–689)",
    doc_type="bo_luat", channel="luatvietnam", excerpt=True,
    excerpt_spec="header; PHẦN THỨ BA/Chương XVI/Mục 4: Điều 463–471; PHẦN THỨ SÁU: Điều 688–689",
    issued_date="2015-11-24", issued_date_quote="thông qua ngày 24 tháng 11 năm 2015",
    effective_date="2017-01-01", effective_date_quote="Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2017.",
    expected_ops=[
        op(1, "repeal", "dieu:689", "33/2005/QH11", "Bộ luật dân sự số 33/2005/QH11 hết hiệu lực", "2017-01-01", notes="out-of-corpus"),
        op(2, "norm_decl", "dieu:689", "91/2015/QH13", "Bộ luật dân sự số 33/2005/QH11 hết hiệu lực kể từ ngày Bộ luật này có hiệu lực.", "2017-01-01"),
    ],
    expected_transitions=[{
        "source_path": "dieu:688/khoan:1",
        "surface": "giao dịch dân sự được xác lập trước ngày Bộ luật này có hiệu lực",
        "scope_predicate": {"contract_signed_before": "2017-01-01"},
        "notes": "Đ688 chi tiết hơn DSL D-25 v1 (phân nhánh đã/chưa thực hiện) — ghi xấp xỉ, chi tiết trong text",
    }],
    expected_norm_events=[{"norm": "bo-luat-dan-su", "event": "succession",
                           "from": "33/2005/QH11", "to": "91/2015/QH13", "at": "2017-01-01"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Hiến pháp 2013", "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam"),
        edge("dieu:468/khoan:1", "ngoai_le", "FRONTIER:luật khác có liên quan", "trừ trường hợp luật khác có liên quan quy định khác"),
        edge("dieu:468/khoan:2", "dinh_nghia", "SELF dieu:468/khoan:1", "mức lãi suất giới hạn quy định tại khoản 1 Điều này"),
        edge("dieu:466/khoan:4", "pinpoint", "SELF dieu:468/khoan:2", "lãi suất theo quy định tại khoản 2 Điều 468 của Bộ luật này"),
        edge("dieu:688/khoan:1", "chuyen_tiep", "COHORT:xác lập trước 2017-01-01", "Giao dịch dân sự chưa được thực hiện mà có nội dung, hình thức khác với quy định của Bộ luật này"),
    ],
))

DOCS.append(doc(
    doc_key="01/2019/NQ-HĐTP", slug="nq-01-2019-nq-hdtp",
    title="Nghị quyết hướng dẫn áp dụng một số quy định của pháp luật về lãi, lãi suất, phạt vi phạm",
    doc_type="nghi_quyet_hdtp", channel="luatvietnam",
    issued_date="2019-01-11", issued_date_quote="Hà Nội, ngày 11 tháng 01 năm 2019",
    effective_date="2019-03-15", effective_date_quote="có hiệu lực thi hành kể từ ngày 15 tháng 3 năm 2019",
    expected_ops=[],
    expected_norm_events=[{
        "norm": "tran-lai-suat-hdtd", "event": "conflict_resolution",
        "by": "01/2019/NQ-HĐTP dieu:7", "at": "2019-03-15",
        "notes": "statement giải certificate Đ468 BLDS vs cơ chế lãi suất TCTD: HĐ tín dụng KHÔNG áp trần BLDS (đóng pending_event, resolved_by_op — 02 §6.2)",
    }],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Luật Tổ chức TAND 2014", "Căn cứ Luật Tổ chức Tòa án nhân dân ngày 24 tháng 11 năm 2014"),
        edge("dieu:7/khoan:1", "chu_de", "NORM:luat-cac-tctd", "phải phù hợp với quy định của Luật Các tổ chức tín dụng"),
        edge("dieu:7/khoan:2", "pinpoint", "91/2015/QH13 (giới hạn lãi suất)", "không áp dụng quy định về giới hạn lãi suất của Bộ luật Dân sự năm 2005, Bộ luật Dân sự năm 2015"),
        edge("dieu:13/khoan:1", "pinpoint", "91/2015/QH13 dieu:357,468", "mức lãi suất quy định tại Điều 357, Điều 468 của Bộ luật Dân sự năm 2015"),
        edge("dieu:5", "pinpoint", "91/2015/QH13 dieu:468", "Bộ luật Dân sự năm 2015"),
    ],
))

DOCS.append(doc(
    doc_key="47/2010/QH12", slug="luat-47-2010-qh12-trich",
    title="Luật Các tổ chức tín dụng (TRÍCH: Đ1–4, Đ90–96, Đ126–128, Đ161–163)",
    doc_type="luat", channel="luatvietnam", excerpt=True,
    excerpt_spec="Đ1–Đ4 (phạm vi, giải thích từ ngữ); Đ90–96 (lãi suất, cấp tín dụng); Đ126–128; Đ161–163 (chuyển tiếp, hiệu lực)",
    issued_date="2010-06-16", issued_date_quote="thông qua ngày 16 tháng 6 năm 2010",
    effective_date="2011-01-01", effective_date_quote="Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2011.",
    transcription_notes=["văn bản đã HẾT HIỆU LỰC từ 2024-07-01 (bị 32/2024/QH15 thay thế, trừ các khoản chuyển tiếp Đ210) — giữ trong corpus cho point-in-time"],
    expected_ops=[
        op(1, "repeal", "dieu:162/khoan:2", "02/1997/QH10", "Luật các tổ chức tín dụng số 02/1997/QH10", "2011-01-01", notes="out-of-corpus"),
        op(2, "repeal", "dieu:162/khoan:2", "20/2004/QH11", "Luật sửa đổi, bổ sung một số điều của Luật các tổ chức tín dụng số 20/2004/QH11", "2011-01-01", notes="out-of-corpus"),
        op(3, "norm_decl", "dieu:162/khoan:2", "47/2010/QH12", "hết hiệu lực kể từ ngày Luật này có hiệu lực", "2011-01-01"),
    ],
    expected_norm_events=[{"norm": "luat-cac-tctd", "event": "succession",
                           "from": "02/1997/QH10", "to": "47/2010/QH12", "at": "2011-01-01"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Hiến pháp 1992 (sđ 2001)", "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam năm 1992"),
        edge("dieu:3/khoan:2", "chu_de", "PRECEDENCE-STATEMENT (D-15)", "Trường hợp có quy định khác nhau giữa Luật này và các luật khác có liên quan"),
        edge("dieu:91/khoan:1", "chu_de", "NORM:lai-suat-thoa-thuan", "được quyền ấn định và phải niêm yết công khai mức lãi suất huy động vốn, mức phí cung ứng dịch vụ"),
        edge("dieu:126/khoan:1", "dinh_nghia", "SELF dieu:4", "Tổ chức tín dụng, chi nhánh ngân hàng nước ngoài"),
        edge("dieu:94/khoan:1", "chu_de", "NORM:xet-duyet-cap-tin-dung", "Tổ chức tín dụng phải yêu cầu khách hàng cung cấp tài liệu chứng minh"),
    ],
))

DOCS.append(doc(
    doc_key="32/2024/QH15", slug="luat-32-2024-qh15-trich",
    title="Luật Các tổ chức tín dụng (TRÍCH: Đ1–4, Đ100–103, Đ134–136, Đ209–210)",
    doc_type="luat", channel="luatvietnam", excerpt=True,
    excerpt_spec="Đ1–Đ4; Đ100–103 (lãi suất, xét duyệt cấp tín dụng); Đ134–136; Đ209–210 (hiệu lực + chuyển tiếp)",
    issued_date="2024-01-18", issued_date_quote="thông qua ngày 18 tháng 01 năm 2024",
    effective_date="2024-07-01", effective_date_quote="Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2024, trừ quy định tại khoản 2 Điều này.",
    transcription_notes=["hiệu lực PHÂN KỲ thật: khoản 3 Điều 200 và khoản 15 Điều 210 hiệu lực 2025-01-01 (Đ209 k2 — hai node đó ngoài trích đoạn)"],
    expected_ops=[
        op(1, "repeal", "dieu:209/khoan:3", "47/2010/QH12", "Luật Các tổ chức tín dụng số 47/2010/QH12 đã được sửa đổi, bổ sung một số điều theo Luật số 17/2017/QH14 hết hiệu lực", "2024-07-01",
           notes="có ngoại lệ: trừ quy định tại các khoản 1, 2, 3, 4, 8, 9, 12 và 14 Điều 210"),
        op(2, "norm_decl", "dieu:209/khoan:3", "32/2024/QH15", "hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành", "2024-07-01"),
    ],
    expected_transitions=[{
        "source_path": "dieu:210/khoan:2",
        "surface": "Hợp đồng, giao dịch khác, thỏa thuận được ký kết trước ngày Luật này có hiệu lực thi hành",
        "scope_predicate": {"contract_signed_before": "2024-07-01"},
    }],
    expected_norm_events=[{"norm": "luat-cac-tctd", "event": "succession",
                           "from": "47/2010/QH12", "to": "32/2024/QH15", "at": "2024-07-01"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "Hiến pháp 2013", "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam"),
        edge("dieu:100/khoan:2", "chu_de", "NORM:lai-suat-thoa-thuan", "có quyền thỏa thuận về lãi suất, phí cấp tín dụng"),
        edge("dieu:134", "ngoai_le", "SELF dieu:135", "Hạn chế cấp tín dụng"),
        edge("dieu:209/khoan:2", "pinpoint", "SELF dieu:200/khoan:3 + dieu:210/khoan:15", "Khoản 3 Điều 200 và khoản 15 Điều 210 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025"),
        edge("dieu:210/khoan:2", "chuyen_tiep", "COHORT:contract_signed_before=2024-07-01", "được tiếp tục thực hiện theo hợp đồng, giao dịch khác, thỏa thuận đã ký kết"),
    ],
))

DOCS.append(doc(
    doc_key="41/2016/TT-NHNN", slug="tt-41-2016-tt-nhnn-trich",
    title="Thông tư quy định tỷ lệ an toàn vốn đối với ngân hàng, chi nhánh ngân hàng nước ngoài (TRÍCH + Phụ lục 3 nguyên vẹn)",
    doc_type="thong_tu", channel="luatvietnam", excerpt=True,
    excerpt_spec="Đ1, Đ2, Đ6–7, Đ16, Đ23–24; PHỤ LỤC 3 nguyên vẹn (Chỉ số kinh doanh)",
    issued_date="2016-12-30", issued_date_quote="ngày 30 tháng 12 năm 2016",
    effective_date="2020-01-01", effective_date_quote="Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2020, trừ trường hợp quy định tại khoản 2 Điều này.",
    transcription_notes=[
        "Đ16 k1: dòng '1.' của công thức KOR mất trong transcription (bảng công thức vỡ dòng) — file đếm được 2 khoản tại Đ16, bản gốc có 3",
        "Đ23 hiển thị theo bản gốc 2016 (opt-in sớm); Đ23 bị k2 Đ24 TT22/2019 thay thế từ 2020-01-01 rồi bị k2 Đ1 TT26/2022 thay tiếp từ 2022-12-31 — chuỗi op nằm ở các doc kia",
    ],
    expected_ops=[],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "46/2010/QH12", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam số 46/2010/QH12"),
        edge("preamble", "tham_quyen", "47/2010/QH12", "Căn cứ Luật các tổ chức tín dụng số 47/2010/QH12"),
        edge("dieu:16", "pinpoint", "SELF phuluc:3", "Chỉ số kinh doanh được xác định theo hướng dẫn tại Phụ lục 3 ban hành kèm theo Thông tư này"),
        edge("dieu:2", "frontier", "Moody's/S&P/Fitch (ngoài kho)", "Tổ chức xếp hạng tín nhiệm Moody’s, Standard & Poor, Fitch Rating"),
        edge("dieu:6", "dinh_nghia", "SELF dieu:2", "Tỷ lệ an toàn vốn (CAR) tính theo đơn vị phần trăm (%)"),
    ],
))

DOCS.append(doc(
    doc_key="22/2019/TT-NHNN", slug="tt-22-2019-tt-nhnn-trich",
    title="Thông tư quy định các giới hạn, tỷ lệ bảo đảm an toàn trong hoạt động của ngân hàng, chi nhánh ngân hàng nước ngoài (TRÍCH)",
    doc_type="thong_tu", channel="luatvietnam", excerpt=True,
    excerpt_spec="Đ1–3, Đ6–8, Đ20 (LDR), Đ21–25 (chuyển tiếp + hiệu lực, gồm khoản sửa đổi TT41)",
    issued_date="2019-11-15", issued_date_quote="ngày 15 tháng 11 năm 2019",
    effective_date="2020-01-01", effective_date_quote="Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2020.",
    transcription_notes=[
        "Đ20 k1: dòng '1.' của công thức LDR mất trong transcription — file đếm được 5 khoản tại Đ20, bản gốc có 6",
        "đã vá 1 dấu đóng ngoặc kép ” thiếu ở cuối quote k2 Đ24 (D-43, suffix unique '…giai đoạn 2016- 2020”.')",
        "header căn cứ vỡ dòng 2 cột ('…ngày 16 tháng 6 năm' / '2010;') giữ nguyên — parser R-3 gộp",
    ],
    expected_ops=[
        op(1, "amend", "dieu:24/khoan:2", "41/2016/TT-NHNN", "Sửa đổi, bổ sung Điều 23 Thông tư 41/2016/TT-NHNN", "2020-01-01", target_path="dieu:23",
           notes="op nấp trong Điều Hiệu lực thi hành; CHÍNH op này bị k2 Đ1 TT26/2022 thay thế từ 2022-12-31 (amend-nhắm-op thật)"),
        op(2, "repeal", "dieu:24/khoan:3", "36/2014/TT-NHNN", "Thông tư số 36/2014/TT-NHNN", "2020-01-01", notes="out-of-corpus; danh sách gạch đầu dòng"),
        op(3, "repeal", "dieu:24/khoan:3", "06/2016/TT-NHNN", "Thông tư số 06/2016/TT-NHNN", "2020-01-01", notes="out-of-corpus"),
        op(4, "repeal", "dieu:24/khoan:3", "19/2017/TT-NHNN", "Thông tư số 19/2017/TT-NHNN", "2020-01-01", notes="out-of-corpus"),
        op(5, "repeal", "dieu:24/khoan:3", "16/2018/TT-NHNN", "Thông tư số 16/2018/TT-NHNN", "2020-01-01", notes="out-of-corpus"),
        op(6, "repeal", "dieu:24/khoan:3", "13/2019/TT-NHNN", "Điều 4 Thông tư số 13/2019/TT-NHNN", "2020-01-01", target_path="dieu:4", notes="out-of-corpus; repeal MỘT điều của văn bản khác"),
    ],
    expected_transitions=[{
        "source_path": "dieu:21/khoan:1",
        "surface": "Các hợp đồng được ký kết trước ngày Thông tư này có hiệu lực thi hành",
        "scope_predicate": {"contract_signed_before": "2020-01-01"},
    }],
    expected_norm_events=[{"norm": "gioi-han-ty-le-bao-dam-an-toan", "event": "succession",
                           "from": "36/2014/TT-NHNN", "to": "22/2019/TT-NHNN", "at": "2020-01-01"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "46/2010/QH12", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam số 46/2010/QH12"),
        edge("preamble", "tham_quyen", "17/2017/QH14", "Căn cứ Luật sửa đổi, bổ sung một số điều của Luật các tổ chức tín dụng"),
        edge("dieu:20/khoan:4/diem:a", "ngoai_le", "SELF dieu:20/khoan:4/diem:a/tiet:i-ii", "trừ các khoản sau đây"),
        edge("dieu:21/khoan:1", "chuyen_tiep", "COHORT:contract_signed_before=2020-01-01", "được tiếp tục thực hiện theo các thỏa thuận đã ký kết cho đến hết thời hạn của hợp đồng"),
        edge("dieu:7/khoan:1/diem:b", "pinpoint", "SELF dieu:4/khoan:6", "theo quy định tại điểm a, b khoản 6 Điều 4 Thông tư này"),
        edge("dieu:23/khoan:3", "frontier", "1058/QĐ-TTg (ngoài kho)", "Quyết định số 1058/QĐ-TTg"),
    ],
    amending_nodes=["dieu:24/khoan:2"],
))

DOCS.append(doc(
    doc_key="26/2022/TT-NHNN", slug="tt-26-2022-tt-nhnn",
    title="Thông tư sửa đổi, bổ sung một số điều của Thông tư số 22/2019/TT-NHNN",
    doc_type="thong_tu", channel="luatvietnam",
    issued_date="2022-12-31", issued_date_quote="Hà Nội, ngày 31 tháng 12 năm 2022",
    effective_date="2022-12-31", effective_date_quote="Thông tư này có hiệu lực từ ngày 31 tháng 12 năm 2022./.",
    transcription_notes=[
        "hiệu lực NGAY ngày ban hành (trường hợp thật của same-day effectivity)",
        "quote k2 Đ1 dùng '' (nháy kép đơn) thay “” — biến thể transcription, counter xử lý line-start/line-end",
    ],
    expected_ops=[
        op(1, "amend", "dieu:1/khoan:1", "22/2019/TT-NHNN", "Sửa đổi, bổ sung điểm a khoản 4 Điều 20", "2022-12-31", target_path="dieu:20/khoan:4/diem:a",
           notes="lộ trình tiền gửi KBNN theo NĂM ghi TRONG new_text (50%→60%→80%→100%); op này là ĐÍCH của repeal-op TT08/2026 fixture (OPO-01, PIT-01/02)"),
        op(2, "amend", "dieu:1/khoan:2", "22/2019/TT-NHNN", "Sửa đổi, bổ sung khoản 2 Điều 24", "2022-12-31", target_path="dieu:24/khoan:2",
           target_is_op=True, target_op={"doc": "22/2019/TT-NHNN", "paths": ["dieu:24/khoan:2"]},
           notes="AMEND-NHẮM-OP THẬT: đích là khoản sửa đổi (op amend Đ23 TT41 của TT22); new_text lồng quote sửa tiếp Đ23 TT41 (route QĐ 689/QĐ-TTg)"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "46/2010/QH12", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam ngày 16 tháng 6 năm 2010"),
        edge("preamble", "tham_quyen", "16/2017/NĐ-CP", "Căn cứ Nghị định số 16/2017/NĐ-CP"),
        edge("dieu:1/khoan:1", "pinpoint", "22/2019/TT-NHNN dieu:20/khoan:4/diem:a", "điểm a khoản 4 Điều 20"),
        edge("dieu:1/khoan:2", "pinpoint", "22/2019/TT-NHNN dieu:24/khoan:2", "khoản 2 Điều 24"),
        edge("dieu:2", "pinpoint", "SELF (thi hành)", "Chánh Thanh tra, giám sát ngân hàng"),
    ],
    amending_nodes=["dieu:1/khoan:1", "dieu:1/khoan:2"],
))

DOCS.append(doc(
    doc_key="52/2025/TT-NHNN", slug="tt-52-2025-tt-nhnn",
    title="Thông tư sửa đổi, bổ sung một số điều của Thông tư số 39/2016/TT-NHNN",
    doc_type="thong_tu", channel="luatvietnam",
    issued_date="2025-12-25", issued_date_quote="Hà Nội, ngày 25 tháng 12 năm 2025",
    effective_date="2025-12-25", effective_date_quote="Thông tư này có hiệu lực thi hành từ ngày 25 tháng 12 năm 2025./.",
    transcription_notes=["văn bản PHÁT HIỆN THÊM khi kiểm tra VBHN 06/VBHN-NHNN 2026 (hợp nhất đến TT52) — bổ sung vào corpus để oracle diff không lệch"],
    expected_ops=[
        op(1, "amend", "dieu:1", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 3 Điều 22", "2025-12-25", target_path="dieu:22/khoan:3",
           notes="op trọn trong heading; new_text chứa '10 (mười) ngày làm việc' — bị QĐ 4033/QĐ-NHNN đính chính thành 'ngày'"),
        op(2, "amend", "dieu:2", "39/2016/TT-NHNN", "Sửa đổi, bổ sung khoản 2 Điều 35", "2025-12-25", target_path="dieu:35/khoan:2"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "46/2010/QH12", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam số 46/2010/QH12"),
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("preamble", "tham_quyen", "26/2025/NĐ-CP", "Căn cứ Nghị định số 26/2025/NĐ-CP"),
        edge("dieu:1", "pinpoint", "39/2016/TT-NHNN dieu:22/khoan:3", "khoản 3 Điều 22"),
        edge("dieu:2", "pinpoint", "39/2016/TT-NHNN dieu:35/khoan:2", "khoản 2 Điều 35"),
    ],
    amending_nodes=["dieu:1", "dieu:2"],
))

DOCS.append(doc(
    doc_key="4033/QĐ-NHNN", slug="qd-4033-2025-dinh-chinh",
    title="Quyết định đính chính Thông tư số 52/2025/TT-NHNN",
    doc_type="quyet_dinh", channel="luatvietnam",
    issued_date="2025-12-25", issued_date_quote="Hà Nội, ngày 25 tháng 12 năm 2025",
    effective_date="2025-12-25", effective_date_quote="Quyết định này có hiệu lực kể từ ngày ký.",
    transcription_notes=["OP DINH_CHINH THẬT (không phải fixture); typo transcription giữ nguyên: 'văn ban quy phạm', 'Thông tư sô 39'"],
    expected_ops=[
        op(1, "dinh_chinh", "dieu:1", "52/2025/TT-NHNN", "Đính chính cụm từ “ngày làm việc” thành “ngày”.", "2025-12-25",
           target_path="dieu:1", retroactive_to_window_start=True,
           notes="hồi tố về ĐẦU cửa sổ version bị đính chính (D-12): text k3 Đ22 TT39 bản-TT52 đọc là '10 (mười) ngày' từ 2025-12-25; VBHN 06/VBHN-NHNN xác nhận"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "64/2025/QH15", "Căn cứ Luật Ban hành văn ban quy phạm pháp luật số 64/2025/QH15"),
        edge("preamble", "tham_quyen", "87/2025/QH15", "Luật số 87/2025/QH15"),
        edge("preamble", "tham_quyen", "78/2025/NĐ-CP", "Căn cứ Nghị định số 78/2025/NĐ-CP"),
        edge("preamble", "tham_quyen", "26/2025/NĐ-CP", "Căn cứ Nghị định số 26/2025/NĐ-CP"),
        edge("dieu:1", "pinpoint", "52/2025/TT-NHNN dieu:1", "Điều 1 Thông tư số 52/2025/TT-NHNN"),
    ],
))

DOCS.append(doc(
    doc_key="21/VBHN-NHNN", slug="vbhn-21-2024-tt39", is_oracle=True,
    title="Văn bản hợp nhất TT39 (hợp nhất đến TT12/2024) — DIFFERENTIAL ORACLE",
    doc_type="vbhn", channel="luatvietnam",
    issued_date="2024-07-16", issued_date_quote="Hà Nội, ngày 16 tháng 7 năm 2024",
    effective_date=None, effective_date_quote=None,
    transcription_notes=[
        "VBHN không có giá trị pháp lý (D-22) — is_oracle, không vào retrieval; hợp nhất TT39 + TT06 + TT10 + TT12",
        "footnote dính vào số khoản ('12.6 Cho vay' / '1.21Căn cứ') đã tách space; nội dung footnote giữ nguyên",
    ],
    expected_ops=[], expected_edges_sample=[],
))

DOCS.append(doc(
    doc_key="06/VBHN-NHNN", slug="vbhn-06-2026-tt39", is_oracle=True,
    title="Văn bản hợp nhất TT39 (hợp nhất đến TT52/2025) — DIFFERENTIAL ORACLE",
    doc_type="vbhn", channel="luatvietnam",
    issued_date="2026-01-07", issued_date_quote="Hà Nội, ngày 07 tháng 01 năm 2026",
    effective_date=None, effective_date_quote=None,
    transcription_notes=[
        "hợp nhất TT39 + TT06 + TT10 + TT12 + TT52 (danh sách 4 văn bản sửa đổi ở đầu); k3 Đ22 đã phản ánh cả QĐ 4033 đính chính ('10 (mười) ngày' — không còn 'ngày làm việc')",
        "footnote '5 [42] .' (số khoản tách khỏi dấu chấm) đã chuẩn hóa thành '5. [42]'",
        "provenance ngoặc/footnote ([14][15][16] ngưng hiệu lực k8–10) dùng cho cross-validation 02 §5.5",
    ],
    expected_ops=[], expected_edges_sample=[],
))

# ============================== FIXTURE SYNTHETIC ==============================

DOCS.append(doc(
    doc_key="08/2026/TT-NHNN", slug="tt-08-2026-tt-nhnn", synthetic=True,
    title="[FIXTURE] Thông tư sửa đổi TT22/2019 + bãi bỏ khoản sửa đổi của TT26/2022 (op-nhắm-op)",
    doc_type="thong_tu", channel="fixture",
    issued_date="2026-01-01", issued_date_quote="Hà Nội, ngày 01 tháng 01 năm 2026",
    effective_date="2026-01-01", effective_date_quote="Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2026.",
    expected_ops=[
        op(1, "amend", "dieu:1", "22/2019/TT-NHNN", "Sửa đổi, bổ sung điểm b khoản 4 Điều 20", "2026-01-01", target_path="dieu:20/khoan:4/diem:b"),
        op(2, "repeal", "dieu:2", "26/2022/TT-NHNN", "Bãi bỏ khoản 1 Điều 1 Thông tư số 26/2022/TT-NHNN", "2026-01-01",
           target_is_op=True, target_op={"doc": "26/2022/TT-NHNN", "paths": ["dieu:1/khoan:1"]},
           notes="OP-NHẮM-OP: đóng hiệu lực op TT26-k1Đ1 (amend điểm a k4 Đ20 TT22) TỪ 2026-01-01; cửa sổ 2022-12-31→2026-01-01 BẤT KHẢ XÂM PHẠM (D-10); từ 2026-01-01 điểm a k4 Đ20 TT22 trở về text gốc 2019 (loại toàn bộ tiền gửi KBNN)"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "46/2010/QH12", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam số 46/2010/QH12"),
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("preamble", "tham_quyen", "26/2025/NĐ-CP", "Căn cứ Nghị định số 26/2025/NĐ-CP"),
        edge("dieu:1", "pinpoint", "22/2019/TT-NHNN dieu:20/khoan:4/diem:b", "điểm b khoản 4 Điều 20"),
        edge("dieu:2", "pinpoint", "26/2022/TT-NHNN dieu:1/khoan:1", "khoản 1 Điều 1 Thông tư số 26/2022/TT-NHNN"),
    ],
    amending_nodes=["dieu:1"],
))

DOCS.append(doc(
    doc_key="28/2026/TT-NHNN", slug="tt-28-2026-tt-nhnn", synthetic=True,
    title="[FIXTURE] Thông tư sửa đổi TT22/2019: chèn Điều 7a (alias drift) + thay-cụm-từ đa điều + bẫy binding 'Thông tư này'",
    doc_type="thong_tu", channel="fixture",
    issued_date="2026-01-05", issued_date_quote="Hà Nội, ngày 05 tháng 01 năm 2026",
    effective_date="2026-01-25", effective_date_quote="Thông tư này có hiệu lực thi hành kể từ ngày 25 tháng 01 năm 2026.",
    expected_ops=[
        op(1, "insert", "dieu:1/khoan:1", "22/2019/TT-NHNN", "Bổ sung Điều 7a vào sau Điều 7", "2026-01-25", target_path="dieu:7a",
           notes="alias drift (INV-11); trong QUOTE có 'Điều 6 Thông tư này' và 'Điều 7 Thông tư này' → bind vào TT22 (ĐÍCH), không phải TT28 (02 §5.3); chứa số '10 (mười) ngày làm việc' — sẽ bị DC-01/2026 đính chính thành '05 (năm)'"),
        op(2, "amend", "dieu:1/khoan:2", "22/2019/TT-NHNN", "khoản 3 Điều 7", "2026-01-25", target_path="dieu:7/khoan:3",
           via="phrase_replace (D-21) — curator materialize", phrase={"from": "Ngân hàng Nhà nước chi nhánh tỉnh, thành phố trực thuộc Trung ương", "to": "Ngân hàng Nhà nước chi nhánh Khu vực"}),
        op(3, "amend", "dieu:1/khoan:2", "22/2019/TT-NHNN", "khoản 2 Điều 23", "2026-01-25", target_path="dieu:23/khoan:2",
           via="phrase_replace (D-21) — curator materialize", phrase={"from": "Ngân hàng Nhà nước chi nhánh tỉnh, thành phố trực thuộc Trung ương", "to": "Ngân hàng Nhà nước chi nhánh Khu vực"},
           notes="cụm từ cũng xuất hiện ở Đ24-k2-quote và Đ25 TT22 nhưng op CHỈ liệt kê k3Đ7 + k2Đ23 — extractor không được tự mở rộng"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "46/2010/QH12", "Căn cứ Luật Ngân hàng Nhà nước Việt Nam số 46/2010/QH12"),
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("preamble", "tham_quyen", "26/2025/NĐ-CP", "Căn cứ Nghị định số 26/2025/NĐ-CP"),
        edge("dieu:1/khoan:1", "pinpoint", "22/2019/TT-NHNN dieu:7", "Bổ sung Điều 7a vào sau Điều 7"),
        edge("dieu:1/khoan:2", "pinpoint", "22/2019/TT-NHNN dieu:23/khoan:2", "khoản 2 Điều 23"),
    ],
    amending_nodes=["dieu:1/khoan:1", "dieu:1/khoan:2"],
))

DOCS.append(doc(
    doc_key="32/2026/TT-NHNN", slug="tt-32-2026-tt-nhnn", synthetic=True,
    title="[FIXTURE] Thông tư quy định về hoạt động đại lý thanh toán (norm succession + grandfathering 2 tầng + blanket derogation)",
    doc_type="thong_tu", channel="fixture",
    issued_date="2026-03-20", issued_date_quote="Hà Nội, ngày 20 tháng 3 năm 2026",
    effective_date="2026-07-01", effective_date_quote="Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.",
    transcription_notes=["header 'Số: 32 /2026/TT- NHNN' CỐ TÌNH chứa khoảng trắng lỗi (trap 02 §7.2) — vá trước khi tokenize"],
    expected_ops=[
        op(1, "repeal", "dieu:6/khoan:2", "15/2020/TT-NHNN", "Thông tư này thay thế Thông tư số 15/2020/TT-NHNN", "2026-07-01",
           notes="văn bản bị thay thế là fiction ngoài kho (giống QĐ1627 với TT39)"),
        op(2, "norm_decl", "dieu:6/khoan:2", "32/2026/TT-NHNN", "thay thế Thông tư số 15/2020/TT-NHNN ngày 22 tháng 10 năm 2020", "2026-07-01",
           notes="norm succession; Đ6 k3 tương chiếu dẫn chiếu cũ→mới NON-BINDING (D-08)"),
        op(3, "blanket_derogation", "dieu:6/khoan:4", None, "Các quy định trước đây trái với Thông tư này hết hiệu lực thi hành.", "2026-07-01",
           notes="KHÔNG mutate state; seed conflict screening theo chủ đề (D-14)"),
    ],
    expected_transitions=[{
        "source_path": "dieu:7",
        "surface": "được ký kết trước ngày 01 tháng 7 năm 2026 và không được sửa đổi, bổ sung kể từ ngày 01 tháng 7 năm 2026",
        "scope_predicate": {"contract_signed_before": "2026-07-01", "not_amended_on_or_after": "2026-07-01"},
        "notes": "GF-03: 2 predicate LỒNG đúng DSL D-25; test_scope_split",
    }],
    expected_norm_events=[{"norm": "dai-ly-thanh-toan", "event": "succession",
                           "from": "15/2020/TT-NHNN", "to": "32/2026/TT-NHNN", "at": "2026-07-01"}],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("dieu:3/khoan:2", "pinpoint", "32/2024/QH15 dieu:102", "Điều 102 Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("dieu:3/khoan:2", "chu_de", "NORM:hoat-dong-cho-vay", "quy định của Ngân hàng Nhà nước Việt Nam về hoạt động cho vay của tổ chức tín dụng, chi nhánh ngân hàng nước ngoài đối với khách hàng"),
        edge("dieu:5/khoan:2", "pinpoint", "SELF dieu:4", "phạm vi ủy quyền quy định tại Điều 4 Thông tư này"),
        edge("dieu:6/khoan:3", "chu_de", "CORRELATION non-binding → 15/2020/TT-NHNN", "Các dẫn chiếu đến Thông tư số 15/2020/TT-NHNN"),
        edge("dieu:7/khoan:1", "chuyen_tiep", "COHORT:signed_before=2026-07-01 ∧ not_amended", "hợp đồng đại lý thanh toán được ký kết trước ngày 01 tháng 7 năm 2026"),
    ],
))

DOCS.append(doc(
    doc_key="11/2026/TT-NHNN", slug="tt-11-2026-tt-nhnn", synthetic=True,
    title="[FIXTURE] Thông tư omnibus sửa 5 Thông tư chia theo Chương (context-stack, hiệu lực phân kỳ, op heading, op Phụ lục, mass repeal)",
    doc_type="thong_tu", channel="fixture",
    issued_date="2026-01-12", issued_date_quote="Hà Nội, ngày 12 tháng 01 năm 2026",
    effective_date="2026-03-01", effective_date_quote="Thông tư này có hiệu lực thi hành từ ngày 01 tháng 3 năm 2026, trừ quy định tại khoản 2 Điều này.",
    transcription_notes=["hiệu lực PHÂN KỲ THEO CHỦ ĐỀ: 'Các quy định về Phiếu lý lịch tư pháp tại Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.' (k2 Đ7) — phân loại ngữ nghĩa, không regex nổi (per-op review D-19)"],
    expected_ops=[
        op(1, "insert", "dieu:1/khoan:1", "39/2016/TT-NHNN", "Bổ sung điểm c vào khoản 1 Điều 9", "2026-07-01", target_path="dieu:9/khoan:1/diem:c",
           notes="'Điều 9' TRẦN — resolve bằng context-stack Chương I (02 §5.4); valid_from 2026-07-01 theo k2 Đ7 (Phiếu LLTP) ≠ ngày chung 2026-03-01 (PEN-01)"),
        op(2, "amend", "dieu:1/khoan:2", "39/2016/TT-NHNN", "Sửa đổi tên Điều 14", "2026-03-01", target_path="dieu:14", target_part="heading",
           notes="op CHỈ sửa TIÊU ĐỀ (trap 02 §7.11)"),
        op(3, "amend", "dieu:2/khoan:1", "22/2019/TT-NHNN", "Sửa đổi, bổ sung khoản 5 Điều 20", "2026-03-01", target_path="dieu:20/khoan:5",
           notes="trong QUOTE có 'Điều 9 Thông tư này' = Đ9 TT22 (binding vào ĐÍCH) — node NGOÀI trích đoạn corpus → mandatory edge unresolved (CLO-02)"),
        op(4, "insert", "dieu:3/khoan:1", "41/2016/TT-NHNN", "Bổ sung khoản 3 vào Phụ lục 3", "2026-03-01", target_path="phuluc:3", target_part="appendix",
           notes="op nhắm PHỤ LỤC (trap 02 §7.11)"),
        op(5, "amend", "dieu:4", "26/2022/TT-NHNN", "Sửa đổi, bổ sung Điều 2", "2026-03-01", target_path="dieu:2",
           notes="đích là điều KHÔNG-amending của một thông tư sửa đổi (đối chứng với op-nhắm-op)"),
        op(6, "amend", "dieu:5", "12/2024/TT-NHNN", "Điều 3 Thông tư số 12/2024/TT-NHNN", "2026-03-01", target_path="dieu:3",
           via="phrase_replace (D-21) — curator materialize", phrase={"from": "Giám đốc Ngân hàng Nhà nước chi nhánh các tỉnh, thành phố trực thuộc Trung ương", "to": "Giám đốc Ngân hàng Nhà nước chi nhánh Khu vực"}),
        op(7, "repeal", "dieu:6/khoan:1", "97/2019/TT-NHNN", "Thông tư số 97/2019/TT-NHNN", "2026-03-01", notes="mass repeal; fiction ngoài kho"),
        op(8, "repeal", "dieu:6/khoan:2", "98/2020/TT-NHNN", "Thông tư số 98/2020/TT-NHNN", "2026-03-01", notes="fiction ngoài kho"),
        op(9, "repeal", "dieu:6/khoan:3", "99/2021/TT-NHNN", "Khoản 3 Điều 3 Thông tư số 99/2021/TT-NHNN", "2026-03-01", target_path="dieu:3/khoan:3", notes="repeal MỘT khoản của văn bản ngoài kho"),
    ],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("dieu:1/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:9/khoan:1 (context-stack)", "Bổ sung điểm c vào khoản 1 Điều 9"),
        edge("dieu:2/khoan:1", "pinpoint", "22/2019/TT-NHNN dieu:20/khoan:5", "khoản 5 Điều 20"),
        edge("dieu:3/khoan:1", "pinpoint", "41/2016/TT-NHNN phuluc:3", "Phụ lục 3 ban hành kèm theo Thông tư số 41/2016/TT-NHNN"),
        edge("dieu:7/khoan:2", "pinpoint", "SELF dieu:1/khoan:1 (ngữ nghĩa)", "Các quy định về Phiếu lý lịch tư pháp tại Thông tư này"),
    ],
    amending_nodes=["dieu:1/khoan:1", "dieu:1/khoan:2", "dieu:2/khoan:1", "dieu:3/khoan:1", "dieu:4", "dieu:5"],
))

DOCS.append(doc(
    doc_key="DC-01/2026", slug="dc-01-2026", synthetic=True,
    title="[FIXTURE] Công văn đính chính một con số của TT28/2026 — hồi tố về đầu cửa sổ",
    doc_type="cong_van", channel="fixture",
    issued_date="2026-02-10", issued_date_quote="Hà Nội, ngày 10 tháng 02 năm 2026",
    effective_date="2026-02-10", effective_date_quote="Hà Nội, ngày 10 tháng 02 năm 2026",
    transcription_notes=["công văn — KHÔNG có Điều (counts 0/0/0/0/0); effective = ngày ký, nhưng op hồi tố"],
    expected_ops=[
        op(1, "dinh_chinh", "body", "22/2019/TT-NHNN", "đã in là: “trong thời hạn 10 (mười) ngày làm việc đầu tiên của quý tiếp theo”", "2026-01-25",
           target_path="dieu:7a/khoan:1", retroactive_to_window_start=True,
           notes="DCH-01: sửa '10 (mười)' → '05 (năm)' HỒI TỐ về đầu cửa sổ Đ7a (2026-01-25 = ngày TT28 hiệu lực), KHÔNG phải từ 2026-02-10; as_of 2026-02-01 với K≥ingest phải trả 05"),
    ],
    expected_edges_sample=[
        edge("body", "pinpoint", "28/2026/TT-NHNN dieu:1/khoan:1", "khoản 1 Điều 1 Thông tư số 28/2026/TT-NHNN"),
        edge("body", "pinpoint", "22/2019/TT-NHNN dieu:7a/khoan:1", "khoản 1 Điều 7a Thông tư số 22/2019/TT-NHNN"),
        edge("body", "pinpoint", "22/2019/TT-NHNN", "Thông tư số 22/2019/TT-NHNN ngày 15 tháng 11 năm 2019"),
        edge("body", "pinpoint", "28/2026/TT-NHNN", "Thông tư số 28/2026/TT-NHNN ngày 05 tháng 01 năm 2026"),
        edge("body", "chu_de", "NORM:gioi-han-ty-le-bao-dam-an-toan", "quy định các giới hạn, tỷ lệ bảo đảm an toàn trong hoạt động của ngân hàng, chi nhánh ngân hàng nước ngoài"),
    ],
))

DOCS.append(doc(
    doc_key="QT-TD-01/SHB", slug="shb-qt-td-01", synthetic=True,
    title="[FIXTURE nội bộ] Quy trình cho vay khách hàng cá nhân — có MỘT mục cố tình stale (SEM-01)",
    doc_type="quy_trinh_noi_bo", channel="internal_registry", audience="internal",
    owner="Khối Khách hàng cá nhân — Phòng Chính sách tín dụng",
    issued_date="2023-03-20", issued_date_quote="Hà Nội, ngày 20 tháng 3 năm 2023",
    effective_date="2023-04-01", effective_date_quote="Quy trình này có hiệu lực kể từ ngày 01 tháng 4 năm 2023.",
    transcription_notes=[
        "STALE CỐ TÌNH tại khoản 2 Điều 3 ('Mục 3.2' theo cách gọi 04 §1.2): liệt kê '05 (năm) điều kiện vay vốn' và dẫn 'khoản 5 Điều 7 Thông tư số 39/2016/TT-NHNN' — khoản 5 Đ7 bị TT06 Đ2 BÃI BỎ từ 2023-09-01 và k3 Đ7 được TT12 nới cho khoản giá trị nhỏ; sau 2023-09-01 mục này lệch chuẩn (SEM-01, blast-radius → notice owner)",
        "ban hành TRƯỚC TT06 → stale tự nhiên theo dòng thời gian, không lộ liễu",
    ],
    expected_ops=[],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "39/2016/TT-NHNN", "Căn cứ Thông tư số 39/2016/TT-NHNN"),
        edge("preamble", "chu_de", "NORM:hoat-dong-cho-vay", "Căn cứ các quy định của Ngân hàng Nhà nước Việt Nam về hoạt động cho vay của tổ chức tín dụng, chi nhánh ngân hàng nước ngoài đối với khách hàng"),
        edge("dieu:2/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:9", "Điều 9 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:3/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:7", "Điều 7 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:3/khoan:2/diem:đ", "pinpoint", "39/2016/TT-NHNN dieu:7/khoan:5 (STALE — node đã bị bãi bỏ)", "khoản 5 Điều 7 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:4/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:13", "Điều 13 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:4/khoan:2", "pinpoint", "CS-LS-01/SHB", "Chính sách lãi suất cho vay số CS-LS-01/SHB"),
        edge("dieu:5/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:23/khoan:1 + MB-HD-01/SHB", "khoản 1 Điều 23 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:5/khoan:2", "chu_de", "NORM:giai-ngan-von-cho-vay (TT21/2017 ngoài kho)", "quy định của Ngân hàng Nhà nước Việt Nam về phương thức giải ngân vốn cho vay"),
    ],
))

DOCS.append(doc(
    doc_key="MB-HD-01/SHB", slug="shb-mb-hd-01", synthetic=True,
    title="[FIXTURE nội bộ] Mẫu hợp đồng cho vay phục vụ nhu cầu đời sống (biểu mẫu — staleness propagation)",
    doc_type="bieu_mau", channel="internal_registry", audience="internal",
    owner="Khối Khách hàng cá nhân — Phòng Phát triển sản phẩm",
    issued_date="2024-07-05", issued_date_quote="Hà Nội, ngày 05 tháng 7 năm 2024",
    effective_date="2024-07-05", effective_date_quote="áp dụng thống nhất trong toàn hệ thống kể từ ngày 05 tháng 7 năm 2024",
    expected_ops=[],
    expected_transitions=[{
        "source_path": "dieu:4/khoan:2",
        "surface": "các hợp đồng cho vay đã ký kết trước ngày Mẫu hợp đồng này được áp dụng",
        "scope_predicate": {"contract_signed_before": "2024-07-05"},
        "notes": "kèm mốc TT06: 'nội dung sửa đổi, bổ sung hợp đồng kể từ ngày Thông tư số 06/2023/TT-NHNN có hiệu lực thi hành phải phù hợp với quy định hiện hành'",
    }],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "91/2015/QH13", "Căn cứ Bộ luật Dân sự số 91/2015/QH13"),
        edge("preamble", "tham_quyen", "32/2024/QH15", "Căn cứ Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("dieu:2/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:13 + 32/2024/QH15 dieu:100", "Điều 13 Thông tư số 39/2016/TT-NHNN và Điều 100 Luật Các tổ chức tín dụng số 32/2024/QH15"),
        edge("dieu:2/khoan:2", "chu_de", "NORM:phuong-phap-tinh-lai (TT14/2017 ngoài kho)", "quy định của Ngân hàng Nhà nước Việt Nam về phương pháp tính lãi"),
        edge("dieu:4/khoan:2", "chuyen_tiep", "COHORT:contract_signed_before=2024-07-05 + mốc TT06", "kể từ ngày Thông tư số 06/2023/TT-NHNN có hiệu lực thi hành"),
    ],
))

DOCS.append(doc(
    doc_key="CS-LS-01/SHB", slug="shb-cs-ls-01", synthetic=True,
    title="[FIXTURE nội bộ] Chính sách lãi suất cho vay — 1 khoản siết nghĩa vụ CỦA SHB (CFL-04) + 1 khoản siết yêu cầu VỚI khách (CFL-03)",
    doc_type="chinh_sach_noi_bo", channel="internal_registry", audience="internal",
    owner="Khối Nguồn vốn",
    issued_date="2024-10-01", issued_date_quote="Hà Nội, ngày 01 tháng 10 năm 2024",
    effective_date="2024-10-15", effective_date_quote="Chính sách này có hiệu lực kể từ ngày 15 tháng 10 năm 2024.",
    transcription_notes=[
        "CFL-04 (Liskov-exempt, chat_hon_ve_minh — TỰ LOẠI): khoản 2 Điều 3 — SHB tự buộc cung cấp bảng tính lãi TRƯỚC ≥03 ngày làm việc (siết nghĩa vụ CỦA SHB so với Đ16 TT39) → KHÔNG được thành conflict",
        "CFL-03 (chat_hon_ve_doi_tac — CANDIDATE): khoản 1 Điều 4 — buộc MỌI khách hàng (kể cả khoản giá trị nhỏ) nộp phương án sử dụng vốn khả thi, TRÁI với miễn trừ tại k3 Đ7 TT39 (bản-sau-TT12: 'Điều kiện này không bắt buộc đối với khoản cho vay có mức giá trị nhỏ') → vào queue, fork internal_external",
    ],
    expected_ops=[],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "39/2016/TT-NHNN", "Căn cứ Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:2/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:13", "Điều 13 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:2/khoan:2", "pinpoint", "39/2016/TT-NHNN dieu:13/khoan:2", "khoản 2 Điều 13 Thông tư số 39/2016/TT-NHNN"),
        edge("dieu:2/khoan:2", "chu_de", "NORM:tran-lai-suat-nganh-uu-tien", "mức lãi suất cho vay tối đa do Thống đốc Ngân hàng Nhà nước Việt Nam quyết định trong từng thời kỳ"),
        edge("dieu:4/khoan:1", "pinpoint", "39/2016/TT-NHNN dieu:7/khoan:3 (CFL-03)", "khoản cho vay có mức giá trị nhỏ"),
    ],
))

DOCS.append(doc(
    doc_key="GT-468-01/SHB", slug="shb-gt-468-01", synthetic=True,
    title="[FIXTURE nội bộ] Diễn giải nội bộ về áp dụng trần lãi suất Đ468 BLDS — statement hạng thấp nhất",
    doc_type="dien_giai_noi_bo", channel="internal_registry", audience="internal",
    owner="Khối Pháp chế và Tuân thủ",
    issued_date="2019-06-10", issued_date_quote="Hà Nội, ngày 10 tháng 6 năm 2019",
    effective_date="2019-06-10", effective_date_quote="Hà Nội, ngày 10 tháng 6 năm 2019",
    transcription_notes=["statement diễn giải (02 §6.3): được cite, hạng thấp nhất, KHÔNG phải quy phạm — Đ3 tự tuyên bố điều đó"],
    expected_ops=[],
    expected_edges_sample=[
        edge("preamble", "tham_quyen", "91/2015/QH13", "Căn cứ Bộ luật Dân sự số 91/2015/QH13"),
        edge("preamble", "tham_quyen", "01/2019/NQ-HĐTP", "Căn cứ Nghị quyết số 01/2019/NQ-HĐTP"),
        edge("dieu:1/khoan:1", "pinpoint", "91/2015/QH13 dieu:468/khoan:1", "Khoản 1 Điều 468 Bộ luật Dân sự số 91/2015/QH13"),
        edge("dieu:1/khoan:2", "pinpoint", "47/2010/QH12 dieu:91", "Điều 91 Luật Các tổ chức tín dụng số 47/2010/QH12"),
        edge("dieu:2/khoan:1", "pinpoint", "01/2019/NQ-HĐTP dieu:7/khoan:2", "khoản 2 Điều 7 Nghị quyết số 01/2019/NQ-HĐTP"),
        edge("dieu:2/khoan:2", "pinpoint", "39/2016/TT-NHNN dieu:13", "Điều 13 Thông tư số 39/2016/TT-NHNN"),
    ],
))


def main():
    for d in DOCS:
        text = T(d['slug'])
        assert unicodedata.is_normalized('NFC', text), d['slug']
        d['sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
        c = count(text)
        d['counts'] = {k: c[k] for k in ('dieu', 'khoan', 'diem', 'tiet', 'phuluc')}
        url_file = CORPUS / 'raw' / d['slug'] / 'source_url.txt'
        if url_file.exists():
            d['source_url'] = url_file.read_text().strip()
    manifest = {"_meta": META, "documents": DOCS}
    out = CORPUS / 'manifest.json'
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    n_ops = sum(len(d['expected_ops']) for d in DOCS)
    print(f'{out}: {len(DOCS)} docs, {n_ops} expected_ops')


if __name__ == '__main__':
    main()
