"""Replay THẬT qua API với engine F4 đã merge (heavy) — demo beat 8 'vòng đời 15 giây':
duyệt op (per-op + batch) → replay → trạng thái ĐỔI (timeline mang version do engine fold)
→ blast-radius bắn notification cho owner.
"""
import pytest

pytestmark = pytest.mark.heavy

from tests.api.seed_demo import (  # noqa: E402
    N_QT3,
    OP_BATCH_1,
    OP_BATCH_2,
    OP_BATCH_3,
    RUN_ID,
)

CUR = {"X-Role": "curator", "X-Actor": "qa.replay"}
EMP = {"X-Role": "employee"}
TPL = {"pattern": "uniform_field_change", "field_regex": r"\d+ ngày làm việc", "from": "10", "to": "07"}


def test_lifecycle_ratify_replay_state_changes(seeded_client):
    # 0) trước replay: QT3 chỉ có version seed (10 ngày làm việc), run cũ
    t0 = seeded_client.get(f"/v1/nodes/{N_QT3}/timeline", headers=EMP).json()
    assert len(t0["versions"]) == 1 and "10 ngày làm việc" in t0["versions"][0]["body"]

    # 1) curator ký lô 3 op cơ học 10→07 (D-19)
    r = seeded_client.post("/v1/admin/batches",
                           json={"op_ids": [OP_BATCH_1, OP_BATCH_2, OP_BATCH_3],
                                 "invariant_template": TPL, "description": "beat-8"},
                           headers=CUR)
    assert r.status_code == 200, r.text

    # 2) replay — engine F4 fold toàn corpus, run_id MỚI
    r = seeded_client.post("/v1/admin/replay", headers=CUR)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["status"] == "ok" and rep["run_id"] and rep["run_id"] != RUN_ID
    changed_ids = {c["node_id"] for c in rep["changed_nodes"]}
    assert N_QT3 in changed_ids, "node QT3 phải nằm trong changed_nodes sau khi op 10→07 ratified"
    assert "digest" in (rep.get("note") or "")

    # 3) câu trả lời ĐỔI (mức substrate): timeline QT3 giờ có 2 version, bản mới 07 ngày
    t1 = seeded_client.get(f"/v1/nodes/{N_QT3}/timeline", headers=EMP).json()
    bodies = [v["body"] for v in t1["versions"]]
    assert len(t1["versions"]) == 2
    assert any("07 ngày làm việc" in b for b in bodies)
    # lịch sử không bị viết lại: bản 10 ngày vẫn còn với cửa sổ đã đóng (INV-5 tinh thần)
    old = [v for v in t1["versions"] if "10 ngày làm việc" in (v["body"] or "")]
    assert old and old[0]["valid_to"] == "2023-10-01"
    # provenance version mới truy ra lô đã ký (INV-6 xuyên suốt)
    new = [v for v in t1["versions"] if "07 ngày làm việc" in (v["body"] or "")][0]
    assert any(p["batch_approved_by"] == "qa.replay" for p in new["provenance"])

    # 4) run_id được pin vào /ask meta (R-18)
    ans = seeded_client.post("/v1/ask", json={"question": "thời hạn thẩm định?"},
                             headers=EMP).json()
    assert ans["run_id"] == rep["run_id"]

    # 5) k8 vẫn đúng câu chuyện sau fold engine: suspended, chưa từng active
    t8 = seeded_client.get("/v1/nodes/39%2F2016%2FTT-NHNN~dieu:8/khoan:8/timeline",
                           headers=EMP).json()
    assert [v["status"] for v in t8["versions"]] == ["suspended"]
    assert t8["versions"][0]["never_active"] is True


def test_blast_radius_fires_on_approve(seeded_client):
    """R-23 qua adapter engine: approve op definitional nhắm d2k5 (TT39) →
    (1) d8k2 cite trực tiếp qua dinh_nghia; (2) QT-TD-01 cite “quy định của NHNN về
    cho vay” qua chu_de→Norm mà TT39 là hiện thân (PB-12) — cả hai nhận notice."""
    from tests.api.seed_demo import N_D8K2, N_QT3, OP_DEF_PROPOSED

    before = seeded_client.get("/v1/admin/notifications", headers=CUR).json()["total"]
    r = seeded_client.post(f"/v1/admin/ops/{OP_DEF_PROPOSED}/decision",
                           json={"action": "approve"}, headers=CUR)
    assert r.status_code == 200
    after = seeded_client.get("/v1/admin/notifications", headers=CUR).json()
    assert after["total"] == before + 2
    flat = [n for rows in after["by_owner"].values() for n in rows]
    new_nodes = {str(n["affected_node"]) for n in flat}
    assert {N_D8K2, N_QT3} <= new_nodes
    # op definitional → interruptive (D-36)
    assert any(n["severity"] == "interruptive" and str(n["affected_node"]) == N_D8K2
               for n in flat)
