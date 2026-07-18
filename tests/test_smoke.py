"""Smoke F1: API stub trung thực + build_status hợp lệ. Không cần Docker/DB/model."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

ROOT = Path(__file__).resolve().parent.parent


def test_health_responds_with_db_field():
    # Không có DB trong smoke: chấp nhận 200 (db ok) hoặc 503 (degraded) — schema phải đúng
    r = client.get("/health")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "db" in body


def test_ask_stub_returns_honest_tier_d():
    r = client.post("/v1/ask", json={"question": "Điều kiện vay vốn hiện nay?"})
    assert r.status_code == 200
    ans = r.json()
    # Đủ 4 mục cố định + metadata
    for key in ("answer", "bases", "conflicts", "upcoming_changes",
                "banners", "coverage", "tier", "audience", "as_of", "run_id"):
        assert key in ans, f"thiếu field {key}"
    # Stub trung thực: Tier D, không căn cứ, không run, coverage rỗng, có lý do từ chối
    assert ans["tier"] == "D"
    assert ans["run_id"] is None
    assert ans["answer"] == [] and ans["bases"] == []
    assert ans["coverage"] == []
    assert ans["refusal_reason"]


def test_ask_respects_as_of_and_audience():
    r = client.post(
        "/v1/ask",
        json={"question": "?", "as_of": "2023-09-01", "audience": "customer"},
    )
    assert r.status_code == 200
    ans = r.json()
    assert ans["as_of"] == "2023-09-01"
    assert ans["audience"] == "customer"


def test_build_status_json_valid():
    status = json.loads((ROOT / "build_status.json").read_text(encoding="utf-8"))
    assert "components" in status and isinstance(status["components"], list)
    for c in status["components"]:
        assert c["status"] in ("done", "in_progress", "pending")
