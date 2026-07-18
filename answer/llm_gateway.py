"""LLM gateway — MỘT module cho MỌI call LLM toàn hệ (D-41). ĐÓNG BĂNG theo CONTRACTS.md.

Ba role: extract (op extraction lúc nạp) · compose (soạn văn trả lời) · judge
(entailment khác họ model — D-30). Không file nào khác được gọi HTTP tới LLM.

Config qua env (default = hạ tầng đã verify):
  LLM_{EXTRACT|COMPOSE|JUDGE}_MODEL / _BASE_URL / _API_KEY / _JSON_MODE
  key fallback theo provider: OPENROUTER_API_KEY | DEEPSEEK_API_KEY | LLM_API_KEY

Guard (raise lúc boot, không phải lúc gọi): judge KHÁC HỌ extract/compose — so
prefix tên model (D-30/D-41: cùng họ = tương quan lỗi tối đa, judge vô giá trị).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import jsonschema
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("lawstate.llm_gateway")

Role = Literal["extract", "compose", "judge"]
ROLES: tuple[Role, ...] = ("extract", "compose", "judge")

_DEFAULTS: dict[str, dict[str, str]] = {
    # extract/compose MỘT họ (gemini qua OpenRouter); judge KHÁC họ (deepseek trực tiếp)
    "extract": {"model": "google/gemini-2.5-flash",
                "base_url": "https://openrouter.ai/api/v1", "json_mode": "json_schema"},
    "compose": {"model": "google/gemini-2.5-flash",
                "base_url": "https://openrouter.ai/api/v1", "json_mode": "json_schema"},
    # deepseek-chat chưa hỗ trợ json_schema strict → json_object + schema nhúng system prompt
    "judge":   {"model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1", "json_mode": "json_object"},
}


class LLMGatewayError(RuntimeError):
    """Lỗi gateway sau khi đã hết retry — caller quyết định thoái lui tier."""


class FamilyGuardError(LLMGatewayError):
    """Judge cùng họ model với extract/compose — cấu hình vi phạm D-30/D-41."""


def model_family(model: str) -> str:
    """Họ model = token đầu của tên model (bỏ org prefix và suffix ':free').
    'google/gemini-2.5-flash' → 'gemini' · 'deepseek-chat' → 'deepseek'."""
    name = model.split("/")[-1].split(":")[0]
    return name.split("-")[0].lower()


@dataclass(frozen=True)
class RoleConfig:
    model: str
    base_url: str
    api_key: str
    json_mode: Literal["json_schema", "json_object"]


def _resolve_key(base_url: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if "openrouter" in base_url:
        return os.getenv("OPENROUTER_API_KEY", "")
    if "deepseek" in base_url:
        return os.getenv("DEEPSEEK_API_KEY", "")
    return os.getenv("LLM_API_KEY", "")


def role_config(role: Role) -> RoleConfig:
    d = _DEFAULTS[role]
    prefix = f"LLM_{role.upper()}"
    base_url = os.getenv(f"{prefix}_BASE_URL", d["base_url"]).rstrip("/")
    json_mode = os.getenv(f"{prefix}_JSON_MODE", d["json_mode"])
    if json_mode not in ("json_schema", "json_object"):
        raise LLMGatewayError(f"{prefix}_JSON_MODE không hợp lệ: {json_mode}")
    return RoleConfig(
        model=os.getenv(f"{prefix}_MODEL", d["model"]),
        base_url=base_url,
        api_key=_resolve_key(base_url, os.getenv(f"{prefix}_API_KEY")),
        json_mode=json_mode,  # type: ignore[arg-type]
    )


def check_family_guard(configs: dict[Role, RoleConfig] | None = None) -> None:
    """Gọi lúc boot (api lifespan / gateway init). Vi phạm → raise, không chạy tiếp."""
    cfg = configs or {r: role_config(r) for r in ROLES}
    judge_fam = model_family(cfg["judge"].model)
    for r in ("extract", "compose"):
        fam = model_family(cfg[r].model)
        if fam == judge_fam:
            raise FamilyGuardError(
                f"Judge ('{cfg['judge'].model}' họ '{judge_fam}') CÙNG HỌ với "
                f"{r} ('{cfg[r].model}' họ '{fam}') — vi phạm D-30/D-41: "
                "judge phải khác họ model để tránh tương quan lỗi."
            )


class LLMGateway:
    """Sync gateway; temperature 0 + JSON schema mode; retry 1 lần khi JSON không hợp lệ;
    402/429 từ OpenRouter → fallback ':free' variant + log warning."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._configs: dict[Role, RoleConfig] = {r: role_config(r) for r in ROLES}
        check_family_guard(self._configs)
        self._client = httpx.Client(timeout=timeout)

    def config(self, role: Role) -> RoleConfig:
        return self._configs[role]

    def complete_json(self, role: Role, system: str, user: str,
                      schema: dict[str, Any]) -> dict[str, Any]:
        """Một call LLM → dict đã parse + validate theo `schema` (JSON Schema).
        Invalid JSON/schema → retry đúng 1 lần kèm thông điệp sửa lỗi → LLMGatewayError."""
        cfg = self._configs[role]
        messages = [{"role": "system", "content": self._system_content(cfg, system, schema)},
                    {"role": "user", "content": user}]
        last_err = ""
        for attempt in (1, 2):
            raw = self._post_chat(cfg, messages, schema)
            try:
                parsed = json.loads(raw)
                jsonschema.validate(parsed, schema)
                return parsed
            except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                logger.warning("llm_gateway role=%s attempt=%d JSON không hợp lệ: %s",
                               role, attempt, last_err[:300])
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content":
                        "Output trên KHÔNG phải JSON hợp lệ theo schema đã yêu cầu "
                        f"({last_err[:500]}). Trả về DUY NHẤT một JSON object hợp lệ, "
                        "không markdown, không giải thích."},
                ]
        raise LLMGatewayError(
            f"role={role} model={cfg.model}: JSON không hợp lệ sau 2 lần thử — {last_err[:500]}")

    # ------------------------------------------------------------------ intern

    @staticmethod
    def _system_content(cfg: RoleConfig, system: str, schema: dict[str, Any]) -> str:
        if cfg.json_mode == "json_object":
            # provider chỉ có json_object (DeepSeek): nhúng schema vào system prompt;
            # từ 'json' bắt buộc phải xuất hiện trong prompt theo API DeepSeek
            return (f"{system}\n\nTrả về DUY NHẤT một JSON object hợp lệ theo đúng "
                    f"JSON Schema sau, không thêm chữ nào khác:\n{json.dumps(schema, ensure_ascii=False)}")
        return system

    @staticmethod
    def _response_format(cfg: RoleConfig, schema: dict[str, Any]) -> dict[str, Any]:
        if cfg.json_mode == "json_schema":
            return {"type": "json_schema",
                    "json_schema": {"name": "output", "strict": True, "schema": schema}}
        return {"type": "json_object"}

    def _post_chat(self, cfg: RoleConfig, messages: list[dict[str, str]],
                   schema: dict[str, Any]) -> str:
        """POST /chat/completions; 402/429 OpenRouter → thử lại với ':free' variant."""
        resp = self._send(cfg, cfg.model, messages, schema)
        if (resp.status_code in (402, 429) and "openrouter" in cfg.base_url
                and not cfg.model.endswith(":free")):
            free_model = f"{cfg.model}:free"
            logger.warning("llm_gateway: HTTP %d từ OpenRouter cho model=%s — fallback %s",
                           resp.status_code, cfg.model, free_model)
            resp = self._send(cfg, free_model, messages, schema)
        if resp.status_code >= 400:
            raise LLMGatewayError(
                f"model={cfg.model} HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMGatewayError(f"response thiếu choices/message: {exc}") from exc

    def _send(self, cfg: RoleConfig, model: str, messages: list[dict[str, str]],
              schema: dict[str, Any]) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "response_format": self._response_format(cfg, schema),
        }
        return self._client.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
        )


_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    """Singleton lazy — mọi module dùng LLM lấy gateway qua đây, không tự tạo client."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
