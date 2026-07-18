"""Snapshot seed — corpus TT39/TT06/TT10/BLDS/NQ01 + nội bộ SHB (fixture F5).

MỘT nguồn dữ liệu cho cả ba nơi dùng:
  - `mem_store()`  → MemStore cho unit test + demo offline không cần Postgres;
  - `seed_postgres(conn)` → INSERT cùng corpus vào Postgres test/demo (F5 tự
    seed, không chờ F4 — CHÚ Ý: đây là fixture, run thật do engine F4 ghi);
  - `python -m answer.demo --seed` dùng cả hai đường.

Corpus mã hóa đúng các ca 00-VISION §2: amendment (TT06 sửa Đ7/Đ8/Đ13 TT39),
insert + suspension-theo-sự-kiện (k8-10 Đ8: TT06 bổ sung, TT10 ngưng đúng ngày
hiệu lực → CHƯA TỪNG active), grandfather scope-split (Đ13), conflict treo
Đ468 BLDS vs Đ13 TT39 giải bởi NQ01/2019, contamination bait (node amending
TT06 Đ1 chứa NGUYÊN VĂN k8-10, retrievable=false), audience (QĐ nội bộ SHB),
pending change 2026, closure-unresolved (Đ14 phí), consolidation-pending (Đ10).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from retrieval.query_builder import (ConflictRow, CoverageRow, EdgeRow, MemStore,
                                     OpBrief, RunInfo, SnapshotRow)

RUN_ID = "00000000-0000-4000-a000-000000000001"
K_CUTOFF = datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc)


def _n(i: int) -> str:  # node id
    return f"00000000-0000-4000-8000-{i:012d}"


def _o(i: int) -> str:  # op id
    return f"00000000-0000-4000-9000-{i:012d}"


# --- ids -------------------------------------------------------------------
N_D2, N_D7, N_D8 = _n(2), _n(7), _n(8)
N_K8, N_K9, N_K10 = _n(88), _n(89), _n(90)
N_D10, N_D13, N_D14 = _n(10), _n(13), _n(14)
N_TT06_D1, N_TT06_D6, N_TT10_D1 = _n(61), _n(66), _n(101)
N_BLDS_468, N_NQ01_D7, N_SHB = _n(468), _n(197), _n(500)

OP_TT06_D7, OP_TT06_D8, OP_TT06_D13 = _o(1), _o(2), _o(3)
OP_INS_K8, OP_INS_K9, OP_INS_K10 = _o(4), _o(5), _o(6)
OP_SUS_K8, OP_SUS_K9, OP_SUS_K10 = _o(7), _o(8), _o(9)
OP_NQ01, OP_2026_D7, OP_PROP_D10 = _o(10), _o(11), _o(12)

CONFLICT_468 = "00000000-0000-4000-b000-000000000001"
NORM_CHOVAY = "00000000-0000-4000-b000-000000000010"

INTERNAL_MARKER = "XYZZY-INTERNAL-742"  # canary INV-12: không byte nào lọt ra customer


# --- artifacts -------------------------------------------------------------
ARTIFACTS: dict[str, dict[str, Any]] = {
    "sha-tt39": dict(doc_key="39/2016/TT-NHNN", doc_type="thong_tu", issuer="NHNN",
                     title="Quy định về hoạt động cho vay của TCTD", audience="public",
                     issued=date(2016, 12, 30), effective=date(2017, 3, 15), channel="congbao"),
    "sha-tt06": dict(doc_key="06/2023/TT-NHNN", doc_type="thong_tu", issuer="NHNN",
                     title="Sửa đổi, bổ sung một số điều của TT 39/2016/TT-NHNN",
                     audience="public", issued=date(2023, 6, 28), effective=date(2023, 9, 1),
                     channel="congbao"),
    "sha-tt10": dict(doc_key="10/2023/TT-NHNN", doc_type="thong_tu", issuer="NHNN",
                     title="Ngưng hiệu lực thi hành một số nội dung của TT 39/2016/TT-NHNN",
                     audience="public", issued=date(2023, 8, 23), effective=date(2023, 9, 1),
                     channel="congbao"),
    "sha-blds": dict(doc_key="91/2015/QH13", doc_type="luat", issuer="QH",
                     title="Bộ luật Dân sự 2015", audience="public",
                     issued=date(2015, 11, 24), effective=date(2017, 1, 1), channel="congbao"),
    "sha-nq01": dict(doc_key="01/2019/NQ-HĐTP", doc_type="nghi_quyet", issuer="HDTP",
                     title="Hướng dẫn áp dụng quy định về lãi, lãi suất, phạt vi phạm",
                     audience="public", issued=date(2019, 1, 11), effective=date(2019, 3, 15),
                     channel="congbao"),
    "sha-2026": dict(doc_key="05/2026/TT-NHNN", doc_type="thong_tu", issuer="NHNN",
                     title="Sửa đổi TT 39/2016/TT-NHNN (fixture synthetic)", audience="public",
                     issued=date(2026, 5, 15), effective=date(2026, 9, 1), channel="congbao",
                     synthetic=True),
    "sha-shb": dict(doc_key="QT-TD-01/SHB", doc_type="noi_bo", issuer="SHB.QLTD",
                    title="Quy trình thẩm định và phê duyệt tín dụng nội bộ",
                    audience="internal", issued=date(2021, 12, 20), effective=date(2022, 1, 1),
                    channel="internal_registry", owner="SHB.QLTD"),
}


# --- text ------------------------------------------------------------------
T = {
    "d2": ("Điều 2. Giải thích từ ngữ",
           "Trong Thông tư này, các từ ngữ dưới đây được hiểu như sau: "
           "3. Khách hàng vay vốn tại tổ chức tín dụng là pháp nhân, cá nhân, bao gồm: "
           "a) Pháp nhân được thành lập và hoạt động tại Việt Nam, pháp nhân được thành lập "
           "ở nước ngoài và hoạt động hợp pháp tại Việt Nam; b) Cá nhân có quốc tịch Việt Nam, "
           "cá nhân có quốc tịch nước ngoài."),
    "d7_v1": ("Điều 7. Điều kiện vay vốn",
              "Tổ chức tín dụng xem xét, quyết định cho vay khi khách hàng có đủ các điều kiện "
              "sau đây: 1. Khách hàng là pháp nhân có năng lực pháp luật dân sự theo quy định "
              "của pháp luật; khách hàng là cá nhân từ đủ 18 tuổi trở lên có năng lực hành vi "
              "dân sự đầy đủ theo quy định của pháp luật. 2. Nhu cầu vay vốn để sử dụng vào mục "
              "đích hợp pháp. 3. Có phương án sử dụng vốn khả thi. 4. Có khả năng tài chính để "
              "trả nợ. 5. Trường hợp vay vốn theo lãi suất tối đa quy định tại khoản 2 Điều 13 "
              "Thông tư này, khách hàng được đánh giá là có tình hình tài chính minh bạch, lành mạnh."),
    "d7_v2": ("Điều 7. Điều kiện vay vốn",
              "Tổ chức tín dụng xem xét, quyết định cho vay khi khách hàng có đủ các điều kiện "
              "sau đây: 1. Khách hàng là pháp nhân có năng lực pháp luật dân sự theo quy định "
              "của pháp luật; khách hàng là cá nhân từ đủ 18 tuổi trở lên có năng lực hành vi "
              "dân sự đầy đủ theo quy định của pháp luật. 2. Nhu cầu vay vốn để sử dụng vào mục "
              "đích hợp pháp. 3. Có phương án sử dụng vốn khả thi; trường hợp cho vay bằng phương "
              "tiện điện tử, phương án sử dụng vốn được thẩm định qua hệ thống công nghệ thông tin. "
              "4. Có khả năng tài chính để trả nợ."),
    "d7_v3": ("Điều 7. Điều kiện vay vốn",
              "Tổ chức tín dụng xem xét, quyết định cho vay khi khách hàng có đủ các điều kiện "
              "sau đây: 1. Khách hàng là pháp nhân có năng lực pháp luật dân sự; cá nhân từ đủ "
              "18 tuổi có năng lực hành vi dân sự đầy đủ, đã được định danh điện tử mức độ 2. "
              "2. Nhu cầu vay vốn để sử dụng vào mục đích hợp pháp. 3. Có phương án sử dụng vốn "
              "khả thi. 4. Có khả năng tài chính để trả nợ."),
    "d8_v1": ("Điều 8. Những nhu cầu vốn không được cho vay",
              "Tổ chức tín dụng không được cho vay đối với các nhu cầu vốn: 1. Để thực hiện các "
              "hoạt động đầu tư kinh doanh thuộc ngành, nghề mà pháp luật cấm đầu tư kinh doanh. "
              "2. Để thanh toán các chi phí, đáp ứng các nhu cầu tài chính của các giao dịch, "
              "hành vi mà pháp luật cấm. 3. Để mua, sử dụng các hàng hóa, dịch vụ thuộc ngành, "
              "nghề mà pháp luật cấm đầu tư kinh doanh. 4. Để mua vàng miếng. 5. Để trả nợ khoản "
              "cấp tín dụng tại chính tổ chức tín dụng cho vay. 6. Để trả nợ khoản cấp tín dụng "
              "tại tổ chức tín dụng khác và trả nợ khoản vay nước ngoài, trừ trường hợp cho vay "
              "để trả nợ trước hạn khoản vay đáp ứng đầy đủ các điều kiện sau đây: a) Là khoản "
              "vay phục vụ hoạt động kinh doanh; b) Thời hạn cho vay không vượt quá thời hạn cho "
              "vay còn lại của khoản vay cũ; c) Là khoản vay chưa thực hiện cơ cấu lại thời hạn trả nợ."),
    "d8_v2": ("Điều 8. Những nhu cầu vốn không được cho vay",
              "Tổ chức tín dụng không được cho vay đối với các nhu cầu vốn: 1. Để thực hiện các "
              "hoạt động đầu tư kinh doanh thuộc ngành, nghề mà pháp luật cấm đầu tư kinh doanh. "
              "2. Để thanh toán các chi phí, đáp ứng các nhu cầu tài chính của các giao dịch, "
              "hành vi mà pháp luật cấm. 3. Để mua, sử dụng các hàng hóa, dịch vụ thuộc ngành, "
              "nghề mà pháp luật cấm đầu tư kinh doanh. 4. Để mua vàng miếng. 5. Để trả nợ khoản "
              "cấp tín dụng tại chính tổ chức tín dụng cho vay, trừ trường hợp cho vay để thanh "
              "toán lãi tiền vay phát sinh trong quá trình thi công xây dựng công trình. 6. Để "
              "trả nợ khoản cấp tín dụng tại tổ chức tín dụng khác và trả nợ khoản vay nước ngoài "
              "(không bao gồm khoản vay nước ngoài dưới hình thức mua bán hàng hóa trả chậm), trừ "
              "trường hợp cho vay để trả nợ trước hạn khoản vay đáp ứng đầy đủ các điều kiện sau "
              "đây: a) Thời hạn cho vay không vượt quá thời hạn cho vay còn lại của khoản vay cũ; "
              "b) Là khoản vay chưa thực hiện cơ cấu lại thời hạn trả nợ."),
    "k8": (None, "8. Để thanh toán tiền góp vốn, mua, nhận chuyển nhượng phần vốn góp của công "
                 "ty trách nhiệm hữu hạn, công ty hợp danh; góp vốn, mua, nhận chuyển nhượng cổ "
                 "phần của công ty cổ phần chưa niêm yết trên thị trường chứng khoán hoặc chưa "
                 "đăng ký giao dịch trên hệ thống giao dịch UPCoM."),
    "k9": (None, "9. Để thanh toán tiền góp vốn theo hợp đồng góp vốn, hợp đồng hợp tác đầu tư "
                 "hoặc hợp đồng hợp tác kinh doanh để thực hiện dự án đầu tư không đủ điều kiện "
                 "đưa vào kinh doanh theo quy định của pháp luật tại thời điểm tổ chức tín dụng "
                 "quyết định cho vay."),
    "k10": (None, "10. Để bù đắp tài chính, trừ trường hợp khoản vay đáp ứng đầy đủ các điều "
                  "kiện sau đây: a) Khách hàng đã ứng vốn của chính khách hàng để thanh toán, "
                  "chi trả chi phí thực hiện dự án hoạt động kinh doanh phát sinh dưới 12 tháng "
                  "tính đến thời điểm tổ chức tín dụng quyết định cho vay; b) Các chi phí đã "
                  "thanh toán, chi trả bằng vốn của chính khách hàng nhằm thực hiện dự án hoạt "
                  "động kinh doanh có sử dụng nguồn vốn vay của tổ chức tín dụng theo phương án "
                  "sử dụng vốn đã gửi tổ chức tín dụng."),
    "d10": ("Điều 10. Loại cho vay",
            "Tổ chức tín dụng xem xét quyết định cho khách hàng vay theo các loại cho vay như "
            "sau: 1. Cho vay ngắn hạn là các khoản cho vay có thời hạn cho vay tối đa 01 năm. "
            "2. Cho vay trung hạn là các khoản cho vay có thời hạn cho vay trên 01 năm và tối đa "
            "05 năm. 3. Cho vay dài hạn là các khoản cho vay có thời hạn cho vay trên 05 năm."),
    "d13_v1": ("Điều 13. Lãi suất cho vay",
               "1. Tổ chức tín dụng và khách hàng thỏa thuận về lãi suất cho vay theo cung cầu "
               "vốn thị trường, nhu cầu vay vốn và mức độ tín nhiệm của khách hàng, trừ trường "
               "hợp Ngân hàng Nhà nước Việt Nam có quy định về lãi suất cho vay tối đa tại khoản "
               "2 Điều này. 2. Tổ chức tín dụng và khách hàng thỏa thuận về lãi suất cho vay "
               "ngắn hạn bằng đồng Việt Nam nhưng không vượt quá mức lãi suất cho vay tối đa do "
               "Thống đốc Ngân hàng Nhà nước Việt Nam quyết định trong từng thời kỳ. 4. Trường "
               "hợp khoản nợ vay bị chuyển nợ quá hạn, thì khách hàng phải trả lãi trên dư nợ "
               "gốc bị quá hạn tương ứng với thời gian chậm trả, lãi suất áp dụng không vượt quá "
               "150% lãi suất cho vay trong hạn tại thời điểm chuyển nợ quá hạn."),
    "d13_v2": ("Điều 13. Lãi suất cho vay",
               "1. Tổ chức tín dụng và khách hàng thỏa thuận về lãi suất cho vay theo cung cầu "
               "vốn thị trường, nhu cầu vay vốn và mức độ tín nhiệm của khách hàng, trừ trường "
               "hợp Ngân hàng Nhà nước Việt Nam có quy định về lãi suất cho vay tối đa tại khoản "
               "2 Điều này. 1a. Tổ chức tín dụng công bố mức lãi suất cho vay bình quân và chênh "
               "lệch lãi suất tiền gửi - cho vay trên trang thông tin điện tử của tổ chức tín "
               "dụng. 2. Tổ chức tín dụng và khách hàng thỏa thuận về lãi suất cho vay ngắn hạn "
               "bằng đồng Việt Nam nhưng không vượt quá mức lãi suất cho vay tối đa do Thống đốc "
               "Ngân hàng Nhà nước Việt Nam quyết định trong từng thời kỳ. 4. Trường hợp khoản "
               "nợ vay bị chuyển nợ quá hạn, thì khách hàng phải trả lãi trên dư nợ gốc bị quá "
               "hạn, lãi suất áp dụng không vượt quá 150% lãi suất cho vay trong hạn tại thời "
               "điểm chuyển nợ quá hạn."),
    "d14": ("Điều 14. Phí liên quan đến hoạt động cho vay",
            "Tổ chức tín dụng và khách hàng thỏa thuận về việc thu các loại phí liên quan đến "
            "hoạt động cho vay, gồm: 1. Phí trả nợ trước hạn trong trường hợp khách hàng trả nợ "
            "trước hạn. 2. Phí trả cho hạn mức tín dụng dự phòng. 3. Phí thu xếp cho vay hợp "
            "vốn. 4. Phí cam kết rút vốn. 5. Các loại phí khác, trừ trường hợp quy định tại văn "
            "bản quy phạm pháp luật liên quan khác."),
    "tt06_d1": ("Điều 1. Sửa đổi, bổ sung một số điều của Thông tư số 39/2016/TT-NHNN",
                "Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8 như sau: \"8. Để thanh toán "
                "tiền góp vốn, mua, nhận chuyển nhượng phần vốn góp của công ty trách nhiệm hữu "
                "hạn, công ty hợp danh; góp vốn, mua, nhận chuyển nhượng cổ phần của công ty cổ "
                "phần chưa niêm yết trên thị trường chứng khoán hoặc chưa đăng ký giao dịch trên "
                "hệ thống giao dịch UPCoM. 9. Để thanh toán tiền góp vốn theo hợp đồng góp vốn, "
                "hợp đồng hợp tác đầu tư hoặc hợp đồng hợp tác kinh doanh để thực hiện dự án đầu "
                "tư không đủ điều kiện đưa vào kinh doanh theo quy định của pháp luật. 10. Để bù "
                "đắp tài chính, trừ trường hợp khoản vay đáp ứng đầy đủ các điều kiện quy định.\""),
    "tt06_d6": ("Điều 6. Quy định chuyển tiếp",
                "Các thỏa thuận cho vay, hợp đồng cho vay được ký kết trước ngày Thông tư này có "
                "hiệu lực thi hành, tổ chức tín dụng và khách hàng tiếp tục thực hiện các nội "
                "dung theo thỏa thuận, hợp đồng đã ký kết phù hợp với quy định của pháp luật có "
                "hiệu lực thi hành tại thời điểm ký kết, hoặc thỏa thuận sửa đổi, bổ sung phù "
                "hợp với quy định tại Thông tư này."),
    "tt10_d1": ("Điều 1. Ngưng hiệu lực thi hành một số nội dung của Thông tư số 39/2016/TT-NHNN",
                "Ngưng hiệu lực thi hành khoản 8, khoản 9, khoản 10 Điều 8 Thông tư số "
                "39/2016/TT-NHNN (đã được bổ sung theo khoản 2 Điều 1 Thông tư số "
                "06/2023/TT-NHNN) từ ngày 01 tháng 9 năm 2023 cho đến ngày có hiệu lực thi hành "
                "của văn bản quy phạm pháp luật mới quy định về các vấn đề này. Nội dung ngưng "
                "gồm: để thanh toán tiền góp vốn, mua, nhận chuyển nhượng phần vốn góp của công "
                "ty trách nhiệm hữu hạn, công ty hợp danh; góp vốn theo hợp đồng hợp tác đầu tư; "
                "để bù đắp tài chính."),
    "blds468": ("Điều 468. Lãi suất",
                "1. Lãi suất vay do các bên thỏa thuận. Trường hợp các bên có thỏa thuận về lãi "
                "suất thì lãi suất theo thỏa thuận không được vượt quá 20%/năm của khoản tiền "
                "vay, trừ trường hợp luật khác có liên quan quy định khác. 2. Trường hợp các bên "
                "có thỏa thuận về việc trả lãi, nhưng không xác định rõ lãi suất và có tranh "
                "chấp về lãi suất thì lãi suất được xác định bằng 50% mức lãi suất giới hạn quy "
                "định tại khoản 1 Điều này."),
    "nq01_d7": ("Điều 7. Áp dụng pháp luật về lãi, lãi suất trong hợp đồng tín dụng",
                "Lãi suất trong hợp đồng tín dụng do các bên thỏa thuận nhưng phải phù hợp với "
                "quy định của Luật Các tổ chức tín dụng và văn bản quy phạm pháp luật quy định "
                "chi tiết, hướng dẫn áp dụng Luật Các tổ chức tín dụng tại thời điểm xác lập hợp "
                "đồng, thời điểm tính lãi suất; không áp dụng mức trần lãi suất 20%/năm quy định "
                "tại Điều 468 Bộ luật Dân sự năm 2015."),
    "shb": ("Điều 1. Hạn mức phê duyệt tín dụng nội bộ",
            f"TÀI LIỆU NỘI BỘ SHB — MÃ {INTERNAL_MARKER}. Hạn mức phê duyệt tín dụng của Giám "
            "đốc chi nhánh tối đa 5 tỷ đồng một khách hàng; vượt hạn mức phải trình Hội đồng tín "
            "dụng Hội sở. Quy trình thẩm định nội bộ thực hiện theo quy định của Ngân hàng Nhà "
            "nước về hoạt động cho vay."),
    "d7_2026_note": None,
}

GF_SCOPE = {"contract_signed_before": "2023-09-01", "not_amended_on_or_after": "2023-09-01"}


def _rows() -> list[SnapshotRow]:
    def row(node_id, version, tkey, status, vf, vt, artifact, path, role="rule",
            scope=None, scope_hash="", prov=(), retrievable=True):
        heading, body = T[tkey]
        art = ARTIFACTS[artifact]
        return SnapshotRow(
            node_id=node_id, version=version, heading=heading, body=body, status=status,
            valid_from=vf, valid_to=vt, scope_predicate=scope, scope_hash=scope_hash,
            provenance=tuple(prov), run_id=RUN_ID, path=path, role=role,
            artifact_id=artifact, doc_key=art["doc_key"], audience=art["audience"],
            title=art["title"], retrievable=retrievable)

    d = date
    return [
        row(N_D2, 1, "d2", "active", d(2017, 3, 15), None, "sha-tt39", "dieu:2", role="definition"),
        row(N_D7, 1, "d7_v1", "active", d(2017, 3, 15), d(2023, 9, 1), "sha-tt39", "dieu:7"),
        row(N_D7, 2, "d7_v2", "active", d(2023, 9, 1), d(2026, 9, 1), "sha-tt39", "dieu:7",
            prov=[OP_TT06_D7]),
        row(N_D7, 3, "d7_v3", "active", d(2026, 9, 1), None, "sha-tt39", "dieu:7",
            prov=[OP_TT06_D7, OP_2026_D7]),
        row(N_D8, 1, "d8_v1", "active", d(2017, 3, 15), d(2023, 9, 1), "sha-tt39", "dieu:8"),
        row(N_D8, 2, "d8_v2", "active", d(2023, 9, 1), None, "sha-tt39", "dieu:8",
            prov=[OP_TT06_D8]),
        # k8-10: TT06 bổ sung, TT10 ngưng ĐÚNG ngày hiệu lực — chưa từng active (D-24)
        row(N_K8, 1, "k8", "suspended", d(2023, 9, 1), None, "sha-tt39", "dieu:8/khoan:8",
            prov=[OP_INS_K8, OP_SUS_K8]),
        row(N_K9, 1, "k9", "suspended", d(2023, 9, 1), None, "sha-tt39", "dieu:8/khoan:9",
            prov=[OP_INS_K9, OP_SUS_K9]),
        row(N_K10, 1, "k10", "suspended", d(2023, 9, 1), None, "sha-tt39", "dieu:8/khoan:10",
            prov=[OP_INS_K10, OP_SUS_K10]),
        row(N_D10, 1, "d10", "active", d(2017, 3, 15), None, "sha-tt39", "dieu:10"),
        row(N_D13, 1, "d13_v1", "active", d(2017, 3, 15), d(2023, 9, 1), "sha-tt39", "dieu:13"),
        row(N_D13, 2, "d13_v2", "active", d(2023, 9, 1), None, "sha-tt39", "dieu:13",
            prov=[OP_TT06_D13]),
        # grandfather: nhánh scope song song CÙNG cửa sổ (D-04) — text CŨ tiếp tục govern
        row(N_D13, 3, "d13_v1", "active", d(2023, 9, 1), None, "sha-tt39", "dieu:13",
            scope=dict(GF_SCOPE), scope_hash="gf-2023-09-01", prov=[OP_TT06_D13]),
        row(N_D14, 1, "d14", "active", d(2017, 3, 15), None, "sha-tt39", "dieu:14"),
        # node amending — retrievable FALSE (D-05/INV-8): chứa NGUYÊN VĂN k8-10
        row(N_TT06_D1, 1, "tt06_d1", "active", d(2023, 9, 1), None, "sha-tt06", "dieu:1",
            role="amending", retrievable=False),
        row(N_TT06_D6, 1, "tt06_d6", "active", d(2023, 9, 1), None, "sha-tt06", "dieu:6",
            role="transition"),
        row(N_TT10_D1, 1, "tt10_d1", "active", d(2023, 9, 1), None, "sha-tt10", "dieu:1",
            role="amending", retrievable=False),
        row(N_BLDS_468, 1, "blds468", "active", d(2017, 1, 1), None, "sha-blds", "dieu:468"),
        row(N_NQ01_D7, 1, "nq01_d7", "active", d(2019, 3, 15), None, "sha-nq01", "dieu:7"),
        row(N_SHB, 1, "shb", "active", d(2022, 1, 1), None, "sha-shb", "dieu:1"),
    ]


EDGES: list[EdgeRow] = [
    EdgeRow(src_node=N_D7, src_version=1, kind="ngoai_le", dst_node=N_D8,
            raw_citation="nhu cầu vốn không được cho vay tại Điều 8"),
    EdgeRow(src_node=N_D7, src_version=2, kind="ngoai_le", dst_node=N_D8,
            raw_citation="nhu cầu vốn không được cho vay tại Điều 8"),
    EdgeRow(src_node=N_D7, src_version=3, kind="ngoai_le", dst_node=N_D8,
            raw_citation="nhu cầu vốn không được cho vay tại Điều 8"),
    EdgeRow(src_node=N_D7, src_version=1, kind="dinh_nghia", dst_node=N_D2, raw_citation="khách hàng"),
    EdgeRow(src_node=N_D7, src_version=2, kind="dinh_nghia", dst_node=N_D2, raw_citation="khách hàng"),
    EdgeRow(src_node=N_D8, src_version=2, kind="dinh_nghia", dst_node=N_D2, raw_citation="khách hàng"),
    EdgeRow(src_node=N_D13, src_version=2, kind="chuyen_tiep", dst_node=N_TT06_D6,
            raw_citation="quy định chuyển tiếp TT 06/2023/TT-NHNN"),
    EdgeRow(src_node=N_D13, src_version=3, kind="chuyen_tiep", dst_node=N_TT06_D6,
            raw_citation="quy định chuyển tiếp TT 06/2023/TT-NHNN"),
    EdgeRow(src_node=N_D7, src_version=2, kind="chuyen_tiep", dst_node=N_TT06_D6,
            raw_citation="quy định chuyển tiếp TT 06/2023/TT-NHNN"),
    # chu_de trỏ Norm — nuôi blast-radius, KHÔNG gate closure (D-29)
    EdgeRow(src_node=N_SHB, src_version=1, kind="chu_de", dst_norm=NORM_CHOVAY,
            raw_citation="quy định của NHNN về hoạt động cho vay"),
]

# Đ14: ngoại lệ trỏ 'văn bản khác' CHƯA resolve (backlog R-10, confidence 0) —
# chạm là Tier D theo D-29. TÁCH khỏi seed mặc định: corpus fixture chỉ ~11 node
# nên MỌI câu hỏi đều kéo Đ14 vào top-12 → gate giết toàn bộ demo (artifact của
# cỡ corpus, không phải của gate). Test closure bật tường minh with_unresolved_d14.
UNRESOLVED_D14_EDGE = EdgeRow(
    src_node=N_D14, src_version=1, kind="ngoai_le", dst_node=None,
    raw_citation="trừ trường hợp quy định tại văn bản quy phạm pháp luật liên quan khác",
    confidence=0.0)

CONFLICTS: list[ConflictRow] = [
    ConflictRow(
        id=CONFLICT_468, member_node_ids=(N_BLDS_468, N_D13), tier=2, label="mau_thuan",
        reason=("Trần lãi suất thỏa thuận 20%/năm (Điều 468 BLDS 2015) vs cơ chế lãi suất "
                "thỏa thuận của TCTD (Điều 13 TT 39/2016/TT-NHNN) — Điều 156 Luật BHVBQPPL "
                "không phân định được (khác cơ quan ban hành)."),
        status="resolved", resolved_by_op=OP_NQ01,
        resolution_valid_from=date(2019, 3, 15)),
]

COVERAGE_ROWS: list[CoverageRow] = [
    CoverageRow(channel="congbao", last_seq="59/2026", last_checked=K_CUTOFF),
    CoverageRow(channel="internal_registry", last_seq="2026-07-01", last_checked=K_CUTOFF),
]

ALIASES: list[tuple[str, str, str]] = [
    ("39/2016/TT-NHNN", "dieu:2", N_D2), ("39/2016/TT-NHNN", "dieu:7", N_D7),
    ("39/2016/TT-NHNN", "dieu:8", N_D8), ("39/2016/TT-NHNN", "dieu:8/khoan:8", N_K8),
    ("39/2016/TT-NHNN", "dieu:8/khoan:9", N_K9), ("39/2016/TT-NHNN", "dieu:8/khoan:10", N_K10),
    ("39/2016/TT-NHNN", "dieu:10", N_D10), ("39/2016/TT-NHNN", "dieu:13", N_D13),
    ("39/2016/TT-NHNN", "dieu:14", N_D14),
    ("06/2023/TT-NHNN", "dieu:1", N_TT06_D1), ("06/2023/TT-NHNN", "dieu:6", N_TT06_D6),
    ("10/2023/TT-NHNN", "dieu:1", N_TT10_D1),
    ("91/2015/QH13", "dieu:468", N_BLDS_468), ("01/2019/NQ-HĐTP", "dieu:7", N_NQ01_D7),
    ("QT-TD-01/SHB", "dieu:1", N_SHB),
]

OPS: dict[str, OpBrief] = {
    OP_TT06_D7: OpBrief(OP_TT06_D7, "amend", "06/2023/TT-NHNN", date(2023, 9, 1)),
    OP_TT06_D8: OpBrief(OP_TT06_D8, "amend", "06/2023/TT-NHNN", date(2023, 9, 1)),
    OP_TT06_D13: OpBrief(OP_TT06_D13, "amend", "06/2023/TT-NHNN", date(2023, 9, 1)),
    OP_INS_K8: OpBrief(OP_INS_K8, "insert", "06/2023/TT-NHNN", date(2023, 9, 1)),
    OP_INS_K9: OpBrief(OP_INS_K9, "insert", "06/2023/TT-NHNN", date(2023, 9, 1)),
    OP_INS_K10: OpBrief(OP_INS_K10, "insert", "06/2023/TT-NHNN", date(2023, 9, 1)),
    OP_SUS_K8: OpBrief(OP_SUS_K8, "suspend", "10/2023/TT-NHNN", date(2023, 9, 1)),
    OP_SUS_K9: OpBrief(OP_SUS_K9, "suspend", "10/2023/TT-NHNN", date(2023, 9, 1)),
    OP_SUS_K10: OpBrief(OP_SUS_K10, "suspend", "10/2023/TT-NHNN", date(2023, 9, 1)),
    OP_NQ01: OpBrief(OP_NQ01, "norm_decl", "01/2019/NQ-HĐTP", date(2019, 3, 15)),
    OP_2026_D7: OpBrief(OP_2026_D7, "amend", "05/2026/TT-NHNN", date(2026, 9, 1)),
}


def mem_store(with_unresolved_d14: bool = False) -> MemStore:
    edges = EDGES + ([UNRESOLVED_D14_EDGE] if with_unresolved_d14 else [])
    return MemStore(
        rows=_rows(), edges=edges, conflicts=CONFLICTS,
        consolidation={N_D10},
        coverage_rows=COVERAGE_ROWS, aliases=ALIASES,
        suspension_pending_ops={OP_SUS_K8, OP_SUS_K9, OP_SUS_K10},
        ops=OPS, run=RunInfo(run_id=RUN_ID, k_cutoff=K_CUTOFF))


# ---------------------------------------------------------------------------
# Postgres seeding — cùng corpus (fixture; run thật do F4 ghi)
# ---------------------------------------------------------------------------

def seed_postgres(conn, force: bool = False, with_unresolved_d14: bool = False) -> bool:
    """Seed idempotent; trả True nếu vừa seed, False nếu đã có sẵn.
    DB mới tinh (chưa có schema) → tự chạy db/init.sql trước."""
    from pathlib import Path

    from psycopg.types.json import Jsonb

    if conn.execute("SELECT to_regclass('public.replay_run')").fetchone()[0] is None:
        init_sql = (Path(__file__).resolve().parent.parent / "db" / "init.sql"
                    ).read_text(encoding="utf-8")
        conn.execute(init_sql)
        conn.commit()

    have = conn.execute("SELECT 1 FROM replay_run WHERE run_id = %s", (RUN_ID,)).fetchone()
    if have and not force:
        return False

    # DB bẩn (ví dụ leftover của test khác): doc_key đã thuộc artifact id khác —
    # artifact append-only nên không thể sửa; báo rõ thay vì chết giữa chừng.
    clash = conn.execute(
        "SELECT doc_key, id FROM artifact WHERE doc_key = ANY(%s) AND NOT id = ANY(%s)",
        ([a["doc_key"] for a in ARTIFACTS.values()], list(ARTIFACTS.keys()))).fetchall()
    if clash:
        raise RuntimeError(
            f"DB đã có doc_key {[c[0] for c in clash]} thuộc artifact id khác — "
            "seed fixture cần database sạch (tạo DB mới hoặc DROP SCHEMA trước).")

    for aid, a in ARTIFACTS.items():
        conn.execute(
            """INSERT INTO artifact (id, doc_key, doc_type, issuer, title, issued_date,
                                     effective_date, audience, owner, channel, synthetic, text)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (aid, a["doc_key"], a["doc_type"], a["issuer"], a["title"], a["issued"],
             a["effective"], a["audience"], a.get("owner"), a["channel"],
             a.get("synthetic", False), None))

    rows = _rows()
    nodes_done: set[str] = set()
    for r in rows:
        if r.node_id in nodes_done:
            continue
        nodes_done.add(r.node_id)
        conn.execute(
            """INSERT INTO node (id, artifact_id, path, role) VALUES (%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (r.node_id, r.artifact_id, r.path, r.role))

    for dk, path, nid in ALIASES:
        vf = min(r.valid_from for r in rows if r.node_id == nid)
        conn.execute(
            """INSERT INTO alias (doc_key, path, node_id, valid_from)
               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (dk, path, nid, vf))

    _seed_ops(conn)

    conn.execute("""INSERT INTO replay_run (run_id, k_cutoff, corpus_hash, started, finished, ops_count)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id) DO NOTHING""",
                 (RUN_ID, K_CUTOFF, "seed-f5-v1", K_CUTOFF, K_CUTOFF, len(OPS)))

    for r in rows:
        conn.execute(
            """INSERT INTO node_version (node_id, version, heading, body, status, valid_from,
                                         valid_to, scope_predicate, scope_hash, provenance,
                                         run_id, retrievable)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s)
               ON CONFLICT (node_id, version) DO NOTHING""",
            (r.node_id, r.version, r.heading, r.body, r.status, r.valid_from, r.valid_to,
             Jsonb(r.scope_predicate) if r.scope_predicate else None, r.scope_hash,
             list(r.provenance), r.run_id, r.retrievable))

    for e in EDGES + ([UNRESOLVED_D14_EDGE] if with_unresolved_d14 else []):
        conn.execute(
            """INSERT INTO edge (src_node, src_version, dst_node, dst_norm, frontier_ref,
                                 kind, raw_citation, confidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (e.src_node, e.src_version, e.dst_node, e.dst_norm, e.frontier_ref,
             e.kind, e.raw_citation, e.confidence))

    c = CONFLICTS[0]
    conn.execute(
        """INSERT INTO conflict (id, member_versions, tier, label, fork, doctrine, reason,
                                 status, resolved_by_op, detected_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
        (c.id, Jsonb([{"node_id": N_BLDS_468, "version": 1}, {"node_id": N_D13, "version": 1}]),
         c.tier, c.label, "external_external",
         Jsonb({"rank_a": "luat", "rank_b": "thong_tu", "same_issuer": False,
                "art156": "khong_phan_dinh"}),
         c.reason, c.status, c.resolved_by_op, "seed"))

    for op_id in (OP_SUS_K8, OP_SUS_K9, OP_SUS_K10):
        conn.execute(
            """INSERT INTO pending_event (kind, ref, predicate, status)
               VALUES ('open_suspension', %s,
                       'văn bản QPPL mới quy định về các vấn đề này có hiệu lực', 'open')""",
            (op_id,))

    for cv in COVERAGE_ROWS:
        conn.execute(
            """INSERT INTO coverage (channel, last_seq, last_checked) VALUES (%s,%s,%s)
               ON CONFLICT (channel) DO UPDATE SET last_seq = EXCLUDED.last_seq,
                                                   last_checked = EXCLUDED.last_checked""",
            (cv.channel, cv.last_seq, cv.last_checked))

    conn.commit()
    return True


def _seed_ops(conn) -> None:
    def op(op_id, kind, src_art, src_node, quote, seq, target_node=None, target_norm=None,
           new_text=None, vf=None, vte=None, status="ratified"):
        conn.execute(
            """INSERT INTO op (id, kind, source_artifact, source_node, source_quote, seq,
                               target_node, target_norm, new_text, valid_from, valid_to_event,
                               risk_class, extractor, confidence, status, ratified_by, ratified_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (op_id, kind, src_art, src_node, quote, seq, target_node, target_norm,
             new_text, vf, vte, "prescriptive", "rule", 0.99, status,
             "curator:seed" if status == "ratified" else None,
             K_CUTOFF if status == "ratified" else None))

    d = date(2023, 9, 1)
    op(OP_TT06_D7, "amend", "sha-tt06", N_TT06_D1, "Sửa đổi, bổ sung Điều 7 như sau", 1,
       target_node=N_D7, new_text=T["d7_v2"][1], vf=d)
    op(OP_TT06_D8, "amend", "sha-tt06", N_TT06_D1, "Sửa đổi, bổ sung khoản 5, 6 Điều 8", 2,
       target_node=N_D8, new_text=T["d8_v2"][1], vf=d)
    op(OP_INS_K8, "insert", "sha-tt06", N_TT06_D1, "Bổ sung khoản 8 vào Điều 8 như sau", 3,
       target_node=N_K8, new_text=T["k8"][1], vf=d)
    op(OP_INS_K9, "insert", "sha-tt06", N_TT06_D1, "Bổ sung khoản 9 vào Điều 8 như sau", 4,
       target_node=N_K9, new_text=T["k9"][1], vf=d)
    op(OP_INS_K10, "insert", "sha-tt06", N_TT06_D1, "Bổ sung khoản 10 vào Điều 8 như sau", 5,
       target_node=N_K10, new_text=T["k10"][1], vf=d)
    op(OP_TT06_D13, "amend", "sha-tt06", N_TT06_D1, "Sửa đổi, bổ sung Điều 13 như sau", 6,
       target_node=N_D13, new_text=T["d13_v2"][1], vf=d)
    for opid, target, kh in ((OP_SUS_K8, N_K8, 8), (OP_SUS_K9, N_K9, 9), (OP_SUS_K10, N_K10, 10)):
        op(opid, "suspend", "sha-tt10", N_TT10_D1,
           f"Ngưng hiệu lực thi hành khoản {kh} Điều 8 Thông tư số 39/2016/TT-NHNN", kh - 7,
           target_node=target, vf=d,
           vte="đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới")
    op(OP_NQ01, "norm_decl", "sha-nq01", N_NQ01_D7,
       "không áp dụng mức trần lãi suất 20%/năm quy định tại Điều 468 Bộ luật Dân sự", 1,
       target_norm=NORM_CHOVAY, vf=date(2019, 3, 15))
    op(OP_2026_D7, "amend", "sha-2026", None, "Sửa đổi, bổ sung Điều 7 như sau", 1,
       target_node=N_D7, new_text=T["d7_v3"][1], vf=date(2026, 9, 1))
    # op proposed đã ĐẾN HẠN hiệu lực nhưng chưa phê chuẩn → v_consolidation_pending (Đ10)
    op(OP_PROP_D10, "amend", "sha-2026", None, "Sửa đổi Điều 10 (đề xuất, chưa phê chuẩn)", 2,
       target_node=N_D10, new_text="Điều 10 (dự thảo sửa đổi).", vf=date(2026, 7, 1),
       status="proposed")
