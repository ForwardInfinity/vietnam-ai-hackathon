"""Contract test schema (heavy — audit điểm 1): response validate đúng Pydantic
view model + ngữ nghĩa timeline S6 (mọi version kể cả chưa-từng-active + dải treo).
"""
import pytest

pytestmark = pytest.mark.heavy

from tests.api.seed_demo import EVENT_PREDICATE, N_D8K8, RUN_ID  # noqa: E402
from api.view_models import (  # noqa: E402
    BacklogOut,
    BatchVerifyOut,
    DemandOut,
    GraphOut,
    NormOut,
    NotificationDigestOut,
    OpsQueueOut,
    TimelineOut,
)
from tests.api.seed_demo import NORM_CHOVAY  # noqa: E402

CUR = {"X-Role": "curator", "X-Actor": "qa.hackathon"}
EMP = {"X-Role": "employee"}
PUB_KEY = "39/2016/TT-NHNN~dieu:8/khoan:2"


def test_timeline_schema_and_semantics(seeded_client):
    r = seeded_client.get(f"/v1/nodes/{PUB_KEY}/timeline", headers=EMP)
    t = TimelineOut.model_validate(r.json())
    assert len(t.versions) == 2
    v1, v2 = t.versions
    # cửa sổ nửa-mở nối nhau: v1 đóng đúng ngày v2 mở
    assert str(v1.valid_to) == str(v2.valid_from) == "2023-09-01"
    assert v2.diff_from_prev and "07 ngày làm việc" in v2.diff_from_prev
    assert str(v2.run_id) == RUN_ID
    assert t.aliases and t.source_link


def test_timeline_never_active_suspension_band(seeded_client):
    """SUS-02: khoản 8 Đ8 — version active KHÔNG BAO GIỜ tồn tại, dải treo có sự kiện mở."""
    r = seeded_client.get(f"/v1/nodes/{N_D8K8}/timeline", headers=EMP)
    t = TimelineOut.model_validate(r.json())
    assert [v.status for v in t.versions] == ["suspended"]
    assert t.versions[0].never_active is True
    assert len(t.suspensions) == 1
    band = t.suspensions[0]
    assert band.valid_to is None  # treo vô thời hạn
    assert band.event_predicate == EVENT_PREDICATE and band.event_status == "open"
    # provenance: chuỗi op insert (TT06) rồi suspend (TT10) — đúng câu chuyện phả hệ
    kinds = [p.kind for p in t.versions[0].provenance]
    assert kinds == ["insert", "suspend"]


def test_graph_schema_typed_edges_and_norm(seeded_client):
    r = seeded_client.get(f"/v1/nodes/{PUB_KEY}/graph?depth=2&as_of=2023-10-01", headers=EMP)
    g = GraphOut.model_validate(r.json())
    assert g.depth == 2 and str(g.as_of) == "2023-10-01"
    kinds = {e.kind for e in g.edges}
    assert "dinh_nghia" in kinds
    directions = {e.direction for e in g.edges}
    assert directions <= {"outbound", "inbound"}
    # unresolved edge (3 đích NULL) vẫn xuất hiện như outbound với confidence 0 (backlog thấy được)
    assert any(e.dst_node is None and e.dst_norm is None and e.frontier_ref is None for e in g.edges)


def test_graph_as_of_reprojects_edges(seeded_client):
    """Edge treo trên PHIÊN BẢN (D-13): as_of 2020 — version 2 chưa tồn tại → edge của v2 biến mất."""
    r = seeded_client.get(f"/v1/nodes/{PUB_KEY}/graph?depth=1&as_of=2020-01-01", headers=EMP)
    g = GraphOut.model_validate(r.json())
    assert all(e.src_version != 2 for e in g.edges if str(e.src_node) == g.center_nodes[0].__str__())


def test_norm_chain_schema(seeded_client):
    r = seeded_client.get(f"/v1/norms/{NORM_CHOVAY}", headers=EMP)
    n = NormOut.model_validate(r.json())
    assert n.topic.startswith("quy chế cho vay")
    assert n.incarnations[0].doc_key == "39/2016/TT-NHNN"
    assert "NON-BINDING" in n.correlation_note


def test_ops_queue_schema(seeded_client):
    r = seeded_client.get("/v1/admin/ops?status=proposed", headers=CUR)
    q = OpsQueueOut.model_validate(r.json())
    assert q.total == len(q.items) > 0
    assert all(i.op.get("source_quote") for i in q.items)


def test_batch_verify_schema(seeded_client):
    from tests.api.seed_demo import OP_BATCH_1

    r = seeded_client.post(
        "/v1/admin/batches/verify",
        json={"op_ids": [OP_BATCH_1],
              "invariant_template": {"pattern": "uniform_field_change",
                                     "field_regex": r"\d+ ngày làm việc", "from": "10", "to": "07"}},
        headers=CUR,
    )
    BatchVerifyOut.model_validate(r.json())


def test_backlog_demand_notification_schema(seeded_client):
    b = BacklogOut.model_validate(seeded_client.get("/v1/admin/backlog", headers=CUR).json())
    assert b.counts["pending_events_open"] >= 1
    assert b.counts["unresolved_refs"] >= 1
    assert b.counts["consolidation_pending"] >= 1
    assert any("F4" in n for n in b.notes)  # oracle_mismatch chờ engine — nói thẳng

    DemandOut.model_validate(seeded_client.get("/v1/admin/demand", headers=CUR).json())
    NotificationDigestOut.model_validate(
        seeded_client.get("/v1/admin/notifications", headers=CUR).json()
    )


def test_invalid_key_422_and_unknown_404(seeded_client):
    assert seeded_client.get("/v1/nodes/không-phải-key/timeline", headers=EMP).status_code == 422
    assert seeded_client.get(
        "/v1/nodes/99%2F2099%2FTT-XX~dieu:1/timeline", headers=EMP
    ).status_code == 404
