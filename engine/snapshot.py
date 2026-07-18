"""Snapshot/replay (S4.5 R-18..R-20) — lớp DB DUY NHẤT của engine (fold vẫn pure).

- Ghi toàn bộ `node_version` trong MỘT transaction replay (`SET LOCAL lawstate.replay='on'`,
  trigger R-1) với run_id MỚI; run cũ = mọi replay_run có run_id khác bản mới nhất (stale).
- retrievable=false ⟺ role='amending' ∨ artifact.is_oracle (INV-8; node oracle bị fold bỏ
  qua từ gốc nên chỉ còn vế amending).
- Certificate → bảng conflict (tier 2) + pending_event(open_conflict); op treo-theo-sự-kiện
  còn mở → pending_event(open_suspension); close_window ratified → đóng pending_event.
- Embedding + BM25 rebuild là của F5: truyền hook `on_snapshot_written(conn, run_id)` —
  engine chỉ gọi, không tự cài (R-19).

Text gốc của node: bảng `node` không mang text — mặc định đọc `page_anchor.heading/body`
(F3 ghi lúc parse) hoặc cắt `artifact.text` theo `page_anchor.span`; override qua
`base_text_provider(node_row, artifact_text) -> (heading, body)`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from engine.fold import fold_corpus, state_digest
from engine.model import ArtifactInput, CorpusFold, NodeInput, jsonable, sv
from engine.windows import eligible_ops

BaseTextProvider = Callable[[dict, str | None], tuple[str | None, str | None]]


def default_base_text(node_row: dict, artifact_text: str | None) -> tuple[str | None, str | None]:
    pa = node_row.get("page_anchor") or {}
    heading, body = pa.get("heading"), pa.get("body")
    if body is None and artifact_text and isinstance(pa.get("span"), (list, tuple)):
        s, e = pa["span"][:2]
        body = artifact_text[int(s):int(e)]
    return heading, body


def load_corpus(conn, base_text_provider: BaseTextProvider = default_base_text):
    """Đọc L0/L1/L2 + precedence từ Postgres → input pure cho fold_corpus."""
    from psycopg.rows import dict_row  # noqa: PLC0415 — psycopg chỉ cần ở lớp DB
    from api import schemas            # noqa: PLC0415

    with conn.cursor(row_factory=dict_row) as cur:
        art_rows = cur.execute(
            "SELECT id, doc_key, doc_type, issuer, title, issued_date, effective_date, "
            "audience, owner, is_oracle, ingested_at, text FROM artifact").fetchall()
        artifacts = {r["id"]: ArtifactInput(
            id=r["id"], doc_key=r["doc_key"], doc_type=r["doc_type"], issuer=r["issuer"],
            issued_date=r["issued_date"], effective_date=r["effective_date"],
            title=r["title"], is_oracle=r["is_oracle"], audience=sv(r["audience"]),
            owner=r["owner"], text=r["text"], ingested_at=r["ingested_at"])
            for r in art_rows}
        nodes = []
        roles: dict[UUID, str] = {}
        for r in cur.execute("SELECT id, artifact_id, path, role, page_anchor FROM node"):
            heading, body = base_text_provider(r, artifacts[r["artifact_id"]].text)
            roles[r["id"]] = sv(r["role"])
            nodes.append(NodeInput(id=r["id"], artifact_id=r["artifact_id"],
                                   doc_key=artifacts[r["artifact_id"]].doc_key,
                                   path=r["path"], role=sv(r["role"]),
                                   heading=heading, body=body))
        ops = [schemas.Op(**{k: sv(v) if k in ("kind", "status", "risk_class") else v
                             for k, v in r.items()})
               for r in cur.execute(
                   "SELECT id, kind, source_artifact, source_node, source_quote, seq, "
                   "target_node, target_op, target_norm, target_part, new_text, new_heading, "
                   "valid_from, valid_to, valid_to_event, scope_predicate, risk_class, "
                   "extractor, confidence, status, ratified_by, ratified_at, ratify_batch, "
                   "superseded_by, ingested_at FROM op").fetchall()]
        precedence = cur.execute(
            "SELECT doc_type, issuer, rank, source_node, valid_from, valid_to "
            "FROM precedence").fetchall()
        prec = [type("Row", (), r)() for r in precedence] or None
    return nodes, ops, artifacts, prec, roles


def corpus_hash(nodes, ops, artifacts) -> str:
    payload = {"artifacts": sorted(a.id for a in artifacts.values()),
               "nodes": sorted(str(n.id) for n in nodes),
               "ops": sorted((str(o.id), sv(o.status), str(o.superseded_by))
                             for o in ops if o.id is not None)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def write_snapshot(conn, cf: CorpusFold, *, nodes, artifacts, roles: dict[UUID, str],
                   k_cutoff: datetime, corpus_hash_: str, ops_count: int) -> UUID:
    """MỘT transaction: xóa snapshot cũ, ghi run mới; conflict/pending_event/norm đi kèm."""
    from psycopg.types.json import Json  # noqa: PLC0415

    run_id = uuid4()
    started = datetime.now(timezone.utc)
    with conn.transaction():
        conn.execute("SET LOCAL lawstate.replay = 'on'")
        conn.execute("DELETE FROM node_version")
        for node_id in sorted(cf.versions, key=str):
            retrievable = roles.get(node_id) != "amending"          # INV-8 (oracle đã loại)
            for v in cf.versions[node_id]:
                conn.execute(
                    "INSERT INTO node_version (node_id, version, heading, body, status, "
                    "valid_from, valid_to, scope_predicate, scope_hash, provenance, run_id, "
                    "retrievable) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (v.node_id, v.version, v.heading, v.body, v.status, v.valid_from,
                     v.valid_to, Json(v.scope_predicate) if v.scope_predicate else None,
                     v.scope_hash, list(v.provenance), run_id, retrievable))
        conn.execute(
            "INSERT INTO replay_run (run_id, k_cutoff, corpus_hash, started, finished, "
            "ops_count) VALUES (%s,%s,%s,%s,now(),%s)",
            (run_id, k_cutoff, corpus_hash_, started, ops_count))
        for cert in cf.certificates:                                 # R-20
            members = [{"node_id": str(cert.node_id), "op_id": str(o)}
                       for o in cert.member_ops]
            exists = conn.execute(
                "SELECT id FROM conflict WHERE status='open' AND reason=%s",
                (cert.reason,)).fetchone()
            if exists:
                continue
            row = conn.execute(
                "INSERT INTO conflict (member_versions, tier, doctrine, reason, detected_by) "
                "VALUES (%s,%s,%s,%s,'engine.fold') RETURNING id",
                (Json(members), cert.tier, Json(jsonable(cert.doctrine)),
                 cert.reason)).fetchone()
            conn.execute(
                "INSERT INTO pending_event (kind, ref, predicate) VALUES "
                "('open_conflict', %s, %s)",
                (row[0], f"statement giải cho conflict: {cert.reason[:200]}"))
        for pw in cf.open_suspensions:                               # D-11
            if not conn.execute("SELECT 1 FROM pending_event WHERE ref=%s AND status='open'",
                                (pw.op_id,)).fetchone():
                conn.execute(
                    "INSERT INTO pending_event (kind, ref, predicate) VALUES "
                    "('open_suspension', %s, %s)", (pw.op_id, pw.predicate))
        for closed_op, closer in cf.closed_windows:
            conn.execute(
                "UPDATE pending_event SET status='closed', closed_by_op=%s "
                "WHERE ref=%s AND status='open'", (closer, closed_op))
        for ev in cf.norm_events:                                    # D-08/D-09
            prior = conn.execute(
                "SELECT topic FROM norm WHERE id=%s ORDER BY valid_from NULLS FIRST LIMIT 1",
                (ev.norm_id,)).fetchone()
            art = artifacts[ev.source_artifact]
            topic = prior[0] if prior else (art.title or art.doc_key)
            conn.execute(
                "INSERT INTO norm (id, topic, artifact_id, valid_from) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (id, artifact_id) DO UPDATE "
                "SET valid_from=EXCLUDED.valid_from", (ev.norm_id, topic,
                                                       ev.source_artifact, ev.valid_from))
            conn.execute(
                "UPDATE norm SET valid_to=%s WHERE id=%s AND artifact_id<>%s "
                "AND valid_from < %s AND (valid_to IS NULL OR valid_to > %s)",
                (ev.valid_from, ev.norm_id, ev.source_artifact, ev.valid_from, ev.valid_from))
    return run_id


def replay(conn, *, k_cutoff: datetime | None = None, precedence=None,
           base_text_provider: BaseTextProvider = default_base_text,
           on_snapshot_written: Callable[[Any, UUID], None] | None = None) -> dict:
    """Fold toàn corpus từ DB → ghi snapshot mới. → report cho /admin/replay (S6)."""
    nodes, ops, artifacts, db_prec, roles = load_corpus(conn, base_text_provider)
    k = k_cutoff or datetime.now(timezone.utc)
    cf = fold_corpus(nodes, ops, artifacts, precedence=precedence or db_prec, k_cutoff=k)
    run_id = write_snapshot(conn, cf, nodes=nodes, artifacts=artifacts, roles=roles,
                            k_cutoff=k, corpus_hash_=corpus_hash(nodes, ops, artifacts),
                            ops_count=len(eligible_ops(ops, k)))
    if on_snapshot_written is not None:
        on_snapshot_written(conn, run_id)                            # hook F5 (R-19)
    return {"run_id": run_id,
            "nodes": len(cf.versions),
            "versions": sum(len(v) for v in cf.versions.values()),
            "certificates": len(cf.certificates),
            "pending_open": len(cf.open_suspensions),
            "state_digest": state_digest(cf)}
