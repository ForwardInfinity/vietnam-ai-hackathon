"""/v1/admin: ingest · replay · backlog · conflicts · demand · notifications (S6, FR-11..14)."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from api import db, integrations
from api.auth import require_actor, require_curator
from api.view_models import (
    BacklogOut,
    ConflictCreateRequest,
    ConflictTriageRequest,
    DemandItem,
    DemandOut,
    IngestOut,
    NotificationDigestOut,
    NotificationOut,
    ReplayOut,
)

router = APIRouter(prefix="/admin", tags=["admin:ops"], dependencies=[Depends(require_curator)])


# ---------------------------------------------------------------------------
# Ingest (multipart → L0 → F3 pipeline)
# ---------------------------------------------------------------------------

@router.post("/ingest", response_model=IngestOut)
def ingest(
    file: UploadFile = File(...),
    doc_key: str = Form(...),
    doc_type: str = Form(...),
    issuer: str = Form(...),
    title: str | None = Form(default=None),
    issued_date: date | None = Form(default=None),
    effective_date: date | None = Form(default=None),
    audience: str = Form(default="internal"),
    owner: str | None = Form(default=None),
    channel: str | None = Form(default=None),
    is_oracle: bool = Form(default=False),
    synthetic: bool = Form(default=False),
    actor: str = Depends(require_actor),
):
    """Lưu artifact L0 (sha256, tem K — R-3 bước 1) rồi gọi pipeline F3 (parse→citation→op).

    F3 chưa merge → trả pipeline='stub': văn bản ĐÃ vào log bất biến, op đề xuất = 0.
    """
    if audience not in ("public", "internal", "restricted"):
        raise HTTPException(422, "audience phải là public|internal|restricted")
    raw = file.file.read()
    if not raw:
        raise HTTPException(422, "file rỗng")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None  # DOCX/PDF → F3 parse (D-43)

    with db.tx() as conn:
        existing = conn.execute("SELECT id, doc_key FROM artifact WHERE id = %s", [sha]).fetchone()
        if existing:
            created = False
        else:
            dup = conn.execute("SELECT id FROM artifact WHERE doc_key = %s", [doc_key]).fetchone()
            if dup:
                raise HTTPException(409, f"doc_key {doc_key!r} đã tồn tại với nội dung khác (id={dup['id'][:12]}…) "
                                         "— artifact là log bất biến, không ghi đè (INV-1)")
            conn.execute(
                """INSERT INTO artifact (id, doc_key, doc_type, issuer, title, issued_date,
                                         effective_date, audience, owner, channel, is_oracle,
                                         synthetic, raw, text)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [sha, doc_key, doc_type, issuer, title, issued_date, effective_date,
                 audience, owner, channel, is_oracle, synthetic, raw, text],
            )
            created = True

    try:
        report = integrations.run_ingest_pipeline(sha)
        return IngestOut(artifact_id=sha, doc_key=doc_key, created=created, pipeline="f3",
                         proposed_ops=int(report.get("proposed_ops", 0)),
                         note=report.get("note"))
    except integrations.IntegrationMissing as missing:
        return IngestOut(artifact_id=sha, doc_key=doc_key, created=created, pipeline="stub",
                         proposed_ops=0, note=missing.todo + " — artifact đã vào L0, "
                         "op sẽ được đề xuất khi F3 chạy trên artifact này.")


# ---------------------------------------------------------------------------
# Replay (F4) — FR-11
# ---------------------------------------------------------------------------

@router.post("/replay", response_model=ReplayOut)
def replay(actor: str = Depends(require_actor)):
    """Chạy fold toàn corpus (F4) → {run_id, changed_nodes, certificates, guard_violations}.
    F4 chưa merge → 501 kèm TODO (UI hiển thị 'chờ engine')."""
    try:
        report = integrations.run_replay()
    except integrations.IntegrationMissing as missing:
        raise HTTPException(501, detail=missing.todo)
    return ReplayOut(
        status="ok",
        run_id=report.get("run_id"),
        changed_nodes=list(report.get("changed_nodes", [])),
        certificates=list(report.get("certificates", [])),
        guard_violations=list(report.get("guard_violations", [])),
        note=report.get("note"),
    )


# ---------------------------------------------------------------------------
# Backlog dashboard — FR-12
# ---------------------------------------------------------------------------

@router.get("/backlog", response_model=BacklogOut)
def backlog():
    notes = []
    with db.tx() as conn:
        consolidation = conn.execute(
            """SELECT v.node_id, n.path, a.doc_key,
                      count(o.id) AS proposed_ops_due
               FROM v_consolidation_pending v
               JOIN node n ON n.id = v.node_id
               JOIN artifact a ON a.id = n.artifact_id
               LEFT JOIN op o ON o.target_node = v.node_id AND o.status='proposed'
                              AND o.valid_from <= current_date
               GROUP BY v.node_id, n.path, a.doc_key ORDER BY a.doc_key, n.path"""
        ).fetchall()
        unresolved = conn.execute(
            """SELECT e.id, e.kind, e.raw_citation, e.confidence,
                      n.path AS src_path, a.doc_key AS src_doc_key
               FROM edge e JOIN node n ON n.id = e.src_node
               JOIN artifact a ON a.id = n.artifact_id
               WHERE e.dst_node IS NULL AND e.dst_norm IS NULL AND e.frontier_ref IS NULL
               ORDER BY a.doc_key"""
        ).fetchall()
        pending = conn.execute(
            """SELECT pe.id, pe.kind, pe.ref, pe.predicate, pe.status, pe.closed_by_op,
                      o.valid_to_event, sa.doc_key AS suspend_source_doc
               FROM pending_event pe
               LEFT JOIN op o ON o.id = pe.ref
               LEFT JOIN artifact sa ON sa.id = o.source_artifact
               WHERE pe.status = 'open' ORDER BY pe.kind"""
        ).fetchall()
        coverage = conn.execute(
            "SELECT channel, last_seq, last_checked FROM coverage ORDER BY channel"
        ).fetchall()

    oracle: list[dict] = []
    notes.append(integrations.TODO_F4 + " — oracle_mismatch (S4.7) sẽ đọc từ output diff của engine.")
    notes.append(integrations.TODO_F3 + " — coverage gap (R-6) do scanner kênh cập nhật; ở đây liệt kê attestation hiện có.")

    return BacklogOut(
        counts={
            "consolidation_pending": len(consolidation),
            "oracle_mismatch": len(oracle),
            "unresolved_refs": len(unresolved),
            "pending_events_open": len(pending),
            "coverage_channels": len(coverage),
        },
        consolidation_pending=consolidation,
        oracle_mismatch=oracle,
        unresolved_refs=unresolved,
        pending_events=pending,
        coverage=coverage,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Conflicts — kanban + triage + fork (FR-13, D-33..D-35)
# ---------------------------------------------------------------------------

@router.get("/conflicts")
def conflicts_list(
    status: str | None = Query(default=None),
    fork: str | None = Query(default=None),
):
    where, params = ["TRUE"], []
    if status:
        where.append("c.status = %s")
        params.append(status)
    if fork:
        where.append("c.fork = %s")
        params.append(fork)
    with db.tx() as conn:
        rows = conn.execute(
            f"""SELECT c.*, ro.source_quote AS resolved_by_quote
                FROM conflict c LEFT JOIN op ro ON ro.id = c.resolved_by_op
                WHERE {' AND '.join(where)}
                ORDER BY c.status, c.tier, c.created_at DESC""",
            params,
        ).fetchall()
    board: dict[str, list] = {"open": [], "resolved": [], "dismissed": [], "accepted_risk": []}
    for r in rows:
        board.setdefault(r["status"], []).append(r)
    return {"total": len(rows), "board": board}


@router.post("/conflicts")
def conflict_create(body: ConflictCreateRequest, actor: str = Depends(require_actor)):
    """Mở certificate thủ công (curator phát hiện bằng mắt — kênh SEM)."""
    with db.tx() as conn:
        row = conn.execute(
            """INSERT INTO conflict (member_versions, tier, label, fork, doctrine, reason,
                                     ticket_ref, detected_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            [json.dumps(body.member_versions), body.tier, body.label, body.fork,
             json.dumps(body.doctrine) if body.doctrine else None,
             body.reason, body.ticket_ref, f"curator:{actor}"],
        ).fetchone()
        return {"id": row["id"], "created": True}


@router.post("/conflicts/{conflict_id}/triage")
def conflict_triage(conflict_id: UUID, body: ConflictTriageRequest, actor: str = Depends(require_actor)):
    """Triage: đổi status/fork/label/ticket/resolved_by_op — ghi actor vào reason (audit)."""
    sets, params = [], []
    for col in ("status", "fork", "label", "ticket_ref", "resolved_by_op"):
        val = getattr(body, col)
        if val is not None:
            sets.append(f"{col} = %s")
            params.append(str(val) if col == "resolved_by_op" else val)
    if not sets:
        raise HTTPException(422, "không có trường nào để triage")
    changes = ", ".join(s.split(" =")[0] + "→" + str(p) for s, p in zip(sets, params))
    sets.append("reason = reason || %s")
    params.append(f"\n[triage {datetime.now().isoformat(timespec='seconds')} bởi {actor}: {changes}]")
    with db.tx() as conn:
        row = conn.execute(
            f"UPDATE conflict SET {', '.join(sets)} WHERE id = %s RETURNING id, status, fork, label",
            [*params, conflict_id],
        ).fetchone()
        if row is None:
            raise HTTPException(404, "conflict không tồn tại")
        return dict(row) | {"triaged_by": actor}


# ---------------------------------------------------------------------------
# Demand log (câu Tier D theo tần suất) — FR-14
# ---------------------------------------------------------------------------

@router.get("/demand", response_model=DemandOut)
def demand():
    with db.tx() as conn:
        rows = conn.execute(
            """SELECT question, count(*) AS count,
                      array_agg(DISTINCT audience::text) AS audiences,
                      max(created_at) AS last_asked
               FROM answer_log WHERE tier = 'D'
               GROUP BY question ORDER BY count DESC, last_asked DESC LIMIT 200"""
        ).fetchall()
        total = conn.execute("SELECT count(*) AS c FROM answer_log WHERE tier='D'").fetchone()["c"]
    return DemandOut(total_tier_d=total, items=[DemandItem(**r) for r in rows])


# ---------------------------------------------------------------------------
# Notifications digest + ack — FR-14, D-36
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=NotificationDigestOut)
def notifications(unacked_only: bool = Query(default=False)):
    with db.tx() as conn:
        rows = conn.execute(
            f"""SELECT id, op_id, affected_node, affected_doc, owner, severity, acked, created_at
                FROM notification {'WHERE NOT acked' if unacked_only else ''}
                ORDER BY severity = 'interruptive' DESC, created_at DESC"""
        ).fetchall()
    by_owner: dict[str, list[NotificationOut]] = {}
    for r in rows:
        by_owner.setdefault(r["owner"] or "(không có owner)", []).append(NotificationOut(**r))
    return NotificationDigestOut(
        total=len(rows),
        unacked=sum(1 for r in rows if not r["acked"]),
        by_owner=by_owner,
    )


@router.post("/notifications/{notification_id}/ack")
def notification_ack(notification_id: UUID, actor: str = Depends(require_actor)):
    with db.tx() as conn:
        row = conn.execute(
            "UPDATE notification SET acked = TRUE WHERE id = %s RETURNING id",
            [notification_id],
        ).fetchone()
        if row is None:
            raise HTTPException(404, "notification không tồn tại")
        return {"id": row["id"], "acked": True, "acked_by": actor}
