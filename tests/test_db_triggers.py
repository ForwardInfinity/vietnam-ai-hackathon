"""INV-1: trigger R-1 trên Postgres thật (heavy).

CẢNH BÁO: fixture DROP SCHEMA public CASCADE rồi chạy lại db/init.sql — CHỈ trỏ
TEST_DATABASE_URL vào database vứt được. Không set TEST_DATABASE_URL → skip toàn file.
CI: service container pgvector (xem .github/workflows/deploy.yml).
"""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.heavy

psycopg = pytest.importorskip("psycopg")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL chưa set — bỏ heavy DB tests", allow_module_level=True)

INIT_SQL = (Path(__file__).parent.parent / "db" / "init.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def db():
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute(INIT_SQL)
        conn.execute("""
            INSERT INTO artifact (id, doc_key, doc_type, issuer)
            VALUES ('sha-t1', '39/2016/TT-NHNN', 'thong_tu', 'NHNN')""")
        conn.execute("""
            INSERT INTO node (id, artifact_id, path)
            VALUES ('00000000-0000-0000-0000-000000000001', 'sha-t1', 'dieu:8/khoan:2')""")
        yield conn


def _raises_inv1(conn, sql, params=None):
    with pytest.raises(psycopg.errors.RaiseException, match="INV-1"):
        conn.execute(sql, params)


# --- artifact: bất biến tuyệt đối --------------------------------------------

def test_artifact_update_forbidden(db):
    _raises_inv1(db, "UPDATE artifact SET title = 'x' WHERE id = 'sha-t1'")


def test_artifact_delete_forbidden(db):
    _raises_inv1(db, "DELETE FROM artifact WHERE id = 'sha-t1'")


# --- op: proposed tự do; sau ratify bất biến trừ supersede -------------------

def _new_op(db, **overrides) -> str:
    cols = dict(kind="repeal", source_artifact="sha-t1",
                source_quote="bãi bỏ khoản 2 Điều 8", seq=1,
                target_node="00000000-0000-0000-0000-000000000001",
                extractor="rule", status="proposed")
    cols.update(overrides)
    row = db.execute(
        """INSERT INTO op (kind, source_artifact, source_quote, seq, target_node, extractor, status)
           VALUES (%(kind)s, %(source_artifact)s, %(source_quote)s, %(seq)s,
                   %(target_node)s, %(extractor)s, %(status)s) RETURNING id""",
        cols).fetchone()
    return row[0]


def test_op_proposed_editable_and_deletable(db):
    op_id = _new_op(db)
    db.execute("UPDATE op SET source_quote = 'bãi bỏ khoản 2 Điều 8 (sửa)' WHERE id = %s", (op_id,))
    db.execute("DELETE FROM op WHERE id = %s", (op_id,))


def test_op_ratify_then_immutable(db):
    op_id = _new_op(db)
    db.execute("UPDATE op SET status='ratified', ratified_by='curator:test', ratified_at=now() WHERE id = %s",
               (op_id,))
    _raises_inv1(db, "UPDATE op SET source_quote = 'viết lại lịch sử' WHERE id = %s", (op_id,))
    _raises_inv1(db, "UPDATE op SET valid_from = '2020-01-01' WHERE id = %s", (op_id,))
    _raises_inv1(db, "DELETE FROM op WHERE id = %s", (op_id,))


def test_op_ratified_supersede_transition_allowed_only_clean(db):
    old_id = _new_op(db)
    db.execute("UPDATE op SET status='ratified', ratified_by='curator:test' WHERE id = %s", (old_id,))
    new_id = _new_op(db, seq=2)
    # supersede sạch (chỉ đổi status + superseded_by) → OK (D-20)
    db.execute("UPDATE op SET status='superseded', superseded_by=%s WHERE id = %s", (new_id, old_id))
    # op đã superseded → đóng băng hoàn toàn
    _raises_inv1(db, "UPDATE op SET source_quote='x' WHERE id = %s", (old_id,))
    _raises_inv1(db, "DELETE FROM op WHERE id = %s", (old_id,))


def test_op_supersede_cannot_smuggle_other_changes(db):
    op_id = _new_op(db)
    db.execute("UPDATE op SET status='ratified', ratified_by='curator:test' WHERE id = %s", (op_id,))
    other = _new_op(db, seq=3)
    _raises_inv1(db,
        "UPDATE op SET status='superseded', superseded_by=%s, source_quote='lén sửa' WHERE id = %s",
        (other, op_id))


# --- answer_log: append-only -------------------------------------------------

def test_answer_log_append_only(db):
    qa = db.execute("""
        INSERT INTO answer_log (question, audience, as_of, tier, claims, retrieved, banners, run_id)
        VALUES ('test?', 'internal', current_date, 'D', '[]', '[]', '[]',
                '00000000-0000-0000-0000-00000000aaaa') RETURNING qa_id""").fetchone()[0]
    _raises_inv1(db, "UPDATE answer_log SET tier = 'A' WHERE qa_id = %s", (qa,))
    _raises_inv1(db, "DELETE FROM answer_log WHERE qa_id = %s", (qa,))


# --- node_version: chỉ replay transaction được UPDATE/DELETE -----------------

@pytest.fixture()
def node_version(db):
    db.execute("""
        INSERT INTO node_version (node_id, version, body, status, valid_from, provenance, run_id, retrievable)
        VALUES ('00000000-0000-0000-0000-000000000001', 1, 'text gốc', 'active',
                '2017-03-15', '{}', '00000000-0000-0000-0000-00000000bbbb', true)
        ON CONFLICT (node_id, version) DO NOTHING""")
    return "00000000-0000-0000-0000-000000000001"


def test_node_version_update_outside_replay_forbidden(db, node_version):
    _raises_inv1(db, "UPDATE node_version SET body = 'sửa ngoài replay' WHERE node_id = %s", (node_version,))
    _raises_inv1(db, "DELETE FROM node_version WHERE node_id = %s", (node_version,))


def test_node_version_writable_inside_replay_transaction(db, node_version):
    # transaction replay: SET LOCAL lawstate.replay = 'on' (giao thức cho F4 — CONTRACTS.md)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.transaction():
            conn.execute("SET LOCAL lawstate.replay = 'on'")
            conn.execute("UPDATE node_version SET body = 'replay ghi được' WHERE node_id = %s",
                         (node_version,))
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        body = conn.execute("SELECT body FROM node_version WHERE node_id = %s",
                            (node_version,)).fetchone()[0]
    assert body == "replay ghi được"
