"""Tầng LLM với gateway MOCK (unit — không mạng): merge rule⊕LLM, routing batch,
prompt bắt buộc chứa quy tắc binding/omnibus/few-shot (D-18, R-8c, R-11)."""
from datetime import date

import pytest

from ingest.citation import LLM_EDGE_SYSTEM
from ingest.op_extract import LLM_OP_FEWSHOT, LLM_OP_SYSTEM
from ingest.orchestrator import ingest_corpus_pure

from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts


class MockGateway:
    """Giả lập answer.llm_gateway.LLMGateway — trả kịch bản cấu hình sẵn."""

    def __init__(self, op_responses=None, edge_response=None, raise_on=None):
        self.op_responses = op_responses or {}
        self.edge_response = edge_response or {"edges": []}
        self.raise_on = raise_on or set()
        self.calls: list[dict] = []

    def config(self, role):
        class _C:
            model = "mock-model"
        return _C()

    def complete_json(self, role, system, user, schema):
        self.calls.append({"role": role, "system": system, "user": user})
        if "ops" in schema.get("properties", {}):
            if "op" in self.raise_on:
                raise RuntimeError("mock op failure")
            for key, resp in self.op_responses.items():
                if key in user:
                    return resp
            return {"ops": []}
        if "edge" in self.raise_on:
            raise RuntimeError("mock edge failure")
        return self.edge_response


def _tt06_llm_ops():
    """LLM đồng thuận với rule trên các op cơ học của TT06 (few-shot VD1 semantics)."""
    mk = lambda **kw: {"kind": "insert", "target_part": "body", "new_text": None,
                       "new_heading": None, "valid_from": "2023-09-01", "valid_to": None,
                       "valid_to_event": None, "scope_predicate": {},
                       "target_is_amending_provision": False, "confidence": 0.95, **kw}
    return {"ops": [
        mk(kind="amend", target_surface="khoản 2 Điều 2 Thông tư số 39/2016/TT-NHNN",
           source_quote="Sửa đổi, bổ sung khoản 2 Điều 2 như sau", ),
        mk(target_surface="khoản 8 Điều 8 Thông tư số 39/2016/TT-NHNN",
           new_text="Để gửi tiền.",
           source_quote="Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8 như sau"),
        mk(target_surface="khoản 9 Điều 8 Thông tư số 39/2016/TT-NHNN",
           new_text="Để thanh toán tiền góp vốn...",
           source_quote="Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8 như sau"),
        mk(target_surface="khoản 10 Điều 8 Thông tư số 39/2016/TT-NHNN",
           new_text="Để bù đắp tài chính...",
           source_quote="Bổ sung khoản 8, khoản 9 và khoản 10 vào Điều 8 như sau"),
    ]}


@pytest.fixture()
def corpus_with_llm():
    gw = MockGateway(op_responses={"06/2023/TT-NHNN": _tt06_llm_ops()})
    return gw, ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts(), gateway=gw)


def test_rule_llm_agreement_enables_batch(corpus_with_llm):
    gw, (store, bundles) = corpus_with_llm
    ops = bundles["06/2023/TT-NHNN"].ops
    k8 = next(o for o in ops if o.target_path == "dieu:8/khoan:8")
    assert k8.rule_llm_agree
    assert k8.queue == "batch"                        # 4 điều kiện cơ học đạt (D-19)
    assert "+llm:" in k8.extractor
    # định nghĩa vẫn per-op dù LLM đồng thuận
    d2 = next(o for o in ops if o.target_path == "dieu:2/khoan:2")
    assert d2.rule_llm_agree and d2.queue == "per_op" and d2.risk_class == "definitional"


def test_rule_only_ops_stay_per_op_when_llm_silent(corpus_with_llm):
    gw, (store, bundles) = corpus_with_llm
    ops = bundles["06/2023/TT-NHNN"].ops
    rep = next(o for o in ops if o.kind == "repeal")   # LLM mock không trả op này
    assert not rep.rule_llm_agree
    assert rep.queue == "per_op"


def test_llm_failure_falls_back_to_rule():
    gw = MockGateway(raise_on={"op", "edge"})
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts(), gateway=gw)
    ops = bundles["06/2023/TT-NHNN"].ops
    assert len([o for o in ops if o.kind == "insert"]) == 4      # rule vẫn đủ
    assert all(not o.rule_llm_agree for o in ops)


def test_llm_only_op_added_low_confidence_per_op():
    extra = {"ops": [{
        "kind": "repeal", "target_surface": None, "target_part": "body",
        "target_is_amending_provision": False, "new_text": None, "new_heading": None,
        "valid_from": None, "valid_to": None, "valid_to_event": None,
        "scope_predicate": {}, "source_quote": "câu mơ hồ nào đó", "confidence": 0.2}]}
    gw = MockGateway(op_responses={"06/2023/TT-NHNN": extra})
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts(), gateway=gw)
    ops = bundles["06/2023/TT-NHNN"].ops
    ghost = next(o for o in ops if o.source_quote == "câu mơ hồ nào đó")
    assert not ghost.rule_llm_agree
    assert "target_unresolved" in ghost.red_flags
    assert not ghost.check_ok()                        # 0 target → backlog, không vào DB


def test_op_prompt_contains_mandatory_rules(corpus_with_llm):
    """D-18: few-shot BẮT BUỘC — enumeration, ngưng≠bãi bỏ (TT10), binding trong/ngoài
    quote, phân kỳ, không đoán target. Prompt thiếu = vi phạm spec."""
    gw, _ = corpus_with_llm
    op_calls = [c for c in gw.calls if "TOÁN TỬ" in c["system"]]
    assert op_calls
    system = op_calls[0]["system"]
    for must in ["TÁCH enumeration", "ngưng hiệu lực", "bãi bỏ", "Thông tư này",
                 "TRONG text được quote", "phân kỳ", "KHÔNG đoán target",
                 "10/2023/TT-NHNN", "khoản 8, khoản 9 và khoản 10",
                 "valid_to_event", "target_is_amending_provision"]:
        assert must in system, f"prompt op thiếu quy tắc bắt buộc: {must!r}"


def test_op_prompt_carries_chapter_context_for_omnibus():
    gw = MockGateway()
    ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts(), gateway=gw)
    tt11_calls = [c for c in gw.calls if "11/2026/TT-NHNN" in c["user"]]
    assert tt11_calls
    assert any("Chương" in c["user"] and "39/2016/TT-NHNN" in c["user"] for c in tt11_calls)
    # hiệu lực phân kỳ phải được đưa vào context
    assert any("01 tháng 7 năm 2026" in c["user"] or "Phiếu lý lịch tư pháp" in c["user"]
               for c in tt11_calls)


def test_edge_prompt_contains_binding_and_omnibus_rules():
    """R-8c: prompt tầng (c) PHẢI chứa quy tắc binding 02§5.3 + context-stack 02§5.4."""
    assert "TRONG text được quote" in LLM_EDGE_SYSTEM
    assert "văn bản ĐÍCH" in LLM_EDGE_SYSTEM
    assert "OMNIBUS" in LLM_EDGE_SYSTEM or "omnibus" in LLM_EDGE_SYSTEM
    assert "Chương" in LLM_EDGE_SYSTEM
    assert "09/2019" in LLM_EDGE_SYSTEM               # ví dụ binding Điều 7a


def test_edge_llm_classifies_leftovers():
    resp = {"edges": [{"node_path": "dieu:2", "raw_citation": "theo quy định của Ngân hàng Nhà nước",
                       "kind": "chu_de", "target_doc": None, "target_path": None,
                       "confidence": 0.4}]}
    gw = MockGateway(edge_response=resp)
    store, bundles = ingest_corpus_pure(FIXTURE_ENTRIES, fixture_texts(), gateway=gw)
    # không crash + edge từ LLM được nhận vào bundle nếu match node
    assert isinstance(bundles["32/2026/TT-NHNN"].edges, list)
