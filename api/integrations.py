"""Seam DUY NHẤT gọi sang module của task khác (F3/F4/F5/F7).

F4 (engine) ĐÃ MERGE → run_replay/notify_blast_radius là adapter THẬT theo
engine/README.md. F3/F5/F7 chưa merge → IntegrationMissing với TODO rõ;
endpoint dịch thành 501/ghi chú "stub". KHÔNG cài logic thật của họ ở đây.
"""
from __future__ import annotations

import hashlib
import importlib
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable
from uuid import UUID

TODO_F3 = "TODO(F3): ingest pipeline (parse cây → citation → op extraction) chưa merge"
TODO_F4 = "TODO(F4): engine fold/replay chưa merge"
TODO_F5 = "TODO(F5): answering pipeline (retrieval→closure→compose→verify) chưa merge"
TODO_F7 = "TODO(F7): eval runner chưa merge"


class IntegrationMissing(RuntimeError):
    def __init__(self, todo: str):
        self.todo = todo
        super().__init__(todo)


def _try(module: str, *fn_names: str) -> Callable[..., Any] | None:
    try:
        mod = importlib.import_module(module)
    except ImportError:
        return None
    for name in fn_names:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


def _plain_conn():
    """Connection psycopg tuple-row (engine dùng row[0]) — KHÔNG dict_row của api.db."""
    import psycopg

    from api.db import database_url

    return psycopg.connect(database_url())


# ---------------------------------------------------------------------------
# F3 — ingest pipeline
# ---------------------------------------------------------------------------

def run_ingest_pipeline(artifact_id: str) -> dict:
    """F3: chạy S4.1–S4.3 trên artifact đã lưu L0 → đề xuất op. → {proposed_ops, ...}"""
    fn = _try("ingest.pipeline", "run", "run_pipeline", "ingest_artifact")
    if fn is None:
        raise IntegrationMissing(TODO_F3)
    return fn(artifact_id)


# ---------------------------------------------------------------------------
# F4 — replay + blast-radius (adapter thật theo engine/README.md)
# ---------------------------------------------------------------------------

def _versions_digest(conn) -> dict[str, str]:
    """node_id → digest bộ version (so trước/sau replay tìm changed_nodes)."""
    rows = conn.execute(
        """SELECT node_id, version, status, valid_from, valid_to, scope_hash,
                  md5(coalesce(heading,'') || '§' || coalesce(body,'')) AS h
           FROM node_version ORDER BY node_id, version"""
    ).fetchall()
    acc: dict[str, list] = {}
    for r in rows:
        acc.setdefault(str(r[0]), []).append(tuple(str(x) for x in r[1:]))
    return {k: hashlib.md5(repr(v).encode()).hexdigest() for k, v in acc.items()}


def run_replay(k_cutoff: datetime | None = None) -> dict:
    """F4 engine.snapshot.replay → report FR-11: run_id + changed_nodes + certificates
    + guard_violations (invariant compliance R-24 chạy sau replay)."""
    if _try("engine.snapshot", "replay") is None:
        raise IntegrationMissing(TODO_F4)
    from engine import fold as fold_mod
    from engine import invariants, snapshot

    with _plain_conn() as conn:
        before_v = _versions_digest(conn)
        before_c = {str(r[0]) for r in conn.execute("SELECT id FROM conflict").fetchall()}

        report = snapshot.replay(conn, k_cutoff=k_cutoff)

        after_v = _versions_digest(conn)
        changed = []
        for nid in sorted(set(before_v) | set(after_v)):
            if before_v.get(nid) != after_v.get(nid):
                meta = conn.execute(
                    """SELECT a.doc_key, n.path FROM node n
                       JOIN artifact a ON a.id = n.artifact_id WHERE n.id = %s""",
                    (nid,),
                ).fetchone()
                kind = ("mới" if nid not in before_v
                        else "mất" if nid not in after_v else "đổi version")
                changed.append({"node_id": nid, "doc_key": meta[0] if meta else None,
                                "path": meta[1] if meta else None, "change": kind})
        new_certs = [
            {"id": str(r[0]), "tier": r[1], "reason": r[2]}
            for r in conn.execute(
                "SELECT id, tier, reason FROM conflict ORDER BY created_at"
            ).fetchall()
            if str(r[0]) not in before_c
        ]

        # R-24: invariant compliance trên effective state hôm nay
        nodes, ops, artifacts, prec, _roles = snapshot.load_corpus(conn)
        cf = fold_mod.fold_corpus(nodes, ops, artifacts, precedence=prec,
                                  k_cutoff=k_cutoff or datetime.now(timezone.utc))
        state = invariants.effective_state(cf, nodes, artifacts, as_of=date.today())
        violations = [
            {"invariant_id": v.invariant_id, "reason": v.reason,
             "members": [[str(n), ver] for n, ver in v.members]}
            for v in invariants.run_all(state)
        ]

    return {
        "run_id": report["run_id"],
        "changed_nodes": changed,
        "certificates": new_certs,
        "guard_violations": violations,
        "note": (f"fold: {report['nodes']} node / {report['versions']} version · "
                 f"certificates(open): {report['certificates']} · "
                 f"pending mở: {report['pending_open']} · digest {report['state_digest'][:12]}… · "
                 "TODO(F5): hook rebuild BM25/embedding (on_snapshot_written) chưa nối"),
    }


def notify_blast_radius(op_ids: list) -> int | None:
    """F4 R-23: where-used → INSERT notification cho owner. → số notice ghi, None nếu thiếu engine."""
    if _try("engine.blast_radius", "notifications_for_op") is None:
        return None
    from engine import blast_radius, snapshot

    written = 0
    with _plain_conn() as conn:
        nodes, ops, artifacts, _prec, _roles = snapshot.load_corpus(conn)
        ops_by_id = {o.id: o for o in ops if o.id is not None}
        nodes_by_id = {n.id: n for n in nodes}
        edges = [SimpleNamespace(src_node=r[0], dst_node=r[1], dst_norm=r[2])
                 for r in conn.execute(
                     "SELECT src_node, dst_node, dst_norm FROM edge").fetchall()]
        memberships: dict[UUID, set[str]] = {}
        for norm_id, artifact_id in conn.execute(
                "SELECT id, artifact_id FROM norm WHERE artifact_id IS NOT NULL").fetchall():
            memberships.setdefault(norm_id, set()).add(artifact_id)

        for raw in op_ids:
            op = ops_by_id.get(UUID(str(raw)))
            if op is None:
                continue
            for n in blast_radius.notifications_for_op(
                    op, ops_by_id=ops_by_id, nodes_by_id=nodes_by_id,
                    artifacts=artifacts, edges=edges, norm_memberships=memberships):
                dup = conn.execute(
                    "SELECT 1 FROM notification WHERE op_id = %s AND affected_node = %s",
                    (n.op_id, n.affected_node)).fetchone()
                if dup:
                    continue
                conn.execute(
                    """INSERT INTO notification (op_id, affected_node, affected_doc, owner, severity)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (n.op_id, n.affected_node, n.affected_doc, n.owner,
                     n.severity.value if hasattr(n.severity, "value") else n.severity))
                written += 1
    return written


# ---------------------------------------------------------------------------
# F5 — answering · F7 — eval
# ---------------------------------------------------------------------------

def run_answer_pipeline(req, entitlements: tuple[str, ...]):
    """F5: câu hỏi → Answer đầy đủ (compiler→retrieval→closure→compose→verify→tier)."""
    fn = _try("answer.pipeline", "answer", "run", "answer_question")
    if fn is None:
        raise IntegrationMissing(TODO_F5)
    return fn(req, entitlements=entitlements)


def run_eval(**kwargs) -> dict:
    """F7: golden set runner → report."""
    fn = _try("eval.runner", "run", "run_eval", "main")
    if fn is None:
        raise IntegrationMissing(TODO_F7)
    return fn(**kwargs)
