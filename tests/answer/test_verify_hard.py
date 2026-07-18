"""Verifier cứng (R-32) + INV-7 — verification nhóm 6."""
from datetime import date

import pytest

from answer.compose import OfflineComposer, build_context_pack
from answer.verify_hard import digit_runs, fuzzy_best_ratio, verify
from api.schemas import ComposerClaim, ComposerOutput

CTX = {
    "[1]": "[1] 39/2016/TT-NHNN | dieu:13 | hiệu lực 01/09/2023 → nay | active\n"
           "Điều 13. Lãi suất cho vay. Tổ chức tín dụng và khách hàng thỏa thuận về lãi suất "
           "cho vay theo cung cầu vốn thị trường. Lãi suất áp dụng không vượt quá 150% lãi "
           "suất cho vay trong hạn. Phạt chậm trả tối đa 10%/năm.",
    "[2]": "[2] 91/2015/QH13 | dieu:468 | hiệu lực 01/01/2017 → nay | active\n"
           "Điều 468. Lãi suất. Lãi suất theo thỏa thuận không được vượt quá 20%/năm của "
           "khoản tiền vay.",
}


def _out(answer_vi, claims):
    return ComposerOutput(answer_vi=answer_vi, claims=claims, bases=[], refusal=None)


def test_pass_verbatim_quote_and_numbers():
    out = _out(
        'Lãi suất theo thỏa thuận, không vượt 150% lãi trong hạn [1].',
        [ComposerClaim(id="c1", text='"Lãi suất áp dụng không vượt quá 150% lãi suất cho vay '
                                     'trong hạn" [1]', refs=["[1]"])])
    v = verify(out, CTX)
    assert v.passed, v.failures


def test_wrong_number_fails_exact():
    out = _out("x [1]", [ComposerClaim(id="c1", text="Phạt chậm trả tối đa 15%/năm [1]",
                                       refs=["[1]"])])
    v = verify(out, CTX)
    assert not v.passed
    assert any(f.kind == "number_mismatch" and "'15'" in f.detail for f in v.failures)


def test_number_full_run_no_substring_cheat():
    """'20' không được ăn theo '2023' — so digit-run đầy đủ."""
    ctx = {"[1]": "Quy định có hiệu lực từ 01/09/2023."}
    out = _out("x [1]", [ComposerClaim(id="c1", text="Trần 20%/năm [1]", refs=["[1]"])])
    assert not verify(out, ctx).passed


def test_number_from_other_ref_not_borrowed():
    # claim trích [1] nhưng con số chỉ có ở [2] → fail (số phải nằm trong ref ĐÃ trích)
    out = _out("x [1]", [ComposerClaim(id="c1", text="Trần lãi 20%/năm [1]", refs=["[1]"])])
    assert not verify(out, CTX).passed


def test_quote_fabricated_fails():
    out = _out("x [1]", [ComposerClaim(
        id="c1", text='"Ngân hàng được phép thu phí phạt không giới hạn theo quyết định '
                      'riêng" [1]', refs=["[1]"])])
    v = verify(out, CTX)
    assert any(f.kind == "quote_mismatch" for f in v.failures)


def test_quote_fuzzy_above_09_passes():
    # lệch nhẹ chính tả/khoảng trắng vẫn ≥ 0.9
    out = _out("x [2]", [ComposerClaim(
        id="c1", text='"Lãi suất theo thoả thuận không được vượt quá 20%/năm của khoản '
                      'tiền vay" [2]', refs=["[2]"])])
    v = verify(out, CTX)
    assert v.passed, v.failures


def test_ref_outside_context_fails():
    out = _out("x [7]", [ComposerClaim(id="c1", text="nội dung [7]", refs=["[7]"])])
    v = verify(out, CTX)
    assert any(f.kind == "ref_outside_context" for f in v.failures)


def test_claim_without_refs_fails():
    out = _out("x", [ComposerClaim(id="c1", text="khẳng định trần trụi", refs=[])])
    assert not verify(out, CTX).passed


def test_tag_in_answer_must_exist():
    out = _out("theo [9] thì được", [])
    assert not verify(out, CTX).passed


def test_question_numbers_whitelisted():
    out = _out("x [1]", [ComposerClaim(
        id="c1", text="Tại 01/03/2024, lãi suất theo thỏa thuận [1]", refs=["[1]"])])
    assert not verify(out, CTX).passed                       # không whitelist → fail
    assert verify(out, CTX, question_numbers=digit_runs("01/03/2024")).passed


def test_fuzzy_best_ratio_bounds():
    assert fuzzy_best_ratio("cho vay", "quy định cho vay ngắn hạn") == 1.0
    assert fuzzy_best_ratio("hoàn toàn khác", "quy định cho vay") < 0.5


def test_offline_composer_output_passes_verifier():
    """Composer tất định phải tự qua cửa của chính hệ (không đặc cách)."""
    from answer.demo_seed import mem_store
    from retrieval.fuse import hybrid_search
    store = mem_store()
    rows = store.candidates(date(2024, 3, 1), {}, ("public", "internal"))
    fused = hybrid_search(rows, "điều kiện vay vốn")
    pack = build_context_pack(fused)
    out = OfflineComposer().compose(None, "điều kiện vay vốn", pack)
    v = verify(out, {e.ref: e.full_text for e in pack})
    assert v.passed, v.failures
