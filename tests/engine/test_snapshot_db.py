"""Snapshot/replay trên Postgres thật (R-18..R-20) — heavy, tự skip khi thiếu DB.

Chạy trong CI lane heavy (TEST_DATABASE_URL trỏ DB vứt được) hoặc thủ công.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.heavy

psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[2]
K_NOW = datetime(2027, 6, 1, tzinfo=timezone.utc)


@pytest.fixture()
def conn():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL chưa đặt — bỏ qua test DB")
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.execute((ROOT / "db" / "init.sql").read_text(encoding="utf-8"))
        yield c


def _seed(conn, corpus):
    """Nạp fixture corpus vào DB: text gốc của node đi qua page_anchor (xem snapshot.py)."""
    from psycopg.types.json import Json

    for a in corpus.artifacts:
        conn.execute(
            "INSERT INTO artifact (id, doc_key, doc_type, issuer, title, issued_date, "
            "effective_date, audience, owner, is_oracle, synthetic, ingested_at, text) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s)",
            (a.id, a.doc_key, a.doc_type, a.issuer, a.title, a.issued_date,
             a.effective_date, a.audience, a.owner, a.is_oracle,
             a.ingested_at or K_NOW, a.text))
    for n in corpus.nodes:
        conn.execute(
            "INSERT INTO node (id, artifact_id, path, role, page_anchor) "
            "VALUES (%s,%s,%s,%s,%s)",
            (n.id, n.artifact_id, n.path, n.role,
             Json({"heading": n.heading, "body": n.body})))
    # op nhắm op phải insert SAU op đích (FK target_op)
    for o in sorted(corpus.ops, key=lambda o: o.target_op is not None):
        conn.execute(
            "INSERT INTO op (id, kind, source_artifact, source_node, source_quote, seq, "
            "target_node, target_op, target_norm, target_part, new_text, new_heading, "
            "valid_from, valid_to, valid_to_event, scope_predicate, extractor, confidence, "
            "status, ratified_by, ingested_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (o.id, o.kind.value, o.source_artifact, o.source_node, o.source_quote, o.seq,
             o.target_node, o.target_op, o.target_norm, o.target_part, o.new_text,
             o.new_heading, o.valid_from, o.valid_to, o.valid_to_event,
             Json(o.scope_predicate) if o.scope_predicate else None, o.extractor,
             o.confidence, o.status.value, o.ratified_by, o.ingested_at))


def test_replay_roundtrip_and_inv8(conn, corpus):
    from engine.snapshot import replay

    _seed(conn, corpus)
    hook_calls = []
    report = replay(conn, k_cutoff=K_NOW,
                    on_snapshot_written=lambda c, run_id: hook_calls.append(run_id))
    assert report["versions"] > 0 and report["nodes"] > 0
    assert hook_calls == [report["run_id"]]              # hook F5 được gọi đúng 1 lần (R-19)

    # INV-8: node role amending → retrievable=false mọi version
    rows = conn.execute(
        "SELECT nv.retrievable, n.role FROM node_version nv JOIN node n ON n.id=nv.node_id"
    ).fetchall()
    assert rows
    for retrievable, role in rows:
        assert retrievable == (role != "amending")

    # pending_event mở cho 3 op suspend treo-theo-sự-kiện (D-11)
    n_pending = conn.execute(
        "SELECT count(*) FROM pending_event WHERE kind='open_suspension' AND status='open'"
    ).fetchone()[0]
    assert n_pending == 3

    # norm_decl → bảng norm có hiện thân
    n_norm = conn.execute("SELECT count(*) FROM norm").fetchone()[0]
    assert n_norm == 1

    # INV-9 phía DB: replay lần 2 → bit-exact modulo run_id
    report2 = replay(conn, k_cutoff=K_NOW)
    assert report2["state_digest"] == report["state_digest"]
    assert report2["run_id"] != report["run_id"]
    dump = conn.execute(
        "SELECT node_id, version, heading, body, status, valid_from, valid_to, "
        "scope_hash, provenance, retrievable FROM node_version "
        "ORDER BY node_id, version").fetchall()
    assert len({r[:2] for r in dump}) == len(dump)

    # trigger R-1: ghi node_version ngoài replay transaction bị chặn
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM node_version")
