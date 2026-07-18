"""LLM gateway unit tests — HTTP mock bằng respx, không gọi API thật (bản thật: test_llm_live.py)."""
import json

import httpx
import pytest
import respx

from answer import llm_gateway as gw

SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string"}},
    "required": ["verdict"],
    "additionalProperties": False,
}


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture()
def gateway(monkeypatch):
    for var in ("LLM_EXTRACT_MODEL", "LLM_COMPOSE_MODEL", "LLM_JUDGE_MODEL",
                "LLM_EXTRACT_BASE_URL", "LLM_COMPOSE_BASE_URL", "LLM_JUDGE_BASE_URL",
                "LLM_EXTRACT_JSON_MODE", "LLM_COMPOSE_JSON_MODE", "LLM_JUDGE_JSON_MODE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    return gw.LLMGateway()


def test_model_family():
    assert gw.model_family("google/gemini-2.5-flash") == "gemini"
    assert gw.model_family("google/gemini-2.5-flash:free") == "gemini"
    assert gw.model_family("deepseek-chat") == "deepseek"
    assert gw.model_family("anthropic/claude-sonnet-4") == "claude"


def test_default_configs_per_infra_table(gateway):
    ex, jd = gateway.config("extract"), gateway.config("judge")
    assert ex.model == "google/gemini-2.5-flash"
    assert ex.base_url == "https://openrouter.ai/api/v1"
    assert ex.api_key == "sk-or-test"
    assert ex.json_mode == "json_schema"
    assert jd.model == "deepseek-chat"
    assert jd.base_url == "https://api.deepseek.com/v1"
    assert jd.api_key == "sk-ds-test"
    assert jd.json_mode == "json_object"


def test_family_guard_raises_at_boot(monkeypatch):
    monkeypatch.setenv("LLM_JUDGE_MODEL", "google/gemini-2.5-pro")
    monkeypatch.setenv("LLM_JUDGE_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    with pytest.raises(gw.FamilyGuardError):
        gw.LLMGateway()


@respx.mock
def test_extract_uses_openrouter_json_schema_temp0(gateway):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=_chat_response('{"verdict": "ok"}'))
    out = gateway.complete_json("extract", "sys", "user", SCHEMA)
    assert out == {"verdict": "ok"}
    payload = json.loads(route.calls.last.request.content)
    assert payload["model"] == "google/gemini-2.5-flash"
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["schema"] == SCHEMA
    assert route.calls.last.request.headers["Authorization"] == "Bearer sk-or-test"


@respx.mock
def test_judge_uses_deepseek_json_object_with_schema_in_prompt(gateway):
    route = respx.post("https://api.deepseek.com/v1/chat/completions").mock(
        return_value=_chat_response('{"verdict": "entails"}'))
    out = gateway.complete_json("judge", "Anh là judge.", "claim...", SCHEMA)
    assert out == {"verdict": "entails"}
    payload = json.loads(route.calls.last.request.content)
    assert payload["model"] == "deepseek-chat"
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    system = payload["messages"][0]["content"]
    assert "Anh là judge." in system and "JSON" in system and '"verdict"' in system


@respx.mock
def test_invalid_json_retries_once_then_succeeds(gateway):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [_chat_response("đây không phải json"),
                         _chat_response('{"verdict": "ok"}')]
    out = gateway.complete_json("compose", "sys", "user", SCHEMA)
    assert out == {"verdict": "ok"}
    assert route.call_count == 2
    # lần retry phải mang thông điệp sửa lỗi
    second = json.loads(route.calls[1].request.content)
    assert any("JSON" in m["content"] for m in second["messages"] if m["role"] == "user")


@respx.mock
def test_schema_violation_counts_as_invalid(gateway):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [_chat_response('{"wrong_field": 1}'),
                         _chat_response('{"verdict": "ok"}')]
    assert gateway.complete_json("extract", "s", "u", SCHEMA) == {"verdict": "ok"}
    assert route.call_count == 2


@respx.mock
def test_invalid_json_twice_raises(gateway):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [_chat_response("hỏng 1"), _chat_response("hỏng 2")]
    with pytest.raises(gw.LLMGatewayError):
        gateway.complete_json("extract", "s", "u", SCHEMA)
    assert route.call_count == 2


@pytest.mark.parametrize("status", [402, 429])
@respx.mock
def test_openrouter_402_429_falls_back_to_free_variant(gateway, status, caplog):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [httpx.Response(status, json={"error": "quota"}),
                         _chat_response('{"verdict": "ok"}')]
    with caplog.at_level("WARNING", logger="lawstate.llm_gateway"):
        out = gateway.complete_json("compose", "s", "u", SCHEMA)
    assert out == {"verdict": "ok"}
    retry_payload = json.loads(route.calls[1].request.content)
    assert retry_payload["model"] == "google/gemini-2.5-flash:free"
    assert any("fallback" in r.message for r in caplog.records)


@respx.mock
def test_deepseek_429_no_free_fallback_raises(gateway):
    respx.post("https://api.deepseek.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(gw.LLMGatewayError):
        gateway.complete_json("judge", "s", "u", SCHEMA)
