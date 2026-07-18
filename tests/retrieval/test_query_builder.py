"""Query builder MỘT CỬA (R-28, D-27, D-44, INV-12) — unit, không cần DB.

Bảng chân trị predicate chạy trên MemStore (mirror thuần Python của SQL);
bản SQL chạy trong tests/retrieval/test_db_heavy.py trên Postgres thật —
hai hiện thân phải cho cùng kết quả trên cùng ca.
"""
from datetime import date
from pathlib import Path

import pytest

from retrieval import query_builder as qb

ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Entitlements (D-44, R-36)
# ---------------------------------------------------------------------------

def test_entitlements_mapping():
    assert qb.entitlements_for("customer") == ("public",)
    assert qb.entitlements_for("employee") == ("public", "internal")
    with pytest.raises(ValueError):
        qb.entitlements_for("admin")


def test_no_persona_sees_restricted():
    for persona in ("customer", "employee"):
        assert "restricted" not in qb.entitlements_for(persona)


# ---------------------------------------------------------------------------
# SQL constants phải mang ĐỦ conjunct bắt buộc (INV-8, INV-12 wiring)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [qb.CANDIDATE_SQL, qb.VERSIONS_AT_SQL])
def test_candidate_sql_has_all_mandatory_conjuncts(sql):
    for frag in ("nv.run_id = %(run_id)s", "nv.retrievable", "nv.status = 'active'",
                 "nv.valid_from <= %(as_of)s", "a.audience::text = ANY(%(entitlements)s)",
                 "scope_predicate"):
        assert frag in sql, f"thiếu conjunct: {frag}"


@pytest.mark.parametrize("sql", [qb.PENDING_SQL, qb.TIMELINE_SQL, qb.SUSPENSIONS_SQL,
                                 qb.STATUS_AT_SQL])
def test_every_snapshot_sql_filters_audience(sql):
    assert "ANY(%(entitlements)s)" in sql  # không đường đọc snapshot nào bỏ audience


def test_timeline_sql_sees_suspended_but_not_amending():
    # timeline: KHÔNG lọc status (thấy treo/đóng) nhưng vẫn lọc retrievable (amending/oracle)
    assert "nv.status" not in qb.TIMELINE_SQL.split("WHERE", 1)[1].split("ORDER", 1)[0] \
        or "status = 'active'" not in qb.TIMELINE_SQL
    assert "nv.retrievable" in qb.TIMELINE_SQL


def test_one_door_no_node_version_reads_outside_query_builder():
    """MỌI SELECT trên node_version phải nằm trong query_builder.py (D-27/D-44)."""
    offenders = []
    for d in ("retrieval", "answer"):
        for f in (ROOT / d).rglob("*.py"):
            if f.name == "query_builder.py":
                continue
            src = f.read_text(encoding="utf-8")
            if "FROM node_version" in src or "JOIN node_version" in src:
                offenders.append(str(f))
    assert offenders == [], f"đọc snapshot ngoài một cửa: {offenders}"


# ---------------------------------------------------------------------------
# Applicability DSL đóng (D-25) — bảng chân trị thuần
# ---------------------------------------------------------------------------

GF = {"contract_signed_before": "2023-09-01", "not_amended_on_or_after": "2023-09-01"}


@pytest.mark.parametrize("scope,cohort,expected", [
    (None, {}, True),                                    # scope NULL → mọi chủ thể
    (None, {"contract_signed_before": date(2024, 1, 1)}, True),
    (GF, {}, True),                                      # cohort thiếu → match mọi nhánh
    (GF, {"contract_signed_before": date(2021, 7, 1)}, True),       # ký 6/2021 → thuộc
    (GF, {"contract_signed_before": date(2023, 9, 1)}, True),       # đúng biên
    (GF, {"contract_signed_before": date(2024, 6, 1)}, False),      # ký sau → loại
    (GF, {"contract_signed_before": date(2021, 7, 1),
          "not_amended_on_or_after": date(1900, 1, 1)}, True),      # chưa từng sửa
    (GF, {"not_amended_on_or_after": date(2024, 1, 1)}, False),     # sửa cam kết muộn hơn biên
    ({"entity_class": "ca_nhan"}, {}, True),
    ({"entity_class": "ca_nhan"}, {"entity_class": "ca_nhan"}, True),
    ({"entity_class": "ca_nhan"}, {"entity_class": "phap_nhan"}, False),
])
def test_applicability_truth_table(scope, cohort, expected):
    assert qb.applicability_matches(scope, cohort) is expected


def test_certain_match_requires_all_fields():
    assert qb.certain_match(GF, {"contract_signed_before": date(2021, 7, 1)}) is False
    assert qb.certain_match(GF, {"contract_signed_before": date(2021, 7, 1),
                                 "not_amended_on_or_after": date(1900, 1, 1)}) is True
    assert qb.certain_match(None, {}) is True


# ---------------------------------------------------------------------------
# MemStore — bảng chân trị predicate (as_of × status × scope × audience)
# ---------------------------------------------------------------------------

def _row(nid, status="active", vf=date(2020, 1, 1), vt=None, scope=None, shash="",
         audience="public", retrievable=True, run="r1"):
    return qb.SnapshotRow(
        node_id=nid, version=1, heading=None, body=f"body {nid}", status=status,
        valid_from=vf, valid_to=vt, scope_predicate=scope, scope_hash=shash,
        provenance=(), run_id=run, path=f"dieu:{nid}", role="rule", artifact_id="a",
        doc_key="39/2016/TT-NHNN", audience=audience, retrievable=retrievable)


@pytest.fixture()
def store():
    rows = [
        _row("old", vf=date(2017, 1, 1), vt=date(2023, 9, 1)),          # đã đóng
        _row("cur", vf=date(2023, 9, 1)),                                # đang hiệu lực
        _row("fut", vf=date(2026, 9, 1)),                                # tương lai
        _row("susp", status="suspended", vf=date(2023, 9, 1)),           # treo
        _row("rep", status="repealed", vf=date(2020, 1, 1)),             # bãi bỏ
        _row("amn", retrievable=False, vf=date(2020, 1, 1)),             # amending/oracle
        _row("int", audience="internal", vf=date(2020, 1, 1)),           # nội bộ
        _row("gf", vf=date(2023, 9, 1), scope=dict(GF), shash="gf"),     # nhánh grandfather
        _row("stale", run="r0", vf=date(2020, 1, 1)),                    # run cũ
    ]
    return qb.MemStore(rows, run=qb.RunInfo(run_id="r1"))


TRUTH = [
    # (as_of, cohort, audience, node kỳ vọng CÓ, node kỳ vọng KHÔNG)
    (date(2024, 3, 1), {}, "employee",
     {"cur", "int", "gf"}, {"old", "fut", "susp", "rep", "amn", "stale"}),
    (date(2024, 3, 1), {}, "customer",
     {"cur", "gf"}, {"int"}),                                    # INV-12 tại predicate
    (date(2018, 1, 1), {}, "employee",
     {"old"}, {"cur", "gf", "susp", "int"}),                     # point-in-time (int chưa hiệu lực)
    (date(2027, 1, 1), {}, "employee", {"fut", "cur"}, {"old"}),
    (date(2024, 3, 1), {"contract_signed_before": date(2024, 6, 1)}, "employee",
     {"cur"}, {"gf"}),                                           # cohort loại nhánh gf
    (date(2024, 3, 1), {"contract_signed_before": date(2021, 7, 1)}, "employee",
     {"cur", "gf"}, set()),                                      # cohort thuộc nhánh gf
]


@pytest.mark.parametrize("as_of,cohort,audience,expect_in,expect_out", TRUTH)
def test_candidate_truth_table(store, as_of, cohort, audience, expect_in, expect_out):
    ent = qb.entitlements_for(audience)
    got = {r.node_id for r in store.candidates(as_of, cohort, ent)}
    assert expect_in <= got, f"thiếu {expect_in - got}"
    assert not (expect_out & got), f"lọt {expect_out & got}"


def test_pending_versions_only_future_labeled_branch(store):
    got = {r.node_id for r in store.pending_versions(date(2024, 3, 1),
                                                     qb.entitlements_for("employee"))}
    assert got == {"fut"}


def test_timeline_sees_suspended_and_closed_not_amending(store):
    ent = qb.entitlements_for("employee")
    assert {r.node_id for r in store.timeline("39/2016/TT-NHNN", "dieu:susp", ent)} == {"susp"}
    assert {r.node_id for r in store.timeline("39/2016/TT-NHNN", "dieu:old", ent)} == {"old"}
    assert store.timeline("39/2016/TT-NHNN", "dieu:amn", ent) == []  # amending không lộ text


def test_timeline_respects_audience(store):
    assert store.timeline("39/2016/TT-NHNN", "dieu:int", qb.entitlements_for("customer")) == []


def test_version_status_at_and_visibility(store):
    ent_e = qb.entitlements_for("employee")
    ent_c = qb.entitlements_for("customer")
    assert store.version_status_at("susp", date(2024, 3, 1), ent_e) == "suspended"
    assert store.version_status_at("cur", date(2024, 3, 1), ent_e) == "active"
    assert store.version_status_at("int", date(2024, 3, 1), ent_c) is None
    assert store.node_visible("int", ent_e) and not store.node_visible("int", ent_c)
