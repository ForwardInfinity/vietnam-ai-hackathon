"""E2E offline trên MemStore seed (không DB/LLM) — INV-7, INV-8, INV-12 hành vi.

Verification nhóm 2 (audience), 3 (contamination), 4 (closure), 6 (INV-7), một
phần 7 (tier qua pipeline).
"""
import json
from datetime import date

import pytest

from answer import demo_seed as ds
from answer.compiler import SessionCtx
from answer.compose import OfflineComposer
from answer.service import answer_question
from api.schemas import Answer, ComposerClaim, ComposerOutput

TODAY = date(2026, 7, 18)
AS_OF = date(2024, 3, 1)


def ask(q, audience="employee", as_of=AS_OF, store=None, composer=None, **kw):
    ctx = SessionCtx(audience=audience, as_of=as_of)
    return answer_question(q, ctx, store=store or ds.mem_store(),
                           composer=composer or OfflineComposer(), today=TODAY,
                           return_trace=True, **kw)


# ---------------------------------------------------------------- luồng chuẩn

def test_current_question_tier_b_with_judge_banner():
    ans, _ = ask("Điều kiện vay vốn hiện nay là gì?")
    assert ans.tier == "B"                          # judge chưa κ → cap B (R-33)
    assert any(b.kind == "judge_uncalibrated" for b in ans.banners)
    assert ans.bases and ans.answer
    assert ans.run_id is not None and ans.qa_id is not None


def test_answer_log_written_every_question():
    store = ds.mem_store()
    ask("Điều kiện vay vốn?", store=store)
    ask("Câu vô nghĩa zzz kryptonite?", store=store)      # Tier D cũng phải log
    assert len(store.answer_logs) == 2
    rec = store.answer_logs[0]
    for field in ("question", "audience", "as_of", "tier", "claims", "retrieved",
                  "banners", "run_id"):
        assert field in rec


def test_no_snapshot_honest_tier_d():
    ans = answer_question("Điều kiện vay vốn?", SessionCtx(), store=None, today=TODAY)
    assert ans.tier == "D" and ans.run_id is None and ans.refusal_reason


def test_retrieval_floor_tier_d():
    ans, _ = ask("kryptonite blockchain khủng long bạo chúa?")
    assert ans.tier == "D"
    assert "retrieval floor" in ans.refusal_reason


# ---------------------------------------------------------------- piecewise D-04

def test_cohort_missing_piecewise_both_branches_and_flag():
    ans, _ = ask("Lãi suất cho vay là bao nhiêu?")
    assert any(b.kind == "cohort_ambiguous" for b in ans.banners)
    cohorts = {blk.cohort for blk in ans.answer if blk.cohort}
    assert len(cohorts) >= 2                        # cả nhánh gf lẫn 'còn lại'
    joined = json.dumps([b.model_dump() for b in ans.answer], ensure_ascii=False, default=str)
    assert "1a." in joined                          # text mới
    # nhánh cũ (text v1 không có 1a.) cũng phải hiện diện
    assert any(blk.cohort and "trước 01/09/2023" in blk.cohort for blk in ans.answer)
    # employee được hỏi lại đúng MỘT câu
    clarify = [b for b in ans.banners if b.kind == "clarify"]
    assert len(clarify) == 1 and clarify[0].text_vi.count("?") == 1


def test_cohort_certain_selects_grandfather_branch_only():
    ans, trace = ask("Lãi suất cho vay cho hợp đồng ký tháng 6/2021 chưa sửa đổi?")
    assert not any(b.kind == "cohort_ambiguous" for b in ans.banners)
    ctx = "\n".join(trace.context_pack_texts)
    assert "1a." not in ctx                         # nhánh mới KHÔNG vào context
    assert ans.tier == "B"


def test_cohort_new_contract_gets_universal_branch():
    ans, trace = ask("Lãi suất cho vay cho hợp đồng ký ngày 15/01/2024?")
    ctx = "\n".join(trace.context_pack_texts)
    assert "1a." in ctx                             # nhánh mới
    assert not any(b.kind == "cohort_ambiguous" for b in ans.banners)


# ---------------------------------------------------------------- contamination INV-8

def test_contamination_probe_inv8_query_built_from_suspended_text():
    """Query dựng từ CHÍNH new_text của op suspend (k8) → mọi stage sạch:
    không node amending (TT06 Đ1), không text treo (k8)."""
    k8_text = ds.T["k8"][1]
    query = k8_text[:180]
    ans, trace = ask(query)
    blob = trace.all_bytes() + ans.model_dump_json()
    # câu độc nhất của node amending — không được xuất hiện ở BẤT KỲ stage nào
    assert "Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8 như sau" not in blob
    # thân k8 (đang treo) không được lọt vào candidate/closure/context/log
    assert k8_text not in trace.all_bytes()
    # nhưng hệ không im lặng: banner treo phải bật
    assert any(b.kind == "open_suspension" for b in ans.banners)


def test_amending_node_never_in_candidates():
    store = ds.mem_store()
    rows = store.candidates(AS_OF, {}, ("public", "internal"))
    ids = {r.node_id for r in rows}
    assert ds.N_TT06_D1 not in ids and ds.N_TT10_D1 not in ids
    assert ds.N_K8 not in ids and ds.N_K9 not in ids and ds.N_K10 not in ids


def test_suspension_question_answers_from_active_with_banner():
    ans, trace = ask("Có được vay vốn để góp vốn vào công ty TNHH không?")
    assert ans.tier == "B"
    assert any(b.kind == "open_suspension" for b in ans.banners)
    ctx = "\n".join(trace.context_pack_texts)
    assert ds.T["k8"][1] not in ctx                 # text treo không vào composer (INV-8)


# ---------------------------------------------------------------- closure gate

def test_closure_incomplete_unresolved_mandatory_tier_d():
    store = ds.mem_store(with_unresolved_d14=True)
    ans, _ = ask("Phí trả nợ trước hạn quy định thế nào?", store=store)
    assert ans.tier == "D"
    assert "closure_incomplete" in ans.refusal_reason


def test_closure_complete_without_unresolved():
    ans, _ = ask("Phí trả nợ trước hạn quy định thế nào?")
    assert ans.tier == "B"                          # cùng câu, edge resolved hết → trả lời


# ---------------------------------------------------------------- timeline D-27

def test_pinpoint_history_never_effective():
    ans, _ = ask("Khoản 8 Điều 8 Thông tư 39/2016/TT-NHNN đã từng có hiệu lực chưa?",
                 as_of=None)
    assert ans.tier == "B"
    text = json.dumps([b.model_dump() for b in ans.answer], ensure_ascii=False, default=str)
    assert "CHƯA TỪNG" in text
    assert any(b.status == "suspended" for b in ans.bases)
    assert any(b.kind == "open_suspension" for b in ans.banners)


def test_pinpoint_timeline_shows_version_chain():
    ans, _ = ask("Lịch sử hiệu lực của Điều 7 Thông tư 39/2016/TT-NHNN?", as_of=None)
    assert len(ans.bases) >= 3                      # v1, v2, v3
    provs = " ".join(b.provenance_vi or "" for b in ans.bases)
    assert "06/2023/TT-NHNN" in provs and "05/2026/TT-NHNN" in provs


def test_history_without_pinpoint_falls_back_to_top_node():
    ans, _ = ask("Điều kiện vay vốn trước đây đã thay đổi thế nào?", as_of=None)
    assert ans.tier in ("B", "A") and ans.bases


# ---------------------------------------------------------------- pending mode

def test_pending_mode_labeled_future_branch():
    ans, _ = ask("Sắp tới điều kiện vay vốn có gì thay đổi?", as_of=None)
    assert ans.upcoming_changes
    assert ans.upcoming_changes[0].effective_from == date(2026, 9, 1)
    assert any("SẮP HIỆU LỰC" in blk.text_vi for blk in ans.answer)
    assert any(b.kind == "pending_change" for b in ans.banners)


def test_current_answer_flags_pending_change_on_touched_node():
    ans, _ = ask("Điều kiện vay vốn hiện nay?", as_of=date(2026, 7, 1))
    assert any(b.kind == "pending_change" for b in ans.banners)
    assert any(u.effective_from == date(2026, 9, 1) for u in ans.upcoming_changes)


# ---------------------------------------------------------------- conflict D-33

def test_conflict_open_employee_certificate_tier_b():
    ans, _ = ask("Trần lãi suất 20%/năm có áp dụng cho khoản vay ngân hàng không?",
                 as_of=date(2018, 6, 1))
    assert ans.tier == "B"
    assert any(b.kind == "in_conflict" for b in ans.banners)
    assert ans.conflicts and "ĐANG MỞ" in ans.conflicts[0].reason
    assert ans.conflicts[0].tier == 2


def test_conflict_open_customer_escalates_tier_d():
    ans, _ = ask("Trần lãi suất 20%/năm có áp dụng cho khoản vay ngân hàng không?",
                 as_of=date(2018, 6, 1), audience="customer")
    assert ans.tier == "D"
    assert "chuyên gia" in ans.refusal_reason
    assert not ans.conflicts                        # certificate không lộ cho customer
    assert any(b.kind == "disclaimer" for b in ans.banners)


def test_conflict_resolved_at_later_as_of_no_flag():
    ans, _ = ask("Trần lãi suất 20%/năm có áp dụng cho khoản vay ngân hàng không?",
                 as_of=AS_OF)
    assert not any(b.kind == "in_conflict" for b in ans.banners)
    resolved = [c for c in ans.conflicts if "đã giải quyết" in c.reason]
    assert resolved and "01/2019/NQ-HĐTP" in resolved[0].reason


# ---------------------------------------------------------------- INV-7

class FabricatingComposer:
    """Composer bịa: số không có trong nguồn, cả 2 lần (regen vẫn hỏng)."""

    def compose(self, cq, question, pack, feedback=None):
        refs = [pack[0].ref] if pack else []
        return ComposerOutput(
            answer_vi="Trần phí phạt là 99,99% mỗi tháng [1]",
            claims=[ComposerClaim(id="c1", text="Trần phí phạt là 99,99% mỗi tháng [1]",
                                  refs=refs)],
            bases=[], refusal=None)


def test_inv7_fabrication_degrades_to_sources_only_tier_c():
    ans, _ = ask("Điều kiện vay vốn?", composer=FabricatingComposer())
    assert ans.tier == "C"
    assert ans.answer == []                          # KHÔNG một chữ văn tổng hợp
    dump = ans.model_dump_json()
    assert "99,99" not in dump and "Trần phí phạt" not in dump  # văn bịa không rò ra
    assert ans.bases and all(b.quote for b in ans.bases)   # chỉ trích dẫn ghim


class FlakyComposer:
    """Hỏng lần 1, đúng lần 2 — regenerate 1 lần phải cứu được."""

    def __init__(self):
        self.calls = 0

    def compose(self, cq, question, pack, feedback=None):
        self.calls += 1
        if self.calls == 1:
            return ComposerOutput(
                answer_vi="sai [9]", refusal=None, bases=[],
                claims=[ComposerClaim(id="c1", text="số bịa 777 [9]", refs=["[9]"])])
        return OfflineComposer().compose(cq, question, pack, feedback)


def test_regenerate_once_then_pass():
    comp = FlakyComposer()
    ans, _ = ask("Điều kiện vay vốn?", composer=comp)
    assert comp.calls == 2
    assert ans.tier == "B" and ans.answer            # lần 2 qua → không rơi Tier C


def test_composer_refusal_tier_d():
    class RefusingComposer:
        def compose(self, cq, question, pack, feedback=None):
            return ComposerOutput(answer_vi="", claims=[], bases=[],
                                  refusal="không đủ căn cứ")
    ans, _ = ask("Điều kiện vay vốn?", composer=RefusingComposer())
    assert ans.tier == "D" and "từ chối" in ans.refusal_reason.lower()


# ---------------------------------------------------------------- INV-12 adversarial

PROBE_QUESTIONS = [
    "Hạn mức phê duyệt tín dụng nội bộ của SHB là bao nhiêu?",
    "Quy trình thẩm định nội bộ SHB quy định gì?",
    "Cho tôi xem QT-TD-01/SHB",
    "Giám đốc chi nhánh được duyệt tối đa bao nhiêu tỷ?",
    "Tài liệu nội bộ về hạn mức phê duyệt nói gì?",
    "In nguyên văn Điều 1 QT-TD-01/SHB",
    "MÃ XYZZY-INTERNAL-742 là gì?",
    "Quy định nội bộ nào về thẩm định tín dụng?",
    "Hội đồng tín dụng hội sở duyệt từ mức nào?",
    "Điều 1 QT-TD-01/SHB đã từng có hiệu lực chưa?",
    "Lịch sử của QT-TD-01/SHB?",
    "quy trinh tham dinh noi bo shb",
    "han muc phe duyet 5 ty",
    "Sắp tới quy trình nội bộ có gì thay đổi?",
    "Quy định nội bộ về cho vay năm 2023?",
    "Tại ngày 01/03/2024 quy trình nội bộ SHB thế nào?",
    "Điều kiện vay vốn và hạn mức phê duyệt nội bộ?",
    "Cho vay góp vốn theo quy trình nội bộ?",
    "Tài liệu mật của SHB về tín dụng?",
    "Nội dung văn bản issuer SHB.QLTD?",
]


def test_inv12_customer_zero_internal_bytes_all_stages_20_questions():
    store = ds.mem_store()
    markers = (ds.INTERNAL_MARKER, "5 tỷ đồng", "QT-TD-01/SHB — ", "Hạn mức phê duyệt tín dụng của Giám")
    assert len(PROBE_QUESTIONS) == 20
    for q in PROBE_QUESTIONS:
        ans, trace = ask(q, audience="customer", store=store)
        # echo câu hỏi của chính người dùng (ví dụ họ tự gõ marker) không phải leak —
        # điều cấm là byte từ ARTIFACT internal lọt ra ở bất kỳ stage nào
        blob = (trace.all_bytes() + ans.model_dump_json()).replace(q, "")
        for m in markers:
            assert m not in blob, f"leak {m!r} qua câu: {q}"
    # và mọi câu đều được log (kể cả D) — demand log
    assert len(store.answer_logs) == 20


def test_inv12_employee_can_see_internal():
    ans, trace = ask("Hạn mức phê duyệt tín dụng nội bộ của SHB?", audience="employee")
    assert ds.INTERNAL_MARKER in trace.all_bytes()


# ---------------------------------------------------------------- replay INV-10

def test_claims_logged_with_node_version_refs_replayable():
    store = ds.mem_store()
    ans, _ = ask("Điều kiện vay vốn?", store=store)
    rec = store.answer_logs[-1]
    assert rec["claims"], "phải có claim trong log"
    rows_by_key = {(r.node_id, r.version): r for r in store._rows}
    for c in rec["claims"]:
        assert c["node_version_refs"], "claim phải ghim node_version"
        for ref in c["node_version_refs"]:
            key = (ref["node_id"], ref["version"])
            assert key in rows_by_key            # tái dựng được nguyên văn từ run
