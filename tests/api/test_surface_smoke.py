"""Contract bề mặt KHÔNG cần DB — chạy trong smoke.

- SSE /v1/ask: đúng trình tự event S6 (meta → token → citation → banner → tier → done).
- Auth: /admin/* 403 khi thiếu curator; mutation 422 khi thiếu X-Actor (INV-6 tại cổng).
- Persona: role customer bị ghim customer bất kể body (INV-12 tại cổng).
- Endpoint cần DB khi DB tắt → 503 sạch (không 500 traceback).
"""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.schemas import Answer, Banner, Basis, PiecewiseBlock
from api.sse import answer_to_events

DEAD_DB = "postgresql://x:x@127.0.0.1:59999/x"


@pytest.fixture()
def dead_db(monkeypatch):
    """Ép DB không tồn tại — test hành vi degrade bất kể môi trường có Postgres hay không."""
    monkeypatch.setattr("api.db.database_url", lambda: DEAD_DB)

client = TestClient(app)
CURATOR = {"X-Role": "curator", "X-Actor": "smoke.tester"}


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        ev = next(l.split(": ", 1)[1] for l in lines if l.startswith("event: "))
        data = json.loads(next(l.split(": ", 1)[1] for l in lines if l.startswith("data: ")))
        events.append((ev, data))
    return events


def test_ask_sse_event_order_stub():
    r = client.post("/v1/ask", json={"question": "Điều kiện vay?"},
                    headers={"Accept": "text/event-stream", "X-Role": "employee"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "meta" and kinds[-1] == "done"
    assert "tier" in kinds and kinds.index("tier") == len(kinds) - 2  # tier ngay trước done
    assert all(k in ("meta", "token", "citation", "banner", "tier", "done") for k in kinds)
    done = events[-1][1]
    assert done["answer"]["tier"] == "D"  # stub trung thực khi chưa có F5/run


def test_sse_order_with_full_answer_object():
    """Trình tự PHẢI đúng cả khi Answer có đủ token/citation/banner (F5 sau này)."""
    ans = Answer(
        tier="B", audience="employee", as_of="2023-09-02",
        run_id="11111111-1111-4111-8111-111111111111",
        answer=[PiecewiseBlock(text_vi="Áp dụng bản sửa đổi. [1]")],
        bases=[Basis(ref="[1]", citation_vi="khoản 2 Điều 8 TT 39/2016/TT-NHNN")],
        banners=[Banner(kind="pending_change", text_vi="Có thay đổi sắp hiệu lực")],
    )
    kinds = [e for e, _ in ( _parse_sse("".join(answer_to_events(ans))) )]
    # thứ tự S6: meta trước hết; token liền khối; citation sau token; banner sau citation; tier; done
    assert kinds[0] == "meta"
    assert kinds.index("citation") > max(i for i, k in enumerate(kinds) if k == "token")
    assert kinds.index("banner") > kinds.index("citation")
    assert kinds.index("tier") > kinds.index("banner")
    assert kinds[-1] == "done"


def test_ask_json_default_unchanged_contract_f1():
    r = client.post("/v1/ask", json={"question": "?"})
    assert r.status_code == 200
    ans = r.json()
    for key in ("answer", "bases", "conflicts", "upcoming_changes", "banners",
                "coverage", "tier", "audience", "as_of", "run_id"):
        assert key in ans


def test_customer_role_cannot_escalate_audience_via_body():
    r = client.post("/v1/ask", json={"question": "?", "audience": "employee"},
                    headers={"X-Role": "customer"})
    assert r.json()["audience"] == "customer"  # ghim tại cổng (INV-12)


def test_admin_requires_curator_role():
    for path in ("/v1/admin/ops", "/v1/admin/backlog", "/v1/admin/conflicts",
                 "/v1/admin/demand", "/v1/admin/notifications", "/v1/admin/batches"):
        assert client.get(path).status_code == 403, path
        assert client.get(path, headers={"X-Role": "employee"}).status_code == 403, path


def test_admin_mutations_require_actor_inv6():
    # dependency X-Actor chặn TRƯỚC khi chạm DB → 422 kể cả khi DB tắt
    r = client.post("/v1/admin/ops/00000000-0000-0000-0000-000000000001/decision",
                    json={"action": "approve"}, headers={"X-Role": "curator"})
    assert r.status_code == 422
    r = client.post("/v1/admin/batches",
                    json={"op_ids": [], "invariant_template": {"pattern": "phrase_replace", "from": "a", "to": "b"}},
                    headers={"X-Role": "curator"})
    assert r.status_code == 422
    r = client.post("/v1/admin/replay", headers={"X-Role": "curator"})
    assert r.status_code == 422


def test_db_endpoints_degrade_to_503_not_500(dead_db):
    r = client.get("/v1/admin/ops", headers=CURATOR)
    assert r.status_code == 503
    r = client.get("/v1/nodes/39%2F2016%2FTT-NHNN~dieu:8/timeline", headers={"X-Role": "employee"})
    assert r.status_code == 503


def test_ask_stub_honest_even_without_db(dead_db):
    r = client.post("/v1/ask", json={"question": "?"})
    assert r.status_code == 200 and r.json()["tier"] == "D" and r.json()["run_id"] is None


def test_eval_run_501_when_f7_missing():
    r = client.post("/v1/eval/run", json={}, headers=CURATOR)
    # F7 chưa merge → 501; khi F7 merge, test này đổi kỳ vọng (ghi trong report)
    assert r.status_code == 501
    assert "F7" in r.json()["detail"]


def test_replay_501_when_f4_missing():
    r = client.post("/v1/admin/replay", headers=CURATOR)
    assert r.status_code == 501
    assert "F4" in r.json()["detail"]


def test_bad_role_header_rejected():
    assert client.post("/v1/ask", json={"question": "?"}, headers={"X-Role": "root"}).status_code == 400


def test_openapi_has_all_s6_endpoints():
    paths = client.get("/openapi.json").json()["paths"]
    must = ["/v1/ask", "/v1/nodes/{key}/timeline", "/v1/nodes/{key}/graph", "/v1/norms/{norm_id}",
            "/v1/admin/ingest", "/v1/admin/ops", "/v1/admin/ops/{op_id}/decision",
            "/v1/admin/batches", "/v1/admin/replay", "/v1/admin/backlog",
            "/v1/admin/conflicts", "/v1/admin/demand", "/v1/admin/notifications",
            "/v1/eval/run", "/v1/feedback"]
    for m in must:
        assert m in paths, f"thiếu endpoint {m} (bảng S6)"
