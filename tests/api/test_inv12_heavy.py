"""INV-12 qua API (heavy — audit điểm 3): token customer gọi MỌI endpoint đọc
→ 0 byte từ artifact internal/restricted, kể cả qua timeline/graph/citation/norm.

Marker 'LSNB-2026-MAT-7d3f' nằm trong body node nội bộ (seed) — nếu nó xuất hiện
trong BẤT KỲ response nào của customer là leak thật, test đỏ.
"""
import json

import pytest

pytestmark = pytest.mark.heavy

from tests.api.seed_demo import (  # noqa: E402
    INTERNAL_MARKER,
    N_D8K2,
    N_QT3,
    NORM_CHOVAY,
)

EMP = {"X-Role": "employee"}
CUS = {"X-Role": "customer"}
PUB_KEY = "39/2016/TT-NHNN~dieu:8/khoan:2"


def _no_marker(resp) -> None:
    assert INTERNAL_MARKER not in resp.text, "byte nội bộ lọt ra response customer (INV-12)"


def test_customer_timeline_internal_node_404_zero_bytes(seeded_client):
    r = seeded_client.get(f"/v1/nodes/{N_QT3}/timeline", headers=CUS)
    assert r.status_code == 404
    _no_marker(r)
    r = seeded_client.get("/v1/nodes/QT-TD-01~dieu:3/timeline", headers=CUS)
    assert r.status_code == 404
    _no_marker(r)
    # employee thì thấy (đúng entitlement)
    r = seeded_client.get(f"/v1/nodes/{N_QT3}/timeline", headers=EMP)
    assert r.status_code == 200


def test_customer_graph_drops_internal_endpoints(seeded_client):
    r_emp = seeded_client.get(f"/v1/nodes/{PUB_KEY}/graph?depth=2", headers=EMP)
    r_cus = seeded_client.get(f"/v1/nodes/{PUB_KEY}/graph?depth=2", headers=CUS)
    assert r_emp.status_code == r_cus.status_code == 200
    emp, cus = r_emp.json(), r_cus.json()
    # employee thấy inbound tham_quyen từ node nội bộ; customer KHÔNG
    emp_kinds = {e["kind"] for e in emp["edges"]}
    cus_kinds = {e["kind"] for e in cus["edges"]}
    assert "tham_quyen" in emp_kinds
    assert "tham_quyen" not in cus_kinds
    cus_node_ids = {n["node_id"] for n in cus["nodes"]}
    assert str(N_QT3) not in cus_node_ids
    _no_marker(r_cus)
    # không node nào của customer thuộc doc nội bộ
    assert all(n["doc_key"] != "QT-TD-01" for n in cus["nodes"])


def test_customer_artifact_source_404(seeded_client):
    r = seeded_client.get("/v1/artifacts/QT-TD-01", headers=CUS)
    assert r.status_code == 404
    _no_marker(r)
    assert seeded_client.get("/v1/artifacts/QT-TD-01", headers=EMP).status_code == 200
    assert seeded_client.get("/v1/artifacts/39%2F2016%2FTT-NHNN", headers=CUS).status_code == 200


def test_norm_visible_only_via_public_incarnations(seeded_client):
    # norm 'quy chế cho vay' có hiện thân TT39 (public) → cả hai role thấy
    assert seeded_client.get(f"/v1/norms/{NORM_CHOVAY}", headers=CUS).status_code == 200
    assert seeded_client.get(f"/v1/norms/{NORM_CHOVAY}", headers=EMP).status_code == 200


def test_customer_cannot_reach_admin_even_readonly(seeded_client):
    for path in ("/v1/admin/ops", "/v1/admin/backlog", "/v1/admin/demand",
                 "/v1/admin/notifications", "/v1/admin/conflicts", "/v1/admin/batches"):
        r = seeded_client.get(path, headers=CUS)
        assert r.status_code == 403, path
        _no_marker(r)


def test_full_read_sweep_zero_internal_bytes(seeded_client):
    """Quét mọi endpoint đọc công khai với token customer — gom toàn bộ byte trả về."""
    collected = []
    for path in (
        f"/v1/nodes/{PUB_KEY}/timeline",
        f"/v1/nodes/{PUB_KEY}/graph?depth=2",
        f"/v1/nodes/{N_D8K2}/timeline",
        f"/v1/norms/{NORM_CHOVAY}",
        "/v1/artifacts/39%2F2016%2FTT-NHNN",
    ):
        r = seeded_client.get(path, headers=CUS)
        collected.append(r.text)
    r = seeded_client.post("/v1/ask", json={"question": "quy trình thẩm định nội bộ?"}, headers=CUS)
    collected.append(r.text)
    r = seeded_client.post("/v1/ask", json={"question": "quy trình thẩm định nội bộ?"},
                           headers={**CUS, "Accept": "text/event-stream"})
    collected.append(r.text)
    blob = "\n".join(collected)
    assert INTERNAL_MARKER not in blob
    assert "QT-TD-01" not in blob, "doc_key nội bộ cũng là metadata không được lộ"


def test_timeline_provenance_redacted_would_be_visible_to_employee(seeded_client):
    """Đối chứng: employee thấy provenance đầy đủ trên node public."""
    r = seeded_client.get(f"/v1/nodes/{PUB_KEY}/timeline", headers=EMP)
    t = r.json()
    v2 = [v for v in t["versions"] if v["version"] == 2][0]
    assert v2["provenance"] and v2["provenance"][0]["ratified_by"] == "lan.nguyen@shb"
    assert v2["diff_from_prev"]
