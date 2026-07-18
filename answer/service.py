"""Orchestrator: câu hỏi → Answer (S5 trọn đường ống) — interface cho F6.

    from answer.service import answer_question, SessionCtx
    ans = answer_question("Điều kiện vay vốn hiện nay?", SessionCtx(audience="employee"),
                          store=pg_store(conn))

Đường ống: compile (R-27) → candidate MỘT CỬA (R-28) → hybrid RRF (D-28) →
closure gate (R-29) → context pack + composer (R-30/31) → verifier cứng, regen 1
lần (R-32) → judge mềm κ-gate (R-33) → tier TOTAL (R-34) → freshness (R-35) →
audience (R-36) → answer_log (R-37/INV-10).

Chốt an toàn nằm trong CODE:
- INV-7: không code path nào render văn tổng hợp khi ¬hard_pass — Tier C/D
  dựng answer=[] từ trích dẫn ghim, KHÔNG chạm composer output.
- INV-8/INV-12: mọi text vào composer đều qua store một cửa (audience tại SQL).
- Mode pinpoint/history đi đường alias→timeline riêng (D-27); mode pending tách
  nhánh tương lai có nhãn, nội dung CODE-built (không LLM trên nhánh chưa hiệu lực).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from api.schemas import (Answer, Basis, CompiledQuestion, ConflictItem, PiecewiseBlock,
                         UpcomingChange)
from answer import freshness
from answer.compiler import SessionCtx, compile_question
from answer.compose import (Composer, ContextEntry, GatewayComposer, OfflineComposer,
                            assemble_banners, build_context_pack, build_piecewise_blocks,
                            citation_of, clarify_question_for, detect_branch_groups,
                            format_interval, provenance_vi, scope_desc)
from answer.judge_soft import judge_claims, judge_state
from answer.tiers import TierInputs, decide_tier
from answer.verify_hard import digit_runs, verify
from retrieval.closure import close_over
from retrieval.fuse import hybrid_search
from retrieval.query_builder import (ConflictRow, SnapshotRow, SnapshotStore,
                                     _cohort_dict, certain_match, entitlements_for)

__all__ = ["answer_question", "SessionCtx"]

_QUOTE_CHARS = 600  # trích dẫn ghim cho Tier C / bases


@dataclass
class Trace:
    """Bằng chứng từng stage cho adversarial test (INV-8, INV-12)."""
    cq: CompiledQuestion | None = None
    candidate_texts: list[str] = field(default_factory=list)
    fused_texts: list[str] = field(default_factory=list)
    closure_texts: list[str] = field(default_factory=list)
    context_pack_texts: list[str] = field(default_factory=list)
    composer_raw: str = ""
    log_record: dict[str, Any] | None = None

    def all_bytes(self) -> str:
        parts = (self.candidate_texts + self.fused_texts + self.closure_texts
                 + self.context_pack_texts + [self.composer_raw])
        if self.log_record is not None:
            import json
            parts.append(json.dumps(self.log_record, ensure_ascii=False, default=str))
        return "\n".join(parts)


def _default_composer() -> Composer:
    if os.getenv("LLM_OFFLINE", "").lower() in ("1", "true", "yes"):
        return OfflineComposer()
    if os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_COMPOSE_API_KEY"):
        return GatewayComposer()
    return OfflineComposer()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def answer_question(question: str, ctx: SessionCtx | None = None,
                    store: SnapshotStore | None = None,
                    composer: Composer | None = None,
                    judge_gateway=None, today: date | None = None,
                    return_trace: bool = False) -> Answer | tuple[Answer, Trace]:
    ctx = ctx or SessionCtx()
    today = today or date.today()
    trace = Trace()

    def _done(ans: Answer) -> Answer | tuple[Answer, Trace]:
        return (ans, trace) if return_trace else ans

    if store is None or store.run is None:
        return _done(_no_snapshot_answer(ctx, today))

    ent = entitlements_for(ctx.audience)
    cq = compile_question(question, ctx, known_doc_keys=store.doc_keys(ent), today=today)
    trace.cq = cq
    coverage_rows = store.coverage()
    in_cov = freshness.in_coverage(coverage_rows, cq.as_of, today)

    if cq.pinpoint or cq.mode == "history":
        return _done(_timeline_answer(question, cq, ctx, store, ent, coverage_rows,
                                      in_cov, trace))
    if cq.mode == "pending":
        return _done(_pending_answer(question, cq, ctx, store, ent, coverage_rows,
                                     in_cov, trace))

    # ---- retrieval một cửa + hybrid --------------------------------------
    rows = store.candidates(cq.as_of, cq.cohort, ent)
    trace.candidate_texts = [r.text for r in rows]
    fused = hybrid_search(rows, question)
    trace.fused_texts = [r.text for r in fused]

    if not fused:
        return _done(_tier_d(question, cq, ctx, store, coverage_rows, trace,
                             reason="Không tìm thấy căn cứ nào khớp câu hỏi trong trạng thái "
                                    "hiệu lực (retrieval floor). Câu hỏi được route tới chuyên gia."))

    flags: set[str] = set()
    selected = _select_branches(fused, rows, cq, flags)

    # ---- closure gate -----------------------------------------------------
    clo = close_over(selected, store, cq.as_of, cq.cohort, ent)
    flags |= clo.flags
    trace.closure_texts = [r.text for r in clo.rows]
    context_rows = clo.rows
    node_ids = {r.node_id for r in context_rows}

    if not clo.complete:
        return _done(_tier_d(question, cq, ctx, store, coverage_rows, trace,
                             reason="closure_incomplete: " + "; ".join(clo.reasons),
                             closure_complete=False, retrieval_floor=True))

    # ---- flags substrate --------------------------------------------------
    conflicts_touched = [c for c in store.open_conflicts()
                         if set(c.member_node_ids) & node_ids]
    open_conflicts = [c for c in conflicts_touched if c.open_at(cq.as_of)]
    resolved_conflicts = [c for c in conflicts_touched if not c.open_at(cq.as_of)]
    if open_conflicts:
        flags.add("in_conflict")
        if ctx.audience == "customer":  # R-36: conflict → escalate thay vì certificate
            return _done(_tier_d(question, cq, ctx, store, coverage_rows, trace,
                                 reason="Câu hỏi chạm vùng xung đột quy phạm đang mở — đã "
                                        "chuyển chuyên gia của ngân hàng hỗ trợ trực tiếp."))

    if store.consolidation_pending() & node_ids:
        flags.add("consolidation_pending")

    future_rows = store.pending_versions(cq.as_of, ent, node_ids=node_ids)
    if future_rows:
        flags.add("pending_change")

    susp = [s for s in store.suspensions_at(cq.as_of, ent)
            if s.pending_open and _in_family(s, context_rows)]
    if susp:
        flags.add("open_suspension")

    # ---- compose + verifier cứng (regen 1 lần) ---------------------------
    pack = build_context_pack(context_rows, store.ops_brief(
        [op for r in context_rows for op in r.provenance]))
    trace.context_pack_texts = [e.full_text for e in pack]
    context_texts = {e.ref: e.full_text for e in pack}
    q_numbers = digit_runs(question) | digit_runs(cq.as_of.isoformat()) \
        | digit_runs(cq.as_of.strftime("%d/%m/%Y"))

    composer = composer or _default_composer()
    out = composer.compose(cq, question, pack)
    trace.composer_raw = out.model_dump_json()
    if out.refusal:
        return _done(_tier_d(question, cq, ctx, store, coverage_rows, trace,
                             reason=f"Composer từ chối vì thiếu căn cứ: {out.refusal}",
                             composer_refusal=True, retrieval_floor=True))

    verdict = verify(out, context_texts, question_numbers=q_numbers)
    if not verdict.passed:
        out2 = composer.compose(cq, question, pack, feedback=verdict.feedback())
        trace.composer_raw = out2.model_dump_json()
        verdict2 = verify(out2, context_texts, question_numbers=q_numbers)
        if verdict2.passed:
            out, verdict = out2, verdict2
    hard_pass = verdict.passed

    # ---- judge mềm --------------------------------------------------------
    jstate = judge_state()
    judge_verdicts: list[dict[str, str]] = []
    judge_all_pass = False
    if hard_pass and jstate == "calibrated":
        judge_verdicts = judge_claims(out.claims, context_texts, gateway=judge_gateway)
        judge_all_pass = bool(judge_verdicts) and all(
            v["verdict"] == "entails" for v in judge_verdicts)

    decision = decide_tier(TierInputs(
        retrieval_floor=True, in_coverage=in_cov, closure_complete=True,
        composer_refusal=False, hard_pass=hard_pass, flags=frozenset(flags),
        judge_state=jstate, judge_all_pass=judge_all_pass))

    # ---- render (INV-7 nằm ở đây) ----------------------------------------
    branch_groups = detect_branch_groups(context_rows)
    clarify = clarify_question_for(branch_groups) if "cohort_ambiguous" in flags else None
    banners = assemble_banners(flags, decision.judge_capped, ctx.audience, clarify)

    if decision.tier in ("A", "B"):
        blocks = build_piecewise_blocks(out, pack)
        cited_refs = {r for c in out.claims for r in c.refs} | {b.ref for b in out.bases}
        bases = _bases_from_pack(pack, only_refs=cited_refs or None, with_quote=False,
                                 store=store)
    else:  # Tier C sources-only: KHÔNG một chữ nào từ composer (INV-7)
        blocks = []
        bases = _bases_from_pack(pack, only_refs=None, with_quote=True, store=store)

    conflict_items = _conflict_items(open_conflicts, resolved_conflicts, pack, cq.as_of, store)
    upcoming = _upcoming(future_rows)

    ans = Answer(
        tier=decision.tier, audience=ctx.audience, as_of=cq.as_of,
        as_known=ctx.as_known or store.run.k_cutoff,
        run_id=UUID(store.run.run_id), answer=blocks, bases=bases,
        conflicts=conflict_items, upcoming_changes=upcoming, banners=banners,
        coverage=freshness.attestations(coverage_rows))
    _log(ans, question, cq, ctx, store, out.claims if decision.tier in ("A", "B") else [],
         hard_pass, judge_verdicts, context_rows, open_conflicts, trace)
    return _done(ans)


# ---------------------------------------------------------------------------
# Nhánh piecewise theo scope (D-04): cohort xác quyết → đúng nhánh; thiếu → CẢ nhánh + flag
# ---------------------------------------------------------------------------

def _select_branches(fused: list[SnapshotRow], all_rows: list[SnapshotRow],
                     cq: CompiledQuestion, flags: set[str]) -> list[SnapshotRow]:
    cohort_d = _cohort_dict(cq.cohort)
    by_node: dict[str, list[SnapshotRow]] = {}
    for r in all_rows:
        by_node.setdefault(r.node_id, []).append(r)
    out: list[SnapshotRow] = []
    seen: set[tuple[str, int]] = set()
    for r in fused:
        branches = by_node.get(r.node_id, [r])
        if len({b.scope_hash for b in branches}) > 1:
            certain = [b for b in branches
                       if b.scope_predicate and certain_match(b.scope_predicate, cohort_d)]
            chosen = certain if certain else branches
            if not certain:
                flags.add("cohort_ambiguous")  # ranh giới scope mà thiếu cohort (R-27)
        else:
            chosen = [r]
        for b in chosen:
            if b.key not in seen:
                seen.add(b.key)
                out.append(b)
    return out


def _in_family(susp, context_rows: list[SnapshotRow]) -> bool:
    for r in context_rows:
        if susp.node_id == r.node_id:
            return True
        if susp.doc_key == r.doc_key and (susp.path.startswith(r.path + "/")
                                          or r.path.startswith(susp.path + "/")):
            return True
    return False


# ---------------------------------------------------------------------------
# Renderers phụ
# ---------------------------------------------------------------------------

def _quote(text: str, limit: int = _QUOTE_CHARS) -> str:
    t = " ".join(text.split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    return (cut[: cut.rfind(" ")] if " " in cut else cut) + " […]"


def _bases_from_pack(pack: list[ContextEntry], only_refs: set[str] | None,
                     with_quote: bool, store: SnapshotStore) -> list[Basis]:
    ops = store.ops_brief([op for e in pack for op in e.row.provenance])
    bases = []
    for e in pack:
        if only_refs is not None and e.ref not in only_refs:
            continue
        r = e.row
        bases.append(Basis(
            ref=e.ref, citation_vi=citation_of(r), doc_key=r.doc_key, path=r.path,
            node_id=UUID(r.node_id), version=r.version, valid_from=r.valid_from,
            valid_to=r.valid_to, status=r.status,
            quote=_quote(r.text) if with_quote else None,
            provenance_vi=provenance_vi(r, ops)))
    return bases





def _conflict_items(open_c: list[ConflictRow], resolved_c: list[ConflictRow],
                    pack: list[ContextEntry], as_of: date,
                    store: SnapshotStore) -> list[ConflictItem]:
    ref_by_node = {}
    for e in pack:
        ref_by_node.setdefault(e.row.node_id, e.ref)
    items = []
    for c in open_c:
        items.append(ConflictItem(
            conflict_id=_uuid_or_none(c.id), tier=c.tier, label=c.label,
            reason=f"[ĐANG MỞ tại {as_of.strftime('%d/%m/%Y')}] {c.reason} "
                   "Chưa có thẩm quyền phân xử — hệ không tự chọn một bên.",
            member_refs=[ref_by_node[n] for n in c.member_node_ids if n in ref_by_node]))
    for c in resolved_c:
        note = " — đã giải quyết"
        if c.resolved_by_op:
            brief = store.ops_brief([c.resolved_by_op]).get(c.resolved_by_op)
            if brief:
                when = f", hiệu lực {brief.valid_from.strftime('%d/%m/%Y')}" if brief.valid_from else ""
                note = f" — đã giải quyết bởi {brief.source_doc_key}{when}"
        items.append(ConflictItem(
            conflict_id=_uuid_or_none(c.id), tier=c.tier, label=c.label,
            reason=c.reason + note,
            member_refs=[ref_by_node[n] for n in c.member_node_ids if n in ref_by_node]))
    return items


def _upcoming(future_rows: list[SnapshotRow]) -> list[UpcomingChange]:
    return [UpcomingChange(
        effective_from=r.valid_from, doc_key=r.doc_key, node_path=r.path,
        description_vi=f"{citation_of(r)} có phiên bản mới hiệu lực từ "
                       f"{r.valid_from.strftime('%d/%m/%Y')}: {_quote(r.text, 200)}")
        for r in future_rows]


# ---------------------------------------------------------------------------
# Các nhánh trả lời đặc biệt
# ---------------------------------------------------------------------------

def _no_snapshot_answer(ctx: SessionCtx, today: date) -> Answer:
    return Answer(
        tier="D", audience=ctx.audience, as_of=ctx.as_of or today, as_known=ctx.as_known,
        run_id=None, refusal_reason=(
            "Chưa có trạng thái hiệu lực nào được compile (run_id=null) — hệ từ chối "
            "thay vì bịa; câu hỏi được route tới chuyên gia."))


def _tier_d(question: str, cq: CompiledQuestion, ctx: SessionCtx, store: SnapshotStore,
            coverage_rows, trace: Trace, reason: str, closure_complete: bool = True,
            retrieval_floor: bool = False, composer_refusal: bool = False) -> Answer:
    banners = assemble_banners(set(), judge_capped=False, audience=ctx.audience)
    ans = Answer(
        tier="D", audience=ctx.audience, as_of=cq.as_of,
        as_known=ctx.as_known or store.run.k_cutoff, run_id=UUID(store.run.run_id),
        banners=banners, coverage=freshness.attestations(coverage_rows),
        refusal_reason=reason)
    _log(ans, question, cq, ctx, store, [], False, [], [], [], trace)
    return ans


def _timeline_answer(question: str, cq: CompiledQuestion, ctx: SessionCtx,
                     store: SnapshotStore, ent, coverage_rows, in_cov,
                     trace: Trace) -> Answer:
    """Đường alias→timeline (D-27): thấy CẢ version treo/đóng/không-bao-giờ-active.
    Nội dung CODE-built từ substrate (verbatim) — hard_pass theo cấu trúc."""
    if cq.pinpoint:
        doc_key, _, path = cq.pinpoint.partition("#")
    else:  # history không địa chỉ: lấy node top-1 theo hybrid hiện hành
        rows_now = store.candidates(cq.as_of, cq.cohort, ent)
        fused = hybrid_search(rows_now, question)
        if not fused:
            return _tier_d(question, cq, ctx, store, coverage_rows, trace,
                           reason="Không xác định được điều khoản nào để dựng timeline.")
        doc_key, path = fused[0].doc_key, fused[0].path

    rows = store.timeline(doc_key, path, ent)
    trace.candidate_texts = [r.text for r in rows]
    if not rows:
        return _tier_d(question, cq, ctx, store, coverage_rows, trace,
                       reason=f"Địa chỉ {cq.pinpoint or f'{doc_key}#{path}'} không resolve "
                              "được trong snapshot (alias không có hoặc ngoài quyền đọc).")

    _STATUS_VI = {"active": "hiệu lực", "suspended": "NGƯNG HIỆU LỰC (treo)",
                  "repealed": "bị bãi bỏ"}
    ops = store.ops_brief([op for r in rows for op in r.provenance])
    blocks, bases = [], []
    for i, r in enumerate(rows, 1):
        blocks.append(PiecewiseBlock(
            interval_from=r.valid_from, interval_to=r.valid_to,
            cohort=scope_desc(r.scope_predicate) if r.scope_predicate else None,
            text_vi=f"[{_STATUS_VI.get(r.status, r.status)}] "
                    f"{format_interval(r.valid_from, r.valid_to)} — “{_quote(r.text, 300)}”"))
        bases.append(Basis(
            ref=f"[{i}]", citation_vi=citation_of(r), doc_key=r.doc_key, path=r.path,
            node_id=UUID(r.node_id), version=r.version, valid_from=r.valid_from,
            valid_to=r.valid_to, status=r.status, quote=_quote(r.text),
            provenance_vi=provenance_vi(r, ops)))

    never_active = all(r.status != "active" for r in rows)
    if never_active and any(r.status == "suspended" for r in rows):
        first = min(rows, key=lambda r: r.valid_from)
        blocks.insert(0, PiecewiseBlock(text_vi=(
            f"KẾT LUẬN: {citation_of(first)} CHƯA TỪNG có hiệu lực — bị ngưng từ "
            f"{first.valid_from.strftime('%d/%m/%Y')} trước khi kịp có hiệu lực; "
            "cửa sổ hoạt động rỗng.")))

    flags: set[str] = set()
    node_ids = {r.node_id for r in rows}
    if any(s.pending_open and s.node_id in node_ids
           for s in store.suspensions_at(cq.as_of, ent)):
        flags.add("open_suspension")
    conflicts_touched = [c for c in store.open_conflicts()
                         if set(c.member_node_ids) & node_ids]
    open_c = [c for c in conflicts_touched if c.open_at(cq.as_of)]
    if open_c:
        flags.add("in_conflict")

    jstate = judge_state()
    decision = decide_tier(TierInputs(
        retrieval_floor=True, in_coverage=in_cov, closure_complete=True,
        composer_refusal=False, hard_pass=True, flags=frozenset(flags),
        judge_state=jstate, judge_all_pass=False))
    banners = assemble_banners(flags, decision.judge_capped, ctx.audience)

    ans = Answer(
        tier=decision.tier, audience=ctx.audience, as_of=cq.as_of,
        as_known=ctx.as_known or store.run.k_cutoff, run_id=UUID(store.run.run_id),
        answer=blocks, bases=bases,
        conflicts=_conflict_items(open_c, [], [], cq.as_of, store),
        banners=banners, coverage=freshness.attestations(coverage_rows))
    _log(ans, question, cq, ctx, store,
         [], True, [], rows, open_c, trace)
    return ans


def _pending_answer(question: str, cq: CompiledQuestion, ctx: SessionCtx,
                    store: SnapshotStore, ent, coverage_rows, in_cov,
                    trace: Trace) -> Answer:
    """Mode pending: nhánh valid_from tương lai TÁCH RIÊNG có nhãn (R-28)."""
    future = store.pending_versions(cq.as_of, ent)
    trace.candidate_texts = [r.text for r in future]
    relevant = hybrid_search(future, question, top=8) if future else []
    current_rows = store.candidates(cq.as_of, cq.cohort, ent)
    current_hit = hybrid_search(current_rows, question, top=4)

    if not relevant and not current_hit:
        return _tier_d(question, cq, ctx, store, coverage_rows, trace,
                       reason="Không tìm thấy thay đổi sắp hiệu lực nào khớp câu hỏi.")

    blocks = [PiecewiseBlock(
        interval_from=r.valid_from, interval_to=r.valid_to, cohort=None,
        text_vi=f"[SẮP HIỆU LỰC từ {r.valid_from.strftime('%d/%m/%Y')}] "
                f"{citation_of(r)}: “{_quote(r.text, 300)}”") for r in relevant]
    if not relevant:
        blocks = [PiecewiseBlock(text_vi="Không có thay đổi sắp hiệu lực nào được ghi nhận "
                                         "cho chủ đề này trong phạm vi coverage bên dưới.")]
    ops = store.ops_brief([op for r in relevant for op in r.provenance])
    bases = [Basis(ref=f"[{i}]", citation_vi=citation_of(r), doc_key=r.doc_key, path=r.path,
                   node_id=UUID(r.node_id), version=r.version, valid_from=r.valid_from,
                   valid_to=r.valid_to, status=r.status, quote=_quote(r.text),
                   provenance_vi=provenance_vi(r, ops))
             for i, r in enumerate(relevant, 1)]

    flags = {"pending_change"} if relevant else set()
    decision = decide_tier(TierInputs(
        retrieval_floor=True, in_coverage=in_cov, closure_complete=True,
        composer_refusal=False, hard_pass=True, flags=frozenset(flags),
        judge_state=judge_state(), judge_all_pass=False))
    ans = Answer(
        tier=decision.tier, audience=ctx.audience, as_of=cq.as_of,
        as_known=ctx.as_known or store.run.k_cutoff, run_id=UUID(store.run.run_id),
        answer=blocks, bases=bases,
        upcoming_changes=_upcoming(relevant),
        banners=assemble_banners(flags, decision.judge_capped, ctx.audience),
        coverage=freshness.attestations(coverage_rows))
    _log(ans, question, cq, ctx, store, [], True, [], relevant, [], trace)
    return ans


# ---------------------------------------------------------------------------
# answer_log — MỌI câu (INV-10, R-37)
# ---------------------------------------------------------------------------

_AUDIENCE_T = {"customer": "public", "employee": "internal"}


def _log(ans: Answer, question: str, cq: CompiledQuestion, ctx: SessionCtx,
         store: SnapshotStore, claims, hard_pass: bool, judge_verdicts,
         retrieved_rows, open_conflicts, trace: Trace) -> None:
    jmap = {v["claim_id"]: v["verdict"] for v in judge_verdicts}
    rows = retrieved_rows if isinstance(retrieved_rows, list) else []

    def _nv_ref(ref: str) -> dict[str, Any]:
        """'[n]' → {node_id, version} — INV-10: từ answer_log + run_id tái dựng được
        nguyên văn mọi trích dẫn (node_version PK toàn cục)."""
        try:
            r = rows[int(ref.strip("[]")) - 1]
            return {"ref": ref, "node_id": r.node_id, "version": r.version}
        except (ValueError, IndexError):
            return {"ref": ref}

    record = {
        "session_id": ctx.session_id,
        "question": question,
        "audience": _AUDIENCE_T[ctx.audience],
        "as_of": cq.as_of,
        "as_known": ctx.as_known or store.run.k_cutoff,
        "tier": ans.tier,
        "claims": [{"text": c.text, "node_version_refs": [_nv_ref(r) for r in c.refs],
                    "hard_pass": hard_pass, "judge_verdict": jmap.get(c.id)}
                   for c in claims],
        "retrieved": [{"node_id": r.node_id, "version": r.version,
                       "doc_key": r.doc_key, "path": r.path} for r in rows],
        "conflicts": [c.id for c in open_conflicts] or None,
        "banners": [b.model_dump() for b in ans.banners],
        "run_id": store.run.run_id,
    }
    trace.log_record = record
    try:
        qa_id = store.write_answer_log(record)
        if qa_id:
            ans.qa_id = UUID(qa_id)
    except Exception:
        # log không được làm chết câu trả lời; demand log mất một dòng là lỗi vận hành
        pass


def _uuid_or_none(v: str | None) -> UUID | None:
    try:
        return UUID(v) if v else None
    except ValueError:
        return None
