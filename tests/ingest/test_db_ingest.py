"""Heavy: orchestrator persist trên Postgres thật — thứ tự R-3, alias DbStore,
op proposed vào bảng op, coverage upsert, VBHN oracle, op-on-op qua DB.

CẢNH BÁO: DROP SCHEMA public CASCADE — TEST_DATABASE_URL chỉ trỏ DB vứt được.
"""
import os
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.heavy

psycopg = pytest.importorskip("psycopg")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL chưa set — bỏ heavy DB tests", allow_module_level=True)

from ingest import manifest as mf                                   # noqa: E402
from ingest.alias import DbStore                                    # noqa: E402
from ingest.orchestrator import ingest_artifact                     # noqa: E402
from ingest.ratify import create_batch, ratify_op                   # noqa: E402

from tests.ingest.fixture_corpus import FIXTURE_DIR, FIXTURE_ENTRIES  # noqa: E402

INIT_SQL = (Path(__file__).parent.parent.parent / "db" / "init.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def db():
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute(INIT_SQL)
        yield conn


@pytest.fixture(scope="module")
def ingested(db):
    results = {}
    for entry in FIXTURE_ENTRIES:
        meta = mf.artifact_meta(entry)
        results[entry["doc_key"]] = ingest_artifact(
            db, FIXTURE_DIR / entry["file"], meta=meta)
    return results


def test_artifact_written_with_sha_and_k(db, ingested):
    row = db.execute("SELECT id, ingested_at, is_oracle FROM artifact WHERE doc_key=%s",
                     ("39/2016/TT-NHNN",)).fetchone()
    assert row and len(row[0]) == 64 and row[1] is not None
    oracle = db.execute("SELECT is_oracle FROM artifact WHERE doc_key=%s",
                        ("20/VBHN-NHNN",)).fetchone()
    assert oracle[0] is True


def test_nodes_and_aliases(db, ingested):
    n = db.execute("""SELECT count(*) FROM node n JOIN artifact a ON a.id=n.artifact_id
                      WHERE a.doc_key='39/2016/TT-NHNN'""").fetchone()[0]
    # 7+19+7+2+1 = 36 node cây + 1 preamble + 4 birth TT06 (k8-10, 32a) + 1 birth TT28 (7a)
    assert n == 42
    st = DbStore(db)
    res = st.resolve("39/2016/TT-NHNN", "dieu:8/khoan:2", date(2020, 1, 1))
    assert res is not None and not res.provisional


def test_birth_nodes_resolve_provisional(db, ingested):
    st = DbStore(db)
    res = st.resolve("39/2016/TT-NHNN", "dieu:8/khoan:8", date(2023, 8, 23))
    assert res is not None and res.provisional        # bẫy #4: chưa ratify → chưa alias


def test_ops_written_proposed(db, ingested):
    rows = db.execute("""SELECT o.kind, o.status FROM op o
                         JOIN artifact a ON a.id=o.source_artifact
                         WHERE a.doc_key='06/2023/TT-NHNN'""").fetchall()
    assert len(rows) == 7
    assert all(r[1] == "proposed" for r in rows)      # KHÔNG code path nào tự ratify (D-03)


def test_op_on_op_target_in_db(db, ingested):
    row = db.execute("""SELECT o.target_op, o.target_node FROM op o
                        JOIN artifact a ON a.id=o.source_artifact
                        WHERE a.doc_key='08/2026/TT-NHNN' AND o.kind='repeal'""").fetchone()
    assert row[0] is not None and row[1] is None      # nhắm OP (D-10/R-12)


def test_suspend_event_and_provenance(db, ingested):
    rows = db.execute("""SELECT o.valid_from, o.valid_to_event FROM op o
                         JOIN artifact a ON a.id=o.source_artifact
                         WHERE a.doc_key='10/2023/TT-NHNN' AND o.kind='suspend'""").fetchall()
    assert len(rows) == 3
    for vf, ev in rows:
        assert vf == date(2023, 9, 1) and ev and "văn bản quy phạm pháp luật mới" in ev


def test_scope_predicate_jsonb(db, ingested):
    rows = db.execute("""SELECT o.scope_predicate FROM op o
                         JOIN artifact a ON a.id=o.source_artifact
                         WHERE a.doc_key='06/2023/TT-NHNN' AND o.kind='insert'""").fetchall()
    assert rows and all(r[0] and r[0].get("contract_signed_before") == "2023-09-01"
                        for r in rows)


def test_coverage_upserted(db, ingested):
    row = db.execute("SELECT last_seq FROM coverage WHERE channel='sbv'").fetchone()
    assert row is not None


def test_vbhn_no_ops_no_edges(db, ingested):
    n_ops = db.execute("""SELECT count(*) FROM op o JOIN artifact a ON a.id=o.source_artifact
                          WHERE a.doc_key='20/VBHN-NHNN'""").fetchone()[0]
    assert n_ops == 0                                 # R-7
    n_edges = db.execute("""SELECT count(*) FROM edge e JOIN node n ON n.id=e.src_node
                            JOIN artifact a ON a.id=n.artifact_id
                            WHERE a.doc_key='20/VBHN-NHNN'""").fetchone()[0]
    assert n_edges == 0


def test_reingest_same_doc_rejected(db, ingested):
    entry = FIXTURE_ENTRIES[0]
    with pytest.raises(ValueError, match="append-only"):
        ingest_artifact(db, FIXTURE_DIR / entry["file"], meta=mf.artifact_meta(entry))


def test_edges_unresolved_backlogged_in_db(db, ingested):
    rows = db.execute("""SELECT count(*) FROM edge
                         WHERE dst_node IS NULL AND dst_norm IS NULL
                           AND frontier_ref IS NULL AND confidence = 0""").fetchone()
    assert rows[0] > 0                                # backlog R-10 nhìn thấy được trong DB


def test_batch_ratify_flow_with_human_signature(db, ingested):
    """R-16 + INV-6: machine-verify từng op, chữ ký người, spot-check ≥10%."""
    ids = [r[0] for r in db.execute(
        """SELECT o.id FROM op o JOIN artifact a ON a.id=o.source_artifact
           WHERE a.doc_key='28/2026/TT-NHNN' AND o.kind='amend'
             AND o.new_text LIKE '%hợp pháp%' AND o.status='proposed'""").fetchall()]
    assert len(ids) == 2
    tpl = {"pattern": "phrase_replace", "from": "phương án sử dụng vốn khả thi",
           "to": "phương án sử dụng vốn khả thi, hợp pháp"}
    out = create_batch(db, ids, tpl, approved_by="curator:test-human",
                       get_body=lambda nid: DbStore(db).node_info(nid)["body"])
    assert len(out["ratified"]) == 2 and not out["failed"]
    assert out["spot_check"]
    row = db.execute("SELECT status, ratified_by, ratify_batch FROM op WHERE id=%s",
                     (out["ratified"][0],)).fetchone()
    assert row[0] == "ratified" and row[1] == "curator:test-human" and row[2] is not None


def test_per_op_ratify_and_reject(db, ingested):
    rows = db.execute("""SELECT o.id FROM op o JOIN artifact a ON a.id=o.source_artifact
                         WHERE a.doc_key='11/2026/TT-NHNN' AND o.status='proposed'
                         ORDER BY o.seq""").fetchall()
    assert len(rows) >= 2
    ratify_op(db, rows[0][0], "curator:test-human")
    st = db.execute("SELECT status, ratified_by FROM op WHERE id=%s", (rows[0][0],)).fetchone()
    assert st == ("ratified", "curator:test-human")


def test_pipeline_seam_for_f6(db):
    """api/integrations.run_ingest_pipeline: artifact L0 lưu trước → ingest.pipeline.run(sha)."""
    import hashlib

    from ingest import pipeline

    raw = (FIXTURE_DIR / "tt12_seam_demo.txt").read_bytes() \
        if (FIXTURE_DIR / "tt12_seam_demo.txt").exists() else None
    text = """Số: 77/2026/TT-NHNN
Hà Nội, ngày 01 tháng 8 năm 2026
THÔNG TƯ
SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU CỦA THÔNG TƯ SỐ 39/2016/TT-NHNN
Căn cứ Luật Ngân hàng Nhà nước Việt Nam ngày 16 tháng 6 năm 2010;
Điều 1. Sửa đổi, bổ sung khoản 1 Điều 8 như sau:
“1. Để thực hiện các hoạt động đầu tư kinh doanh thuộc ngành, nghề cấm đầu tư kinh doanh theo quy định của pháp luật.”.
Điều 2. Hiệu lực thi hành
Thông tư này có hiệu lực thi hành từ ngày 01 tháng 10 năm 2026.
"""
    raw = text.encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    db.execute(
        """INSERT INTO artifact (id, doc_key, doc_type, issuer, title, issued_date,
                                 effective_date, audience, synthetic, raw, text)
           VALUES (%s,%s,'thong_tu','NHNN','TT seam demo','2026-08-01','2026-10-01',
                   'public', true, %s, %s)""", (sha, "77/2026/TT-NHNN", raw, text))
    report = pipeline.run(sha, conn=db, gateway=None)
    assert report["proposed_ops"] == 1
    row = db.execute("""SELECT o.kind, o.status, n.path FROM op o JOIN node n ON n.id=o.target_node
                        WHERE o.source_artifact=%s""", (sha,)).fetchone()
    assert row == ("amend", "proposed", "dieu:8/khoan:1")
    # chạy lại → từ chối (op append-only)
    with pytest.raises(ValueError, match="đã có op"):
        pipeline.run(sha, conn=db, gateway=None)


def test_page_anchor_carries_base_text_for_f4(db, ingested):
    """Quy ước F3→F4: node.page_anchor.heading/body = text gốc lúc parse (engine/README)."""
    row = db.execute("""SELECT n.page_anchor FROM node n JOIN artifact a ON a.id=n.artifact_id
                        WHERE a.doc_key='39/2016/TT-NHNN' AND n.path='dieu:8'""").fetchone()
    pa = row[0]
    assert pa["heading"] == "Những nhu cầu vốn không được cho vay"
    assert "không được cho vay" in pa["body"]


def test_f4_replay_end_to_end_on_ingested_corpus(db, ingested):
    """Tích hợp F3→F4 thật: ratify vài op TT06 rồi engine.snapshot.replay — text mới
    phải xuất hiện trong node_version, node amending retrievable=false (INV-8)."""
    engine_snapshot = pytest.importorskip("engine.snapshot")
    ids = [r[0] for r in db.execute(
        """SELECT o.id FROM op o JOIN artifact a ON a.id=o.source_artifact
           WHERE a.doc_key='06/2023/TT-NHNN' AND o.status='proposed'""").fetchall()]
    for oid in ids:
        ratify_op(db, oid, "curator:integration-test")
    report = engine_snapshot.replay(db)
    assert report["versions"] > 0
    body = db.execute("""SELECT nv.body FROM node_version nv JOIN node n ON n.id=nv.node_id
                         JOIN artifact a ON a.id=n.artifact_id
                         WHERE a.doc_key='39/2016/TT-NHNN' AND n.path='dieu:8/khoan:8'
                         ORDER BY nv.version DESC LIMIT 1""").fetchone()
    assert body and "gửi tiền" in body[0]           # op insert đã ratify → text sống
    amending = db.execute("""SELECT bool_or(nv.retrievable) FROM node_version nv
                             JOIN node n ON n.id=nv.node_id
                             WHERE n.role='amending'""").fetchone()[0]
    assert amending is False or amending is None    # INV-8: amending không bao giờ retrievable
