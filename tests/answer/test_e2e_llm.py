"""E2E nhỏ với LLM THẬT (composer + judge) trên snapshot seed — verification nhóm 8.

Chạy thủ công: uv run pytest -m llm_live tests/answer/test_e2e_llm.py -v
(cần OPENROUTER_API_KEY + DEEPSEEK_API_KEY trong .env; không chạy trong CI.)
"""
import os
from datetime import date

import pytest

pytestmark = [pytest.mark.heavy, pytest.mark.llm_live]

if not (os.getenv("OPENROUTER_API_KEY") and os.getenv("DEEPSEEK_API_KEY")):
    pytest.skip("thiếu LLM API key — bỏ e2e llm_live", allow_module_level=True)

from answer.compiler import SessionCtx                       # noqa: E402
from answer.compose import GatewayComposer, build_context_pack  # noqa: E402
from answer.demo_seed import mem_store, T                    # noqa: E402
from answer.judge_soft import judge_claims                   # noqa: E402
from answer.service import answer_question                   # noqa: E402
from retrieval.fuse import hybrid_search                     # noqa: E402

TODAY = date(2026, 7, 18)


def test_e2e_gateway_composer_grounded_answer():
    store = mem_store()
    ans, trace = answer_question(
        "Có được vay vốn để trả nợ khoản vay tại ngân hàng khác không?",
        SessionCtx(audience="employee", as_of=date(2024, 3, 1)),
        store=store, composer=GatewayComposer(), today=TODAY, return_trace=True)
    # composer thật vẫn phải qua gate cứng: B khi pass (judge chưa κ), C khi bịa
    assert ans.tier in ("B", "C")
    if ans.tier == "B":
        assert ans.answer and ans.bases
        # text mới của Đ8 k6 (TT06): điều kiện 'phục vụ kinh doanh' đã bị bỏ
        ctx = "\n".join(trace.context_pack_texts)
        assert "không bao gồm khoản vay nước ngoài" in ctx
    else:
        assert ans.answer == [] and all(b.quote for b in ans.bases)


def test_judge_live_entailment_on_true_and_false_claims():
    from api.schemas import ComposerClaim
    ctx = {"[1]": T["blds468"][1]}
    good = ComposerClaim(id="c1", text="Lãi suất thỏa thuận không được vượt quá 20%/năm "
                                       "của khoản tiền vay, trừ khi luật khác quy định khác [1]",
                         refs=["[1]"])
    bad = ComposerClaim(id="c2", text="Trần lãi suất thỏa thuận là 35%/năm [1]", refs=["[1]"])
    out = judge_claims([good, bad], ctx)
    verdicts = {v["claim_id"]: v["verdict"] for v in out}
    assert verdicts["c1"] == "entails"
    assert verdicts["c2"] in ("fails", "partial")
