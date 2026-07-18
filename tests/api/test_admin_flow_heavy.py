"""Ratify flow qua API trên Postgres thật (heavy): INV-6 + D-19/D-20 end-to-end.

Audit điểm 2 & 4 của đề F6:
- không đường nào tạo op ratified thiếu người ký;
- op ratified từ chối edit in-place (sửa = op mới + superseded_by);
- seed op proposed → approve per-op → batch với template → spot-check ≥10%.
"""
import io
import math

import pytest

pytestmark = pytest.mark.heavy

from tests.api.seed_demo import (  # noqa: E402
    OP_BATCH_1,
    OP_BATCH_2,
    OP_BATCH_3,
    OP_DEF_PROPOSED,
    OP_NODATE,
)

CUR = {"X-Role": "curator", "X-Actor": "qa.hackathon"}
NO_ACTOR = {"X-Role": "curator"}
TPL = {"pattern": "uniform_field_change", "field_regex": r"\d+ ngày làm việc", "from": "10", "to": "07"}


def test_queue_sorted_and_diff_next_to_quote(seeded_client):
    r = seeded_client.get("/v1/admin/ops?status=proposed", headers=CUR)
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert body["total"] == len(items) == 5
    # R-17: definitional đứng đầu; confidence tăng dần trong nhóm còn lại
    assert items[0]["op"]["risk_class"] == "definitional"
    rest_conf = [i["op"]["confidence"] for i in items[1:]]
    assert rest_conf == sorted(rest_conf)
    # FR-9: source_quote + diff (hiện tại vs sau-áp) trên từng item có target text
    first = items[0]
    assert first["op"]["source_quote"]
    assert first["diff"] and "-" in first["diff"] and "+" in first["diff"]
    assert first["target"]["current_text"]


def test_router_flags_queues(seeded_client):
    r = seeded_client.get("/v1/admin/ops?status=proposed", headers=CUR)
    by_id = {i["op"]["id"]: i["queue"] for i in r.json()["items"]}
    assert by_id[OP_DEF_PROPOSED] == "per_op"          # definitional
    assert by_id[OP_NODATE] == "per_op"                # thiếu valid_from
    for oid in (OP_BATCH_1, OP_BATCH_2, OP_BATCH_3):   # cơ học đủ 4 điều kiện
        assert by_id[oid] == "batch_eligible"


def test_approve_requires_actor_inv6(seeded_client):
    r = seeded_client.post(f"/v1/admin/ops/{OP_DEF_PROPOSED}/decision",
                           json={"action": "approve"}, headers=NO_ACTOR)
    assert r.status_code == 422


def test_per_op_approve_then_immutable_then_supersede(seeded_client):
    r = seeded_client.post(f"/v1/admin/ops/{OP_DEF_PROPOSED}/decision",
                           json={"action": "approve"}, headers=CUR)
    assert r.status_code == 200
    assert r.json()["status"] == "ratified" and r.json()["actor"] == "qa.hackathon"

    # op ratified BẤT BIẾN: edit → 409 kèm hướng dẫn supersede (D-20)
    r = seeded_client.post(f"/v1/admin/ops/{OP_DEF_PROPOSED}/decision",
                           json={"action": "edit", "edits": {"new_text": "sửa lén"}}, headers=CUR)
    assert r.status_code == 409
    assert "supersede" in r.json()["detail"]

    # approve lần 2 → 409 (không double-ratify)
    r = seeded_client.post(f"/v1/admin/ops/{OP_DEF_PROPOSED}/decision",
                           json={"action": "approve"}, headers=CUR)
    assert r.status_code == 409

    # sửa thật = op MỚI + superseded_by trên op cũ
    r = seeded_client.post(f"/v1/admin/ops/{OP_DEF_PROPOSED}/decision",
                           json={"action": "supersede", "edits": {"confidence": 0.99}}, headers=CUR)
    assert r.status_code == 200
    new_id = r.json()["new_op_id"]
    assert new_id and r.json()["status"] == "superseded"

    import psycopg
    import os
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        old = conn.execute("SELECT status, superseded_by FROM op WHERE id = %s",
                           (OP_DEF_PROPOSED,)).fetchone()
        assert old[0] == "superseded" and str(old[1]) == new_id
        new = conn.execute("SELECT status, extractor FROM op WHERE id = %s", (new_id,)).fetchone()
        assert new[0] == "proposed" and "curator:qa.hackathon" in new[1]


def test_batch_rejects_per_op_routed_op(seeded_client):
    r = seeded_client.post("/v1/admin/batches",
                           json={"op_ids": [OP_BATCH_1, OP_NODATE], "invariant_template": TPL},
                           headers=CUR)
    assert r.status_code == 422
    detail = r.json()["detail"]
    reasons = {x["op_id"]: x for x in detail["results"]}
    assert not reasons[OP_NODATE]["ok"]
    # atomic: không op nào bị ratify khi lô fail
    q = seeded_client.get("/v1/admin/ops?status=proposed", headers=CUR).json()
    assert OP_BATCH_1 in {i["op"]["id"] for i in q["items"]}


def test_batch_template_mismatch_blocks_all(seeded_client):
    bad_tpl = {"pattern": "phrase_replace", "from": "không có trong text", "to": "gì đó"}
    r = seeded_client.post("/v1/admin/batches",
                           json={"op_ids": [OP_BATCH_1, OP_BATCH_2], "invariant_template": bad_tpl},
                           headers=CUR)
    assert r.status_code == 422


def test_batch_verify_then_sign_spotcheck_inv6(seeded_client):
    ids = [OP_BATCH_1, OP_BATCH_2, OP_BATCH_3]
    # bước 1: dry-run verify — machine check TỪNG op, so được với current_text (strong, weak=False)
    r = seeded_client.post("/v1/admin/batches/verify",
                           json={"op_ids": ids, "invariant_template": TPL}, headers=CUR)
    assert r.status_code == 200
    rep = r.json()
    assert rep["all_ok"] and all(x["ok"] and not x["weak"] for x in rep["results"])

    # bước 2: sign không actor → 422 (INV-6)
    r = seeded_client.post("/v1/admin/batches",
                           json={"op_ids": ids, "invariant_template": TPL}, headers=NO_ACTOR)
    assert r.status_code == 422

    # bước 3: sign cả lớp
    r = seeded_client.post("/v1/admin/batches",
                           json={"op_ids": ids, "invariant_template": TPL,
                                 "description": "Đồng bộ 10→07 ngày làm việc"}, headers=CUR)
    assert r.status_code == 200
    batch = r.json()
    assert batch["ratified_count"] == 3 and batch["approved_by"] == "qa.hackathon"
    assert len(batch["spot_check"]) >= max(1, math.ceil(3 * 0.1))
    assert all(item["source_quote"] for item in batch["spot_check"])

    # INV-6 qua API: mọi op ratified truy ra người ký (per-op HOẶC batch)
    r = seeded_client.get("/v1/admin/ops?status=ratified", headers=CUR)
    for item in r.json()["items"]:
        signer = item["op"]["ratified_by"] or item["batch_approved_by"]
        assert signer, f"op {item['op']['id']} ratified nhưng không truy ra người ký"
    ratified_ids = {i["op"]["id"] for i in r.json()["items"]}
    assert set(ids) <= ratified_ids


def test_batches_list_shows_signature(seeded_client):
    r = seeded_client.get("/v1/admin/batches", headers=CUR)
    assert r.status_code == 200
    # module này đã sign 1 batch ở test trên (thứ tự trong file bảo đảm)
    batches = r.json()["batches"]
    assert batches and batches[0]["approved_by"] == "qa.hackathon"
    assert batches[0]["spot_checked"]


def test_ingest_l0_and_conflict_on_dup_dockey(seeded_client):
    files = {"file": ("cv-2024.txt", io.BytesIO("Điều 1. Nội dung thử nghiệm.".encode()), "text/plain")}
    data = {"doc_key": "01/2024/TT-TEST", "doc_type": "thong_tu", "issuer": "NHNN",
            "audience": "public", "synthetic": "true"}
    r = seeded_client.post("/v1/admin/ingest", files=files, data=data, headers=CUR)
    assert r.status_code == 200
    out = r.json()
    assert out["created"] is True and out["pipeline"] in ("stub", "f3")

    # cùng nội dung → idempotent
    files = {"file": ("cv-2024.txt", io.BytesIO("Điều 1. Nội dung thử nghiệm.".encode()), "text/plain")}
    r = seeded_client.post("/v1/admin/ingest", files=files, data=data, headers=CUR)
    assert r.status_code == 200 and r.json()["created"] is False

    # cùng doc_key, nội dung KHÁC → 409 (artifact bất biến INV-1)
    files = {"file": ("cv-2024.txt", io.BytesIO("Điều 1. Nội dung KHÁC.".encode()), "text/plain")}
    r = seeded_client.post("/v1/admin/ingest", files=files, data=data, headers=CUR)
    assert r.status_code == 409


def test_conflict_triage_and_notification_ack(seeded_client):
    board = seeded_client.get("/v1/admin/conflicts", headers=CUR).json()["board"]
    cid = board["open"][0]["id"]
    r = seeded_client.post(f"/v1/admin/conflicts/{cid}/triage",
                           json={"ticket_ref": "JIRA-123", "fork": "external_external"}, headers=CUR)
    assert r.status_code == 200 and r.json()["triaged_by"] == "qa.hackathon"

    notif = seeded_client.get("/v1/admin/notifications", headers=CUR).json()
    assert notif["total"] >= 2 and notif["unacked"] >= 1
    some = next(iter(notif["by_owner"].values()))[0]
    r = seeded_client.post(f"/v1/admin/notifications/{some['id']}/ack", headers=CUR)
    assert r.status_code == 200 and r.json()["acked"] is True


def test_ask_with_run_logs_answer_and_demand_grows(seeded_client):
    q = "Câu hỏi demand log heavy — chưa trả lời được?"
    r = seeded_client.post("/v1/ask", json={"question": q, "audience": "employee"},
                           headers={"X-Role": "employee"})
    assert r.status_code == 200
    ans = r.json()
    assert ans["tier"] == "D" and ans["run_id"]  # run seed được pin
    assert ans["qa_id"], "có run mà không ghi answer_log là vi phạm INV-10"
    assert ans["coverage"], "coverage attestation phải đi kèm khi đã quét kênh"

    demand = seeded_client.get("/v1/admin/demand", headers=CUR).json()
    assert any(i["question"] == q for i in demand["items"])
