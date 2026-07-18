"""UI smoke qua streamlit AppTest (không cần browser).

Lane smoke (not heavy): API tắt → hai app render trạng thái lỗi TRUNG THỰC, không exception.
Lane heavy: uvicorn thật + DB seed → admin console hiện queue/backlog thật, chat render 4 mục.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest
from streamlit.testing.v1 import AppTest

TIMEOUT = 12  # giây cho mỗi lần chạy script


def _dead_api(monkeypatch):
    monkeypatch.setenv("API_URL", "http://127.0.0.1:59998")  # cổng chết — fail nhanh
    # ui.api_client đọc API_URL lúc import — ép reload để nhận env mới
    for mod in list(sys.modules):
        if mod.startswith("ui"):
            sys.modules.pop(mod)


def test_chat_app_renders_without_api(monkeypatch):
    _dead_api(monkeypatch)
    at = AppTest.from_file("ui/chat_app.py", default_timeout=TIMEOUT).run()
    assert not at.exception, at.exception
    # shell FR-1/FR-7 phải có: persona radio + as-of date input
    assert at.radio and at.date_input


def test_chat_app_ask_flow_degrades_honestly(monkeypatch):
    _dead_api(monkeypatch)
    at = AppTest.from_file("ui/chat_app.py", default_timeout=TIMEOUT).run()
    at.chat_input[0].set_value("Điều kiện vay vốn?").run()
    assert not at.exception
    # API chết → thông điệp lỗi trung thực, không giả vờ có câu trả lời
    assert any("Không gọi được API" in str(e.value) for e in at.error), \
        [str(e.value) for e in at.error]


def test_admin_app_renders_all_sections_without_api(monkeypatch):
    _dead_api(monkeypatch)
    at = AppTest.from_file("ui/admin_app.py", default_timeout=TIMEOUT).run()
    assert not at.exception, at.exception
    sections = at.radio[0].options
    assert len(sections) == 9  # FR-9..14 + ingest + replay + sổ ký
    for sec in sections:
        at.radio[0].set_value(sec).run()
        assert not at.exception, f"section {sec}: {at.exception}"


# ---------------------------------------------------------------------------
# Heavy: API thật + DB seed
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_api():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL chưa set — bỏ heavy UI tests")
    psycopg = pytest.importorskip("psycopg")
    from tests.api.seed_demo import reset, seed

    with psycopg.connect(url, autocommit=True) as conn:
        reset(conn)
        conn.autocommit = False
        seed(conn)

    port = _free_port()
    env = os.environ | {"DATABASE_URL": url}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port), "--log-level", "warning"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    import httpx

    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(base + "/health", timeout=1).status_code in (200, 503):
                    break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("uvicorn không lên được")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.heavy
def test_admin_console_real_content(live_api, monkeypatch):
    monkeypatch.setenv("API_URL", live_api)
    for mod in list(sys.modules):
        if mod.startswith("ui"):
            sys.modules.pop(mod)
    at = AppTest.from_file("ui/admin_app.py", default_timeout=30).run()
    assert not at.exception
    # queue per-op: có metric + expander op với source_quote
    assert any("per-op" in str(m.label) for m in at.metric)
    body = "\n".join(str(e.value) for e in list(at.info) + list(at.markdown))
    assert "source_quote" in body or "Nguyên văn căn cứ" in body

    # backlog section hiện counts thật
    at.radio[0].set_value("🗂 Backlog").run()
    assert not at.exception
    vals = {str(m.label): str(m.value) for m in at.metric}
    assert vals.get("Sự kiện treo mở") == "1"

    # sổ ký INV-6
    at.radio[0].set_value("🖋 Sổ ký (INV-6)").run()
    assert not at.exception


@pytest.mark.heavy
def test_chat_app_full_answer_render(live_api, monkeypatch):
    monkeypatch.setenv("API_URL", live_api)
    for mod in list(sys.modules):
        if mod.startswith("ui"):
            sys.modules.pop(mod)
    at = AppTest.from_file("ui/chat_app.py", default_timeout=30).run()
    at.chat_input[0].set_value("Điều kiện vay vốn hiện nay?").run()
    assert not at.exception
    md = "\n".join(str(m.value) for m in at.markdown)
    # 4 mục cố định
    for section in ("Trả lời", "Căn cứ", "Xung đột", "Thay đổi sắp hiệu lực"):
        assert section in md, f"thiếu mục {section}"
    # stub F5 chưa merge → Tier D trung thực + run_id từ seed được pin trên tem
    assert "Tier D" in md
