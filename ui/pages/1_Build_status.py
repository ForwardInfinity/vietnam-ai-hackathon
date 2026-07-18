"""Trang Build status — đọc build_status.json ở root repo (F1)."""
import json
import os
from datetime import date

import httpx
import streamlit as st

st.set_page_config(page_title="LawState — Build status", page_icon="🛠️", layout="wide")
st.title("🛠️ Build status")

BUILD_STATUS_PATH = os.getenv(
    "BUILD_STATUS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "build_status.json"),
)

STATUS_ICON = {"done": "✅", "in_progress": "🔨", "pending": "⬜"}

try:
    with open(BUILD_STATUS_PATH, encoding="utf-8") as f:
        status = json.load(f)
except Exception as exc:
    st.error(f"Không đọc được build_status.json: {exc}")
    st.stop()

st.caption(f"Cập nhật: {status.get('updated_at', '?')}")

st.subheader("Thành phần")
rows = [
    {
        "": STATUS_ICON.get(c.get("status"), "❔"),
        "Thành phần": c.get("name", ""),
        "Trạng thái": c.get("status", ""),
        "Ghi chú": c.get("note", ""),
    }
    for c in status.get("components", [])
]
st.table(rows)

st.subheader("API")
api_url = os.getenv("API_URL", "http://localhost:8000")
try:
    r = httpx.get(f"{api_url}/health", timeout=5)
    payload = r.json()
    if r.status_code == 200:
        st.success(f"API + DB: {payload}")
    else:
        st.warning(f"API degraded ({r.status_code}): {payload}")
except Exception as exc:
    st.error(f"API không phản hồi: {type(exc).__name__}")

st.caption(f"Hôm nay: {date.today().isoformat()}")
