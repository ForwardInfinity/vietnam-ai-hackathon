"""Heavy — predicate MỘT CỬA + contamination + INV-12 + e2e trên Postgres thật.

Fixture DROP SCHEMA public CASCADE rồi chạy db/init.sql + seed F5 — CHỈ trỏ
TEST_DATABASE_URL vào DB vứt được (giống tests/test_db_triggers.py).
"""
import json
import os
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.heavy

psycopg = pytest.importorskip("psycopg")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL chưa set — bỏ heavy DB tests", allow_module_level=True)

from answer import demo_seed as ds                                    # noqa: E402
from answer.compiler import SessionCtx                                # noqa: E402
from answer.compose import OfflineComposer                            # noqa: E402
from answer.service import answer_question                            # noqa: E402
from retrieval import query_builder as qb                             # noqa: E402
from retrieval.fuse import hybrid_search                              # noqa: E402

INIT_SQL = (Path(__file__).resolve().parent.parent.parent / "db" / "init.sql").read_text(
    encoding="utf-8")

TODAY = date(2026, 7, 18)
AS_OF = date(2024, 3, 1)
EMP = qb.entitlements_for("employee")
CUS = qb.entitlements_for("customer")


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(TEST_DATABASE_URL) as c:
        with c.transaction():
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.execute(INIT_SQL)
        c.commit()
        assert ds.seed_postgres(c, with_unresolved_d14=False) is True
        assert ds.seed_postgres(c) is False          # idempotent
        yield c


@pytest.fixture(scope="module")
def store(conn):
    s = qb.pg_store(conn)
    assert s is not None and s.run.run_id == ds.RUN_ID
    return s


# ---------------------------------------------------------------- truth table SQL

TRUTH = [
    # (as_of, cohort, ent, node có, node không)
    (AS_OF, {}, EMP,
     {ds.N_D7, ds.N_D8, ds.N_D13, ds.N_SHB, ds.N_NQ01_D7},
     {ds.N_TT06_D1, ds.N_TT10_D1, ds.N_K8, ds.N_K9, ds.N_K10}),
    (AS_OF, {}, CUS, {ds.N_D7}, {ds.N_SHB}),                       # INV-12 tại SQL
    (date(2018, 6, 1), {}, EMP, {ds.N_BLDS_468}, {ds.N_NQ01_D7, ds.N_K8}),
    (date(2027, 1, 1), {}, EMP, {ds.N_D7}, set()),
    (AS_OF, {"contract_signed_before": date(2024, 6, 1)}, EMP, {ds.N_D13}, set()),
]


@pytest.mark.parametrize("as_of,cohort,ent,expect_in,expect_out", TRUTH)
def test_sql_predicate_truth_table(store, as_of, cohort, ent, expect_in, expect_out):
    got = {r.node_id for r in store.candidates(as_of, cohort, ent)}
    assert expect_in <= got, f"thiếu {expect_in - got}"
    assert not (expect_out & got), f"lọt {expect_out & got}"


def test_sql_matches_memstore_semantics(store):
    """PgStore và MemStore phải trùng nhau trên cùng corpus (mirror predicate)."""
    mem = ds.mem_store()
    for as_of in (date(2018, 6, 1), AS_OF, date(2027, 1, 1)):
        for ent in (EMP, CUS):
            pg_keys = {r.key for r in store.candidates(as_of, {}, ent)}
            mem_keys = {r.key for r in mem.candidates(as_of, {}, ent)}
            assert pg_keys == mem_keys, f"lệch tại {as_of} {ent}"


def test_sql_grandfather_branch_selection(store):
    # cohort ký 6/2021: cả nhánh gf lẫn universal (bảo thủ ở predicate; service chọn)
    rows = store.candidates(AS_OF, {"contract_signed_before": date(2021, 7, 1)}, EMP)
    d13 = [r for r in rows if r.node_id == ds.N_D13]
    assert {r.scope_hash for r in d13} == {"", "gf-2023-09-01"}
    # HĐ 2024: nhánh gf bị loại ngay tại SQL
    rows = store.candidates(AS_OF, {"contract_signed_before": date(2024, 6, 1)}, EMP)
    d13 = [r for r in rows if r.node_id == ds.N_D13]
    assert {r.scope_hash for r in d13} == {""}


def test_sql_entity_class_scope(conn, store):
    """Probe nhánh entity_class của mảnh SQL scope (không có trong seed chính)."""
    conn.execute(
        """INSERT INTO node_version (node_id, version, body, status, valid_from,
                                     scope_predicate, scope_hash, provenance, run_id, retrievable)
           VALUES (%s, 99, 'chỉ dành cho pháp nhân', 'active', '2020-01-01',
                   %s, 'ec-pn', '{}', %s, true)""",
        (ds.N_D10, psycopg.types.json.Jsonb({"entity_class": "phap_nhan"}), ds.RUN_ID))
    conn.commit()
    ids = lambda rows: {(r.node_id, r.version) for r in rows}
    assert (ds.N_D10, 99) in ids(store.candidates(AS_OF, {}, EMP))                    # cohort thiếu
    assert (ds.N_D10, 99) in ids(store.candidates(AS_OF, {"entity_class": "phap_nhan"}, EMP))
    assert (ds.N_D10, 99) not in ids(store.candidates(AS_OF, {"entity_class": "ca_nhan"}, EMP))


# ---------------------------------------------------------------- contamination INV-8

def test_contamination_probe_top50_no_amending_node(store):
    """Query dựng từ NGUYÊN VĂN new_text của op suspend (k8) → top-50 KHÔNG chứa
    node amending mang bản sao text đó, KHÔNG chứa chính node treo."""
    k8_text = ds.T["k8"][1]
    rows = store.candidates(AS_OF, {}, EMP)
    top50 = hybrid_search(rows, k8_text, bm25_top=50, dense_top=50, top=50)
    ids = {r.node_id for r in top50}
    assert ds.N_TT06_D1 not in ids, "node amending lọt candidate set (INV-8 vỡ)"
    assert ds.N_TT10_D1 not in ids
    assert ds.N_K8 not in ids, "text treo lọt candidate set"
    # và text treo không xuất hiện nguyên văn trong bất kỳ row nào trả về
    assert all(k8_text not in r.text for r in top50)


def test_amending_rows_not_retrievable_in_db(conn):
    cur = conn.execute(
        """SELECT nv.retrievable FROM node_version nv WHERE nv.node_id IN (%s, %s)""",
        (ds.N_TT06_D1, ds.N_TT10_D1))
    vals = [r[0] for r in cur.fetchall()]
    assert vals and all(v is False for v in vals)


# ---------------------------------------------------------------- timeline D-27

def test_timeline_k8_never_active(store):
    rows = store.timeline("39/2016/TT-NHNN", "dieu:8/khoan:8", EMP)
    assert rows and all(r.status == "suspended" for r in rows)


def test_timeline_d7_three_versions(store):
    rows = store.timeline("39/2016/TT-NHNN", "dieu:7", EMP)
    assert [r.version for r in rows] == [1, 2, 3]


def test_timeline_internal_hidden_from_customer(store):
    assert store.timeline("QT-TD-01/SHB", "dieu:1", CUS) == []
    assert store.timeline("QT-TD-01/SHB", "dieu:1", EMP)


def test_pending_versions_sql(store):
    rows = store.pending_versions(AS_OF, EMP)
    assert any(r.node_id == ds.N_D7 and r.valid_from == date(2026, 9, 1) for r in rows)


def test_suspensions_and_consolidation_sql(store):
    susp = store.suspensions_at(AS_OF, EMP)
    assert {s.node_id for s in susp} == {ds.N_K8, ds.N_K9, ds.N_K10}
    assert all(s.pending_open for s in susp)
    assert ds.N_D10 in store.consolidation_pending()   # op proposed quá hạn (view)


def test_open_conflicts_sql(store):
    cfl = store.open_conflicts()
    assert len(cfl) == 1
    c = cfl[0]
    assert c.open_at(date(2018, 6, 1)) is True         # trước NQ01
    assert c.open_at(AS_OF) is False                   # sau NQ01


# ---------------------------------------------------------------- e2e + INV-10

def test_e2e_offline_composer_on_postgres(store):
    ans = answer_question("Điều kiện vay vốn hiện nay là gì?",
                          SessionCtx(audience="employee", as_of=AS_OF),
                          store=store, composer=OfflineComposer(), today=TODAY)
    assert ans.tier == "B" and ans.bases and ans.qa_id is not None


def test_inv12_customer_pipeline_on_postgres(store):
    ans, trace = answer_question(
        "Hạn mức phê duyệt tín dụng nội bộ của SHB là bao nhiêu?",
        SessionCtx(audience="customer", as_of=AS_OF),
        store=store, composer=OfflineComposer(), today=TODAY, return_trace=True)
    blob = trace.all_bytes() + ans.model_dump_json()
    assert ds.INTERNAL_MARKER not in blob
    assert "5 tỷ đồng" not in blob


def test_answer_log_written_and_replayable_inv10(conn, store):
    ans = answer_question("Lãi suất cho vay cho hợp đồng ký tháng 6/2021 chưa sửa đổi?",
                          SessionCtx(audience="employee", as_of=AS_OF),
                          store=store, composer=OfflineComposer(), today=TODAY)
    assert ans.qa_id is not None
    row = conn.execute(
        "SELECT question, tier, claims, run_id::text FROM answer_log WHERE qa_id = %s",
        (ans.qa_id,)).fetchone()
    assert row is not None and row[3] == ds.RUN_ID
    claims = row[2]
    assert claims, "claims phải được log"
    # INV-10: từ (node_id, version) + run pin tái dựng nguyên văn trích dẫn
    for c in claims:
        for ref in c["node_version_refs"]:
            nv = conn.execute(
                "SELECT heading, body FROM node_version WHERE node_id=%s AND version=%s",
                (ref["node_id"], ref["version"])).fetchone()
            assert nv is not None
            quotes = [q for q in c["text"].split('"') if len(q) > 40]
            full = f"{nv[0] or ''}\n{nv[1]}"
            for q in quotes:
                assert q in " ".join(full.split()), "trích dẫn không tái dựng được nguyên văn"
