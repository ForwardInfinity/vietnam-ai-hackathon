"""Chụp screenshot các màn hình chính (QA duyệt bằng mắt — deliverable F6).

Tự dựng cả stack cục bộ: seed DB → uvicorn API → 2 app Streamlit → playwright chromium.
Chạy:  uv run python -m tests.ui.capture_screens "postgresql://lawstate:lawstate@localhost:55432/lawstate"
Ảnh ra ./screenshots/*.png
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "screenshots"
DB = sys.argv[1] if len(sys.argv) > 1 else "postgresql://lawstate:lawstate@localhost:55432/lawstate"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_http(url: str, tries=120, ok=(200, 503)):
    for _ in range(tries):
        try:
            if httpx.get(url, timeout=2).status_code in ok:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"không lên được: {url}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    from tests.api.seed_demo import reset, seed

    with psycopg.connect(DB, autocommit=True) as conn:
        reset(conn)
        conn.autocommit = False
        seed(conn)
    print("• DB seeded")

    api_port, chat_port, admin_port = free_port(), free_port(), free_port()
    env = os.environ | {"DATABASE_URL": DB}
    procs = [subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(api_port), "--log-level", "warning"],
        env=env, cwd=ROOT)]
    ui_env = env | {"API_URL": f"http://127.0.0.1:{api_port}",
                    "PUBLIC_API_URL": f"http://127.0.0.1:{api_port}"}
    for app, port in [("ui/chat_app.py", chat_port), ("ui/admin_app.py", admin_port)]:
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", app, "--server.port", str(port),
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            env=ui_env, cwd=ROOT, stdout=subprocess.DEVNULL))
    try:
        wait_http(f"http://127.0.0.1:{api_port}/health")
        wait_http(f"http://127.0.0.1:{chat_port}/_stcore/health", ok=(200,))
        wait_http(f"http://127.0.0.1:{admin_port}/_stcore/health", ok=(200,))
        print("• stack up — chụp…")
        _shoot(chat_port, admin_port)
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except Exception:
                p.kill()


def _shoot(chat_port: int, admin_port: int) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})

        def snap(name: str, full=True, pause=2.5):
            pg.wait_for_timeout(int(pause * 1000))
            pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
            print(f"  ✓ {name}.png")

        def radio(label: str):
            pg.get_by_text(label, exact=True).click()

        A = f"http://127.0.0.1:{admin_port}"
        C = f"http://127.0.0.1:{chat_port}"

        # ---------- ADMIN (ratify TRƯỚC — R-17) ----------
        pg.goto(A, wait_until="networkidle")
        snap("01_admin_queue_per_op", pause=4)

        radio("📦 Duyệt lô (batch)")
        pg.wait_for_timeout(3000)
        pg.get_by_role("button", name=re.compile("Verify")).click()
        snap("02_admin_batch_verify", pause=3.5)
        pg.get_by_role("button", name=re.compile("SIGN")).click()
        snap("03_admin_batch_signed_spotcheck", pause=4)

        radio("▶️ Replay")
        pg.wait_for_timeout(2000)
        pg.get_by_role("button", name=re.compile("Chạy replay")).click()
        snap("04_admin_replay_report", pause=3)

        radio("🗂 Backlog")
        snap("05_admin_backlog", pause=3.5)

        radio("⚔️ Conflicts")
        snap("06_admin_conflict_kanban", pause=3.5)

        radio("📈 Demand log")
        snap("07_admin_demand", pause=3)

        radio("🔔 Notifications")
        snap("08_admin_notifications", pause=3)

        radio("🖋 Sổ ký (INV-6)")
        snap("09_admin_so_ky_inv6", pause=3.5)

        # ---------- CHAT ----------
        pg.goto(C, wait_until="networkidle")
        pg.wait_for_timeout(3000)
        pg.get_by_test_id("stChatInputTextArea").fill("Điều kiện vay vốn phục vụ nhu cầu đời sống hiện nay?")
        pg.keyboard.press("Enter")
        snap("10_chat_answer_employee_4muc", pause=6)

        pg.get_by_text("🙋 Khách hàng").click()
        pg.wait_for_timeout(2000)
        pg.get_by_test_id("stChatInputTextArea").fill("Tôi muốn vay tiêu dùng thì cần điều kiện gì?")
        pg.keyboard.press("Enter")
        snap("11_chat_customer_disclaimer", pause=6)

        # ---------- TIMELINE EXPLORER (beat 3: dải treo + chưa-từng-active) ----------
        pg.goto(f"{C}/Timeline_explorer", wait_until="networkidle")
        pg.wait_for_timeout(3000)
        pg.get_by_test_id("stSelectbox").first.click()
        pg.get_by_text(re.compile("TT10 treo")).click()
        snap("12_timeline_k8_dai_treo_graph", pause=5)

        browser.close()


if __name__ == "__main__":
    main()
