"""Gọi LLM THẬT mỗi provider — đốt tiền, chạy thủ công:
    uv run pytest -m llm_live -v
Cần OPENROUTER_API_KEY + DEEPSEEK_API_KEY trong env/.env."""
import os

import pytest

from answer.llm_gateway import LLMGateway

pytestmark = [pytest.mark.heavy, pytest.mark.llm_live]

SCHEMA = {
    "type": "object",
    "properties": {"so_dieu": {"type": "integer"}},
    "required": ["so_dieu"],
    "additionalProperties": False,
}


@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="thiếu OPENROUTER_API_KEY")
def test_extract_role_real_call_openrouter():
    out = LLMGateway().complete_json(
        "extract",
        "Anh là bộ trích xuất. Trả về JSON đúng schema.",
        'Trích số điều từ câu: "Sửa đổi Điều 8". Trả {"so_dieu": <int>}.',
        SCHEMA,
    )
    assert out["so_dieu"] == 8


@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="thiếu DEEPSEEK_API_KEY")
def test_judge_role_real_call_deepseek():
    out = LLMGateway().complete_json(
        "judge",
        "Anh là judge entailment. Trả về JSON đúng schema.",
        'Câu "Điều 8 có 5 khoản" nhắc tới điều số mấy? Trả {"so_dieu": <int>}.',
        SCHEMA,
    )
    assert out["so_dieu"] == 8
