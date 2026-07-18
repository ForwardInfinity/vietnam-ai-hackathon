"""HTTP client chung cho 2 app Streamlit (chat + admin) — một chỗ giữ base URL,
header role/actor và parse SSE. UI KHÔNG tự nối chuỗi filter audience: mọi quyền
đi bằng header X-Role, backend lọc qua một cửa (INV-12).
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(30.0, read=120.0)


def _headers(role: str, actor: str | None = None) -> dict[str, str]:
    h = {"X-Role": role}
    if actor:
        h["X-Actor"] = actor
    return h


class DownResponse:
    """API không phản hồi → response giả status 0 — UI render lỗi trung thực, không crash."""

    status_code = 0

    def __init__(self, exc: Exception):
        self.text = f"API không phản hồi: {type(exc).__name__}"

    def json(self) -> dict:
        return {"detail": self.text}

    def raise_for_status(self):
        raise RuntimeError(self.text)


def get(path: str, role: str, actor: str | None = None, **params):
    try:
        return httpx.get(f"{API_URL}{path}", headers=_headers(role, actor),
                         params={k: v for k, v in params.items() if v is not None}, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        return DownResponse(exc)


def post(path: str, role: str, actor: str | None = None, json_body: Any = None,
         files: Any = None, data: Any = None):
    try:
        return httpx.post(f"{API_URL}{path}", headers=_headers(role, actor),
                          json=json_body, files=files, data=data, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        return DownResponse(exc)


def ask_sse(payload: dict, role: str) -> Iterator[tuple[str, dict]]:
    """POST /v1/ask dạng SSE → yield (event, data) theo trình tự server gửi."""
    headers = _headers(role) | {"Accept": "text/event-stream"}
    with httpx.stream("POST", f"{API_URL}/v1/ask", json=payload, headers=headers,
                      timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        event: str | None = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: ") and event:
                yield event, json.loads(line[len("data: "):])
                event = None


def err_text(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
        if isinstance(detail, (dict, list)):
            return json.dumps(detail, ensure_ascii=False, indent=2)[:2000]
        return str(detail)
    except Exception:
        return resp.text[:500]
