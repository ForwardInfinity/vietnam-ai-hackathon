"""/v1/admin/ops* + /v1/admin/batches* — hàng đợi ratify hai đường (S4.4, D-19, INV-6).

Mọi endpoint đòi curator; mọi mutation đòi X-Actor (người ký). Các đường tạo op
ratified: (1) decision approve → ratified_by = actor; (2) batch → ratify_batch có
approved_by = actor + machine-verify từng op. KHÔNG có đường thứ ba (INV-6).
Op đã ratified BẤT BIẾN — edit bị 409; sửa = action supersede (op mới, D-20).
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api import db, integrations
from api.auth import require_actor, require_curator
from api.ratify_logic import (
    queue_sort_key,
    route_queue,
    spot_check_sample,
    unified_diff,
    validate_template,
    verify_op_against_template,
)
from api.view_models import (
    BatchOut,
    BatchRequest,
    BatchVerifyOut,
    DecisionOut,
    DecisionRequest,
    OpsQueueOut,
    QueueItem,
    SpotCheckItem,
    TargetView,
)

router = APIRouter(prefix="/admin", tags=["admin:ratify"], dependencies=[Depends(require_curator)])

_OP_STATUSES = ("proposed", "ratified", "rejected", "superseded")

# Cột op được phép edit khi còn proposed (curator materialize / sửa đề xuất — D-21)
_EDITABLE = {
    "kind", "target_node", "target_op", "target_norm", "target_part", "new_text",
    "new_heading", "valid_from", "valid_to", "valid_to_event", "scope_predicate",
    "risk_class", "confidence", "source_quote", "seq",
}


def _current_versions(conn, node_ids: list) -> dict[str, dict]:
    """node_id → version hiệu lực hôm nay (ưu tiên), fallback version mới nhất."""
    if not node_ids:
        return {}
    rows = conn.execute(
        """SELECT DISTINCT ON (node_id) node_id, version, heading, body, status
           FROM node_version WHERE node_id = ANY(%s::uuid[])
           ORDER BY node_id,
                    (CASE WHEN valid_from <= CURRENT_DATE
                          AND (valid_to IS NULL OR CURRENT_DATE < valid_to) THEN 0 ELSE 1 END),
                    version DESC""",
        [node_ids],
    ).fetchall()
    return {str(r["node_id"]): r for r in rows}


def _load_ops(conn, where_sql: str, params: list) -> list[dict]:
    return conn.execute(
        f"""SELECT o.*, sa.doc_key AS source_doc_key, sa.title AS source_doc_title,
                   tn.path AS target_path, ta.doc_key AS target_doc_key,
                   rb.approved_by AS batch_approved_by
            FROM op o
            JOIN artifact sa ON sa.id = o.source_artifact
            LEFT JOIN node tn ON tn.id = o.target_node
            LEFT JOIN artifact ta ON ta.id = tn.artifact_id
            LEFT JOIN ratify_batch rb ON rb.id = o.ratify_batch
            WHERE {where_sql}""",
        params,
    ).fetchall()


def _dinh_nghia_targets(conn, node_ids: list) -> set[str]:
    """R-15: target có inbound edge dinh_nghia ⇒ definitional ⇒ per-op."""
    if not node_ids:
        return set()
    rows = conn.execute(
        "SELECT DISTINCT dst_node FROM edge WHERE kind = 'dinh_nghia' AND dst_node = ANY(%s::uuid[])",
        [node_ids],
    ).fetchall()
    return {str(r["dst_node"]) for r in rows}


def _after_text(op: dict, current: str | None) -> str | None:
    if op["kind"] in ("amend", "insert", "dinh_chinh"):
        return op.get("new_text")
    if op["kind"] == "repeal":
        return ""  # đóng vĩnh viễn
    if op["kind"] == "suspend":
        return f"[NGƯNG HIỆU LỰC{' đến ' + str(op['valid_to']) if op.get('valid_to') else (' đến sự kiện: ' + op['valid_to_event'] if op.get('valid_to_event') else ' vô thời hạn')}]"
    return None


def _queue_item(op: dict, current: dict | None, dinh_nghia: set[str]) -> QueueItem:
    cur_body = current["body"] if current else None
    after = _after_text(op, cur_body)
    diff = None
    if op["target_node"] is not None:
        if op["target_part"] == "heading":
            diff = unified_diff(current["heading"] if current else None, op.get("new_heading"))
        else:
            diff = unified_diff(cur_body, after if after is not None else cur_body)
    op_row = {k: v for k, v in op.items()
              if k not in ("source_doc_key", "source_doc_title", "target_path",
                           "target_doc_key", "batch_approved_by")}
    return QueueItem(
        op=op_row,
        source_doc_key=op["source_doc_key"],
        source_doc_title=op["source_doc_title"],
        target=TargetView(
            node_id=op["target_node"],
            doc_key=op["target_doc_key"],
            path=op["target_path"],
            heading=current["heading"] if current else None,
            current_text=cur_body,
            current_version=current["version"] if current else None,
            current_status=current["status"] if current else None,
            target_op=op["target_op"],
            target_norm=op["target_norm"],
        ),
        diff=diff,
        queue=route_queue(op, str(op["target_node"]) in dinh_nghia),
        batch_approved_by=op["batch_approved_by"],
    )


@router.get("/ops", response_model=OpsQueueOut)
def ops_queue(status: str = Query(default="proposed")):
    """Queue op theo R-17: sort risk (definitional trước) → confidence tăng dần.
    status=ratified cho log INV-6: mỗi op truy ra người ký (per-op hoặc batch)."""
    if status not in _OP_STATUSES:
        raise HTTPException(422, f"status phải thuộc {_OP_STATUSES}")
    with db.tx() as conn:
        ops = _load_ops(conn, "o.status = %s", [status])
        target_ids = [o["target_node"] for o in ops if o["target_node"]]
        currents = _current_versions(conn, target_ids)
        dinh_nghia = _dinh_nghia_targets(conn, target_ids)
        ops.sort(key=queue_sort_key)
        items = [_queue_item(o, currents.get(str(o["target_node"])), dinh_nghia) for o in ops]
        return OpsQueueOut(status=status, total=len(items), items=items)


@router.post("/ops/{op_id}/decision", response_model=DecisionOut)
def op_decision(op_id: UUID, body: DecisionRequest, actor: str = Depends(require_actor)):
    """approve / reject / edit (chỉ khi proposed) / supersede (op ratified → op mới, D-20).

    INV-6: approve LUÔN ghi ratified_by=actor. Op ratified từ chối edit → 409 kèm hướng dẫn.
    """
    with db.tx() as conn:
        op = conn.execute("SELECT * FROM op WHERE id = %s", [op_id]).fetchone()
        if op is None:
            raise HTTPException(404, "op không tồn tại")

        if body.action == "approve":
            if op["status"] != "proposed":
                raise HTTPException(409, f"op đang status={op['status']} — chỉ approve được op proposed")
            conn.execute(
                "UPDATE op SET status='ratified', ratified_by=%s, ratified_at=now() WHERE id=%s",
                [actor, op_id],
            )
            result = DecisionOut(op_id=op_id, action="approve", status="ratified", actor=actor)

        elif body.action == "reject":
            if op["status"] != "proposed":
                raise HTTPException(409, f"op đang status={op['status']} — chỉ reject được op proposed")
            conn.execute(  # ratified_by ghi ACTOR CỦA QUYẾT ĐỊNH (audit); status nói rõ là rejected
                "UPDATE op SET status='rejected', ratified_by=%s, ratified_at=now() WHERE id=%s",
                [actor, op_id],
            )
            result = DecisionOut(op_id=op_id, action="reject", status="rejected", actor=actor, note=body.note)

        elif body.action == "edit":
            if op["status"] != "proposed":
                raise HTTPException(
                    409,
                    "Op đã "
                    + op["status"]
                    + " là BẤT BIẾN (INV-1/D-20) — không edit in-place. Dùng action=supersede: "
                    "tạo op mới thay thế, op cũ chuyển superseded.",
                )
            edits = {k: v for k, v in (body.edits or {}).items() if k in _EDITABLE}
            if not edits:
                raise HTTPException(422, f"edits rỗng hoặc ngoài cột cho phép: {sorted(_EDITABLE)}")
            if "scope_predicate" in edits and edits["scope_predicate"] is not None:
                edits["scope_predicate"] = json.dumps(edits["scope_predicate"])
            sets = ", ".join(f"{k} = %s" for k in edits)
            conn.execute(  # ghi dấu curator đã sửa đề xuất (extractor lineage)
                f"UPDATE op SET {sets}, extractor = %s WHERE id = %s",
                [*edits.values(), f"{op['extractor']}+curator:{actor}", op_id],
            )
            result = DecisionOut(op_id=op_id, action="edit", status="proposed", actor=actor)

        elif body.action == "supersede":
            if op["status"] != "ratified":
                raise HTTPException(409, "supersede chỉ áp cho op ratified (sửa op proposed thì dùng edit)")
            edits = {k: v for k, v in (body.edits or {}).items() if k in _EDITABLE}
            new_op = {**{k: op[k] for k in _EDITABLE}, **edits}
            if new_op.get("scope_predicate") is not None and not isinstance(new_op["scope_predicate"], str):
                new_op["scope_predicate"] = json.dumps(new_op["scope_predicate"])
            row = conn.execute(
                """INSERT INTO op (kind, source_artifact, source_node, source_quote, seq,
                                   target_node, target_op, target_norm, target_part,
                                   new_text, new_heading, valid_from, valid_to, valid_to_event,
                                   scope_predicate, risk_class, extractor, confidence, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'proposed')
                   RETURNING id""",
                [new_op["kind"], op["source_artifact"], op["source_node"], new_op["source_quote"],
                 new_op["seq"], new_op["target_node"], new_op["target_op"], new_op["target_norm"],
                 new_op["target_part"], new_op["new_text"], new_op["new_heading"],
                 new_op["valid_from"], new_op["valid_to"], new_op["valid_to_event"],
                 new_op["scope_predicate"], new_op["risk_class"],
                 f"curator:{actor}", new_op["confidence"]],
            ).fetchone()
            new_id = row["id"]
            conn.execute(  # transition duy nhất trigger cho phép: ratified → superseded
                "UPDATE op SET status='superseded', superseded_by=%s WHERE id=%s",
                [new_id, op_id],
            )
            result = DecisionOut(op_id=op_id, action="supersede", status="superseded",
                                 actor=actor, new_op_id=new_id)
        else:  # pragma: no cover — Pydantic Literal đã chặn
            raise HTTPException(422, "action không hợp lệ")

    if body.action == "approve":
        integrations.notify_blast_radius([str(op_id)])  # TODO(F4): None khi engine chưa merge
    return result


# ---------------------------------------------------------------------------
# Batch-ratify (D-19, R-16, FR-10)
# ---------------------------------------------------------------------------

def _verify_batch(conn, body: BatchRequest) -> tuple[list[dict], BatchVerifyOut]:
    tpl_err = validate_template(body.invariant_template)
    if tpl_err:
        return [], BatchVerifyOut(all_ok=False, results=[], template_error=tpl_err)
    if not body.op_ids:
        return [], BatchVerifyOut(all_ok=False, results=[], template_error="op_ids rỗng")

    ops = _load_ops(conn, "o.id = ANY(%s::uuid[])", [[str(i) for i in body.op_ids]])
    found = {str(o["id"]) for o in ops}
    missing = [str(i) for i in body.op_ids if str(i) not in found]
    results = [{"op_id": m, "ok": False, "reason": "op không tồn tại", "weak": False} for m in missing]

    currents = _current_versions(conn, [o["target_node"] for o in ops if o["target_node"]])
    dinh_nghia = _dinh_nghia_targets(conn, [o["target_node"] for o in ops if o["target_node"]])

    for op in ops:
        if op["status"] != "proposed":
            results.append({"op_id": str(op["id"]), "ok": False,
                            "reason": f"status={op['status']} — chỉ batch được op proposed", "weak": False})
            continue
        if route_queue(op, str(op["target_node"]) in dinh_nghia) != "batch_eligible":
            results.append({"op_id": str(op["id"]), "ok": False,
                            "reason": "op thuộc hàng per-op theo router R-15 (definitional/norm_decl/"
                                      "ngày cần phân loại) — không được rửa qua batch", "weak": False})
            continue
        cur = currents.get(str(op["target_node"]))
        vr = verify_op_against_template(
            body.invariant_template, op,
            current_text=cur["body"] if cur else None,
            target_doc_key=op["target_doc_key"],
        )
        results.append(vr.as_dict())

    all_ok = bool(results) and all(r["ok"] for r in results)
    return ops, BatchVerifyOut(all_ok=all_ok, results=results, template_error=None)


@router.post("/batches/verify", response_model=BatchVerifyOut)
def batch_verify(body: BatchRequest):
    """Dry-run: máy verify TỪNG op khớp invariant_template — chưa ký gì (bước 2 của FR-10)."""
    with db.tx() as conn:
        _, report = _verify_batch(conn, body)
        return report


@router.post("/batches", response_model=BatchOut)
def batch_create(body: BatchRequest, actor: str = Depends(require_actor)):
    """Khai template → machine-verify từng op → SIGN CẢ LỚP → spot-check ≥10% (R-16).

    Một op fail → 422, KHÔNG op nào được ratify (atomic). INV-6: approved_by = actor,
    op trong lô giữ ratified_by NULL — chữ ký truy qua ratify_batch.
    """
    with db.tx() as conn:
        ops, report = _verify_batch(conn, body)
        if not report.all_ok:
            raise HTTPException(422, detail={
                "message": "machine-verify fail — không op nào được ratify",
                "template_error": report.template_error,
                "results": report.results,
            })

        rate = max(body.spot_check_rate, 0.1)
        sample_ids = spot_check_sample([str(o["id"]) for o in ops], rate)
        batch_row = conn.execute(
            """INSERT INTO ratify_batch (invariant_template, description, approved_by,
                                         spot_check_rate, spot_checked)
               VALUES (%s, %s, %s, %s, %s::uuid[]) RETURNING id, approved_at""",
            [json.dumps(body.invariant_template), body.description, actor, rate, sample_ids],
        ).fetchone()
        batch_id = batch_row["id"]
        conn.execute(
            """UPDATE op SET status='ratified', ratify_batch=%s, ratified_at=now()
               WHERE id = ANY(%s::uuid[]) AND status='proposed'""",
            [batch_id, [str(o["id"]) for o in ops]],
        )
        by_id = {str(o["id"]): o for o in ops}
        spot_items = [
            SpotCheckItem(
                op_id=sid,
                source_quote=by_id[sid]["source_quote"],
                target_path=by_id[sid]["target_path"],
                target_doc_key=by_id[sid]["target_doc_key"],
                new_text=by_id[sid]["new_text"],
            )
            for sid in sample_ids
        ]
        result = BatchOut(
            batch_id=batch_id,
            approved_by=actor,
            ratified_count=len(ops),
            spot_check_rate=rate,
            spot_check=spot_items,
            verify=report,
            description=body.description,
        )
    integrations.notify_blast_radius([str(o["id"]) for o in ops])  # TODO(F4)
    return result


@router.get("/batches")
def batches_list():
    """Danh sách lô đã ký (INV-6 nhìn được: approved_by + spot_checked)."""
    with db.tx() as conn:
        rows = conn.execute(
            """SELECT rb.id, rb.invariant_template, rb.description, rb.approved_by,
                      rb.approved_at, rb.spot_check_rate, rb.spot_checked,
                      count(o.id) AS ops_count
               FROM ratify_batch rb LEFT JOIN op o ON o.ratify_batch = rb.id
               GROUP BY rb.id ORDER BY rb.approved_at DESC"""
        ).fetchall()
        return {"total": len(rows), "batches": rows}
