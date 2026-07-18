"""ratify.py — router hai hàng đợi + batch machine-verify (R-15, R-16, D-19). Backend — UI là F6.

Per-op review khi: risk definitional (target có inbound edge dinh_nghia) ∨ kind norm_decl
∨ ngày-cần-phân-loại-ngữ-nghĩa ∨ cờ đỏ (R-13…). Batch-eligible khi đủ 4 điều kiện CƠ HỌC:
rule↔LLM khớp · target resolve duy nhất · prescriptive · ngày đọc thẳng.

Op đã ratify BẤT BIẾN (D-20 — trigger DB enforce); sửa lỗi = op mới + superseded_by.
KHÔNG hàm nào ở đây tự ratify — chỉ phân loại, verify máy và ghi khi ĐÃ có chữ ký người
(INV-6: ratified_by/approved_by là người, machine-verify chỉ là điều kiện cần).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from ingest.model import ProposedOp


@dataclass
class RouteDecision:
    queue: str                       # 'per_op' | 'batch'
    risk_class: str                  # 'definitional' | 'prescriptive'
    reasons: list[str] = field(default_factory=list)


def classify_risk(op: ProposedOp, store: Any) -> str:
    """definitional ⟺ target có inbound edge dinh_nghia (R-15) ∨ đích là điều Giải thích
    từ ngữ (role definition)."""
    if op.target_node is not None:
        try:
            if store.has_inbound_dinh_nghia(op.target_node):
                return "definitional"
        except Exception:
            pass
        info = getattr(store, "node_info", lambda _x: None)(op.target_node)
        if info and info.get("role") == "definition":
            return "definitional"
    return "prescriptive"


def route_op(op: ProposedOp, store: Any, doc_effective: Any = None,
             llm_enabled: bool = True) -> RouteDecision:
    """Điền risk_class + queue vào op và trả quyết định (R-15)."""
    risk = classify_risk(op, store)
    reasons: list[str] = []

    if risk == "definitional":
        reasons.append("risk=definitional (inbound dinh_nghia)")
    if op.kind == "norm_decl":
        reasons.append("kind=norm_decl")
    if op.red_flags:
        reasons.append("cờ đỏ: " + ",".join(op.red_flags))

    date_direct = (op.valid_from is not None and doc_effective is not None
                   and op.valid_from == doc_effective
                   and "divergent_effective_date" not in op.red_flags)
    op.date_direct = date_direct
    if not date_direct:
        reasons.append("ngày hiệu lực cần phân loại ngữ nghĩa")

    per_op = bool(reasons)
    if not per_op:
        mechanical = (op.rule_llm_agree and llm_enabled
                      and op.target_unique
                      and risk == "prescriptive"
                      and date_direct)
        if not mechanical:
            if not (op.rule_llm_agree and llm_enabled):
                reasons.append("rule↔LLM chưa khớp")
            if not op.target_unique:
                reasons.append("target chưa resolve duy nhất")
            per_op = True

    op.risk_class = risk
    op.queue = "per_op" if per_op else "batch"
    return RouteDecision(queue=op.queue, risk_class=risk, reasons=reasons)


# ============================================================================
# Batch machine-verify (R-16) — verify TỪNG op khớp invariant_template
# ============================================================================

def machine_verify_op(op_row: dict[str, Any], template: dict[str, Any],
                      get_body: Callable[[UUID], str | None] | None = None) -> tuple[bool, str]:
    """op_row: dict cột bảng op (hoặc ProposedOp.__dict__). Template S4.4:
      {"pattern":"phrase_replace","from":X,"to":Y}
      {"pattern":"uniform_field_change","field_regex":R,"from":A,"to":B}
      {"pattern":"mass_repeal","target_doc_keys":[…]}
    """
    pattern = template.get("pattern")
    kind = op_row.get("kind")

    if pattern == "phrase_replace":
        frm, to = template.get("from", ""), template.get("to", "")
        if kind != "amend":
            return False, f"phrase_replace đòi kind=amend, gặp {kind}"
        if op_row.get("phrase_from") is not None:
            if op_row.get("phrase_from") == frm and op_row.get("phrase_to") == to:
                return True, "ok (phrase op materialize khớp from/to)"
            return False, "from/to của op không khớp template"
        new_text = op_row.get("new_text") or ""
        if to not in new_text:
            return False, "new_text không chứa cụm từ đích"
        if get_body is not None and op_row.get("target_node") is not None:
            old = get_body(op_row["target_node"])
            if old is not None:
                if old.replace(frm, to) != new_text:
                    return False, "new_text ≠ old_text.replace(from,to)"
                return True, "ok (đối chiếu old→new chính xác)"
        if frm in new_text:
            return False, "new_text vẫn còn cụm từ cũ"
        return True, "ok (kiểm new_text; thiếu old_text để đối chiếu đầy đủ)"

    if pattern == "uniform_field_change":
        field_re = template.get("field_regex", "")
        frm, to = str(template.get("from", "")), str(template.get("to", ""))
        if kind != "amend":
            return False, f"uniform_field_change đòi kind=amend, gặp {kind}"
        new_text = op_row.get("new_text") or ""
        matches = re.findall(field_re, new_text)
        if not matches:
            return False, f"new_text không khớp field_regex {field_re!r}"
        if any(frm in m for m in matches):
            return False, "new_text còn giá trị cũ trong field"
        if not any(to in m for m in matches):
            return False, "new_text không mang giá trị mới trong field"
        return True, "ok"

    if pattern == "mass_repeal":
        allowed = set(template.get("target_doc_keys", []))
        if kind != "repeal":
            return False, f"mass_repeal đòi kind=repeal, gặp {kind}"
        doc = op_row.get("target_doc_key")
        if doc is None:
            return False, "op thiếu target_doc_key"
        if doc not in allowed:
            return False, f"target doc {doc} ngoài danh sách template"
        return True, "ok"

    return False, f"pattern không hỗ trợ: {pattern}"


def spot_check_ids(op_ids: list[UUID], rate: float = 0.1) -> list[UUID]:
    """Chọn tất định ≥ rate (và ≥1) op để người spot-check — sort theo str(id) cho ổn định."""
    if not op_ids:
        return []
    k = max(1, int(len(op_ids) * rate + 0.9999))
    return sorted(op_ids, key=str)[:k]


# ============================================================================
# Ghi DB — proposed ops + batch (chỉ chạy khi có chữ ký người — INV-6)
# ============================================================================

def insert_proposed_op(conn: Any, op: ProposedOp, source_artifact: str) -> None:
    """Ghi op status='proposed'. Tiền đề: op.check_ok() — CHECK của bảng op đòi đúng
    1 target (trừ blanket). Op unresolved (0 target) KHÔNG ghi được và KHÔNG bịa target:
    orchestrator giữ chúng trong IngestResult.backlog để curator xử lý (R-11 rule 5)."""
    conn.execute(
        """INSERT INTO op (id, kind, source_artifact, source_node, source_quote, seq,
                           target_node, target_op, target_norm, target_part,
                           new_text, new_heading, valid_from, valid_to, valid_to_event,
                           scope_predicate, risk_class, extractor, confidence, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s, %s, %s, %s, 'proposed')""",
        (op.id, op.kind, source_artifact, op.source_node, op.source_quote, op.seq,
         op.target_node, op.target_op, op.target_norm, op.target_part,
         op.new_text, op.new_heading, op.valid_from, op.valid_to, op.valid_to_event,
         _jsonb(op.scope_predicate), op.risk_class, op.extractor, op.confidence))


def _jsonb(obj: Any) -> Any:
    if obj is None:
        return None
    import json
    from psycopg.types.json import Jsonb
    try:
        return Jsonb(obj)
    except Exception:
        return json.dumps(obj, ensure_ascii=False)


def create_batch(conn: Any, op_ids: list[UUID], invariant_template: dict[str, Any],
                 approved_by: str, description: str | None = None,
                 get_body: Callable[[UUID], str | None] | None = None,
                 spot_check_rate: float = 0.1) -> dict[str, Any]:
    """Batch-ratify D-19: máy verify TỪNG op khớp template; op fail bị LOẠI khỏi batch
    (ở lại queue per-op); op pass được ratify DƯỚI chữ ký `approved_by` (người).
    Trả {batch_id, ratified[], failed[{op_id, reason}], spot_check[]}."""
    rows = conn.execute(
        """SELECT o.id, o.kind, o.new_text, o.target_node, a.doc_key
           FROM op o LEFT JOIN node n ON n.id = o.target_node
                     LEFT JOIN artifact a ON a.id = n.artifact_id
           WHERE o.id = ANY(%s) AND o.status = 'proposed'""", (op_ids,)).fetchall()
    verified: list[UUID] = []
    failed: list[dict[str, Any]] = []
    for (oid, kind, new_text, target_node, doc_key) in rows:
        ok, reason = machine_verify_op(
            {"id": oid, "kind": kind, "new_text": new_text,
             "target_node": target_node, "target_doc_key": doc_key},
            invariant_template, get_body)
        (verified.append(oid) if ok else failed.append({"op_id": oid, "reason": reason}))
    if not verified:
        return {"batch_id": None, "ratified": [], "failed": failed, "spot_check": []}
    spot = spot_check_ids(verified, spot_check_rate)
    row = conn.execute(
        """INSERT INTO ratify_batch (invariant_template, description, approved_by,
                                     spot_check_rate, spot_checked)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (_jsonb(invariant_template), description, approved_by, spot_check_rate,
         spot)).fetchone()
    batch_id = row[0]
    conn.execute(
        """UPDATE op SET status='ratified', ratified_by=%s, ratified_at=now(),
                         ratify_batch=%s
           WHERE id = ANY(%s) AND status='proposed'""",
        (approved_by, batch_id, verified))
    return {"batch_id": batch_id, "ratified": verified, "failed": failed, "spot_check": spot}


def ratify_op(conn: Any, op_id: UUID, curator: str,
              edits: dict[str, Any] | None = None) -> None:
    """Per-op approve (R-17 backend): edit trước khi ratify được phép vì op còn proposed;
    chữ ký người bắt buộc (INV-6)."""
    if edits:
        allowed = {"kind", "target_node", "target_op", "target_norm", "target_part",
                   "new_text", "new_heading", "valid_from", "valid_to", "valid_to_event",
                   "scope_predicate", "risk_class"}
        sets = [f"{k} = %s" for k in edits if k in allowed]
        vals = [_jsonb(v) if k == "scope_predicate" else v
                for k, v in edits.items() if k in allowed]
        if sets:
            conn.execute(f"UPDATE op SET {', '.join(sets)} WHERE id = %s AND status='proposed'",
                         (*vals, op_id))
    conn.execute(
        """UPDATE op SET status='ratified', ratified_by=%s, ratified_at=now()
           WHERE id = %s AND status='proposed'""", (curator, op_id))


def reject_op(conn: Any, op_id: UUID, curator: str) -> None:
    conn.execute("UPDATE op SET status='rejected', ratified_by=%s WHERE id=%s AND status='proposed'",
                 (curator, op_id))
