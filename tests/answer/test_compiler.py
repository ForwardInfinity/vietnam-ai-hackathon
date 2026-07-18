"""Question compiler (R-27, D-26) — bộ test riêng, phần thi đấu. Verification nhóm 5.

≥30 câu: thời điểm, cohort, pinpoint, 'đã từng', không dấu, mơ hồ.
"""
from datetime import date, datetime, timezone

import pytest

from answer.compiler import SessionCtx, compile_question, strip_diacritics
from api.schemas import Cohort

TODAY = date(2026, 7, 18)
DOC_KEYS = ["39/2016/TT-NHNN", "06/2023/TT-NHNN", "10/2023/TT-NHNN",
            "91/2015/QH13", "01/2019/NQ-HĐTP"]


def go(q, audience="employee", as_of=None, cohort=None):
    ctx = SessionCtx(audience=audience, as_of=as_of, cohort=cohort)
    return compile_question(q, ctx, known_doc_keys=DOC_KEYS, today=TODAY)


# ---------------------------------------------------------------------- thời điểm

def test_01_current_default():
    cq = go("Điều kiện vay vốn là gì?")
    assert cq.mode == "current" and cq.as_of == TODAY


def test_02_hien_nay_current():
    cq = go("Điều kiện vay vốn hiện nay là gì?")
    assert cq.mode == "current" and cq.as_of == TODAY


def test_03_explicit_year():
    cq = go("Điều kiện vay vốn năm 2022 thế nào?")
    assert cq.mode == "point_in_time" and cq.as_of == date(2022, 12, 31)


def test_04_explicit_date_slash():
    cq = go("Lãi suất cho vay tại ngày 01/03/2024?")
    assert cq.mode == "point_in_time" and cq.as_of == date(2024, 3, 1)


def test_05_explicit_date_long_form():
    cq = go("Quy định tại ngày 15 tháng 3 năm 2022?")
    assert cq.as_of == date(2022, 3, 15) and cq.mode == "point_in_time"


def test_06_month_year():
    cq = go("Trong tháng 3/2022 quy định thế nào?")
    assert cq.as_of == date(2022, 3, 31) and cq.mode == "point_in_time"


def test_07_date_dash():
    cq = go("Tại thời điểm giải ngân 15-03-2022 ngân hàng biết gì?")
    assert cq.as_of == date(2022, 3, 15)


def test_08_docnum_year_not_time():
    """'06/2023' trong số hiệu KHÔNG phải mốc thời gian (bảo vệ trước khi parse)."""
    cq = go("Thông tư 06/2023/TT-NHNN sửa những gì?")
    assert cq.as_of == TODAY and cq.mode == "current"


def test_09_ctx_as_of_when_no_text_time():
    cq = go("Điều kiện vay vốn?", as_of=date(2024, 3, 1))
    assert cq.as_of == date(2024, 3, 1) and cq.mode == "point_in_time"


def test_10_text_time_wins_over_ctx():
    cq = go("Điều kiện vay vốn năm 2020?", as_of=date(2024, 3, 1))
    assert cq.as_of == date(2020, 12, 31)


def test_11_hien_nay_respects_ctx_as_of():
    # as-of control của UI định nghĩa "bây giờ" — không nhảy về máy chủ hôm nay
    cq = go("Lãi suất hiện nay?", as_of=date(2024, 3, 1))
    assert cq.as_of == date(2024, 3, 1)


# ---------------------------------------------------------------------- pending

def test_12_sap_toi_pending():
    cq = go("Sắp tới điều kiện vay vốn có gì thay đổi?")
    assert cq.mode == "pending"


def test_13_tu_thang_sau_pending():
    cq = go("Từ tháng sau có quy định mới nào áp dụng không?")
    assert cq.mode == "pending"


def test_14_sap_co_hieu_luc_pending_khong_dau():
    cq = go("quy dinh nao sap co hieu luc?")
    assert cq.mode == "pending"


# ---------------------------------------------------------------------- history

def test_15_da_tung_history():
    cq = go("Khoản 8 Điều 8 Thông tư 39/2016/TT-NHNN đã từng có hiệu lực chưa?")
    assert cq.mode == "history"
    assert cq.pinpoint == "39/2016/TT-NHNN#dieu:8/khoan:8"


def test_16_truoc_day_history():
    cq = go("Trước đây có quy định cấm cho vay góp vốn không?")
    assert cq.mode == "history"


def test_17_lich_su_history():
    cq = go("Cho tôi lịch sử hiệu lực của Điều 8 Thông tư 39/2016/TT-NHNN")
    assert cq.mode == "history" and cq.pinpoint == "39/2016/TT-NHNN#dieu:8"


# ---------------------------------------------------------------------- pinpoint

def test_18_pinpoint_khoan_dieu_docnum():
    cq = go("Khoản 2 Điều 13 Thông tư 39/2016/TT-NHNN quy định gì?")
    assert cq.pinpoint == "39/2016/TT-NHNN#dieu:13/khoan:2"


def test_19_pinpoint_broken_docnum():
    cq = go("khoản 8 Điều 8 thông tư 39 /2016/TT- NHNN còn hiệu lực không?")
    assert cq.pinpoint == "39/2016/TT-NHNN#dieu:8/khoan:8"


def test_20_pinpoint_shorthand_resolved_via_corpus():
    cq = go("Điều 8 Thông tư 39 còn hiệu lực không?")
    assert cq.pinpoint == "39/2016/TT-NHNN#dieu:8"


def test_21_no_pinpoint_without_doc():
    cq = go("Điều kiện nào để được vay vốn?")
    assert cq.pinpoint is None


def test_22_pinpoint_khong_dau():
    cq = go("khoan 8 dieu 8 thong tu 39/2016/TT-NHNN da tung co hieu luc chua?")
    assert cq.pinpoint == "39/2016/TT-NHNN#dieu:8/khoan:8" and cq.mode == "history"


def test_23_pinpoint_diem():
    cq = go("điểm a khoản 1 Điều 13 Thông tư 39/2016/TT-NHNN")
    assert cq.pinpoint == "39/2016/TT-NHNN#dieu:13/khoan:1/diem:a"


# ---------------------------------------------------------------------- cohort

def test_24_cohort_signed_exact_date():
    cq = go("Hợp đồng ký ngày 15/03/2021 áp dụng lãi suất nào?")
    assert cq.cohort.contract_signed_before == date(2021, 3, 16)  # ký ngày d ⇒ trước d+1


def test_25_cohort_signed_before():
    cq = go("Hợp đồng ký trước ngày 01/09/2023 thì sao?")
    assert cq.cohort.contract_signed_before == date(2023, 9, 1)


def test_26_cohort_signed_month():
    cq = go("Hợp đồng ký tháng 6/2021 áp dụng quy định nào?")
    assert cq.cohort.contract_signed_before == date(2021, 7, 1)


def test_27_cohort_signed_month_december_rollover():
    cq = go("Hợp đồng ký tháng 12/2021?")
    assert cq.cohort.contract_signed_before == date(2022, 1, 1)


def test_28_cohort_signed_year():
    cq = go("HĐ ký năm 2021 có theo quy định mới không?")
    assert cq.cohort.contract_signed_before == date(2022, 1, 1)


def test_29_cohort_not_amended_with_date():
    cq = go("Hợp đồng chưa sửa đổi từ ngày 01/09/2023 thì áp dụng gì?")
    assert cq.cohort.not_amended_on_or_after == date(2023, 9, 1)


def test_30_cohort_not_amended_no_date_sentinel():
    cq = go("Hợp đồng ký năm 2021 chưa sửa đổi gì thì sao?")
    assert cq.cohort.contract_signed_before == date(2022, 1, 1)
    assert cq.cohort.not_amended_on_or_after == date(1900, 1, 1)  # chưa từng sửa


def test_31_cohort_and_as_of_disentangled():
    """Mốc của CÂU HỎI và mốc của HỢP ĐỒNG không được lẫn nhau (money case)."""
    cq = go("Lãi suất cho vay tại ngày 01/03/2024 cho hợp đồng ký tháng 6/2021 chưa sửa đổi?")
    assert cq.as_of == date(2024, 3, 1)
    assert cq.cohort.contract_signed_before == date(2021, 7, 1)
    assert cq.cohort.not_amended_on_or_after == date(1900, 1, 1)


def test_32_entity_ca_nhan():
    cq = go("Khách hàng cá nhân cần điều kiện gì để vay?")
    assert cq.cohort.entity_class == "ca_nhan"


def test_33_entity_phap_nhan_khong_dau():
    cq = go("khach hang doanh nghiep vay von can gi?")
    assert cq.cohort.entity_class == "phap_nhan"


def test_34_tnhh_target_is_not_borrower_entity():
    """'góp vốn vào công ty TNHH' — công ty là ĐÍCH góp vốn, không phải chủ thể vay."""
    cq = go("Có được vay để góp vốn vào công ty TNHH không?")
    assert cq.cohort.entity_class is None


def test_35_ctx_cohort_override_merges_with_text():
    ctx_cohort = Cohort(entity_class="ca_nhan")
    cq = go("Hợp đồng ký năm 2021 thì sao?", cohort=ctx_cohort)
    assert cq.cohort.entity_class == "ca_nhan"
    assert cq.cohort.contract_signed_before == date(2022, 1, 1)


# ---------------------------------------------------------------------- session & topic

def test_36_audience_from_session_never_from_text():
    cq = go("Tôi là nhân viên ngân hàng, cho hỏi lãi suất?", audience="customer")
    assert cq.audience == "customer"


def test_37_as_known_passthrough():
    k = datetime(2023, 8, 25, tzinfo=timezone.utc)
    cq = compile_question("Điều kiện vay vốn?", SessionCtx(as_known=k), today=TODAY)
    assert cq.as_known == k


def test_38_topic_terms_keep_docnum_drop_stopwords_and_time():
    cq = go("Điều kiện vay vốn năm 2022 theo Thông tư 39/2016/TT-NHNN là gì?")
    assert "39/2016/tt-nhnn" in cq.topic_terms
    assert not any(t in ("là", "gì", "theo") for t in cq.topic_terms)
    assert "2022" not in cq.topic_terms          # đã tiêu thụ thành as_of
    assert any("điều_kiện" in t or "điều" in t for t in cq.topic_terms)


def test_39_khong_dau_full_pipeline():
    cq = go("dieu kien vay von nam 2022 la gi?")
    assert cq.as_of == date(2022, 12, 31) and cq.mode == "point_in_time"


def test_40_never_silently_picks_branch():
    """Compiler KHÔNG đoán cohort khi câu hỏi không nêu — piecewise là việc tầng sau."""
    cq = go("Lãi suất cho vay là bao nhiêu?")
    assert cq.cohort.contract_signed_before is None
    assert cq.cohort.not_amended_on_or_after is None
    assert cq.cohort.entity_class is None


def test_41_strip_diacritics_helper():
    assert strip_diacritics("điều kiện vay vốn đầy đủ") == "dieu kien vay von day du"
