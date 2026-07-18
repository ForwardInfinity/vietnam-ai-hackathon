"""Fold engine — PURE FUNCTION (S4.5, D-23, D-24). KHÔNG import DB; test không cần Postgres.

Mô hình: overlay tất định. PASS 1 (windows.py) resolve cửa sổ từng op (op-nhắm-op, treo-theo-
sự-kiện). PASS 2: mỗi (node, nhánh scope) chia trục thời gian tại mọi biên cửa sổ; nội dung
một phân đoạn = base ⊕ các op phủ phân đoạn theo thứ tự canonical D-23:
    (precedence_rank@valid_from, valid_from, issued_date, seq, artifact_id, ingested_at)
Ngữ nghĩa op đúng 02 §3 (normative):
  amend       — text/heading mới govern trên cửa sổ op (body/heading theo target_part)
  insert      — node sinh bởi op: base = new_text, tồn tại đúng cửa sổ op insert
  repeal@node — status 'repealed' từ valid_from, vĩnh viễn, không hồi sinh
  suspend     — status 'suspended' trên cửa sổ; hết cửa sổ (close_window ratified) → hồi sinh;
                version active có thể KHÔNG BAO GIỜ tồn tại (k8-10 Đ8 TT39, D-24)
  repeal@op / close_window — đã xử lý ở PASS 1 (windows.py, INV-5)
  dinh_chinh  — thay text HỒI TỐ về ĐẦU cửa sổ của version bị đính chính (D-12)
  norm_decl   — không mutate node; phát NormEvent (D-08/D-09)
  blanket_derogation — KHÔNG mutate; seed conflict screening (D-14)
Hai op cùng đặt text trên một phân đoạn: tier-1 đã luật hóa (cấp trên thắng; sau-thắng-cùng-
cơ-quan); không phân định → ConflictCertificate cho node đó (conflict.py), KHÔNG chọn bừa.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from engine.conflict import certificate_for, default_precedence, precedence_rank, winning_op
from engine.model import (ArtifactInput, ConflictCertificate, CorpusFold, NodeInput, NormEvent,
                          ScreeningSeed, Version, as_utc_ts, digest_of, jsonable, sv)
from engine.scope import (applicability_matches, canonical_scope, complement, is_complement_of,
                          scope_hash, scopes_equal)
from engine.windows import Window, eligible_ops, min_end, pending_windows, resolve_windows

NODE_KINDS = {"amend", "insert", "suspend", "repeal", "dinh_chinh"}


def canonical_key(op: Any, artifacts: Mapping[str, ArtifactInput], precedence: Sequence[Any]):
    """Sort key canonical D-23 — thứ tự nạp file KHÔNG được quyết định luật (INV-3)."""
    a = artifacts[op.source_artifact]
    rank = precedence_rank(a.doc_type, a.issuer, op.valid_from, precedence)
    return (rank, op.valid_from, a.issued_date or date.min, op.seq,
            op.source_artifact, as_utc_ts(op.ingested_at))


def _sets_body(op: Any) -> bool:
    return sv(op.kind) in ("amend", "insert") and op.new_text is not None \
        and sv(op.target_part) == "body"


def _sets_heading(op: Any) -> bool:
    if sv(op.kind) not in ("amend", "insert"):
        return False
    return (sv(op.target_part) == "heading" and (op.new_heading or op.new_text) is not None) \
        or (sv(op.target_part) == "body" and op.new_heading is not None)


def _heading_text(op: Any) -> str | None:
    return op.new_heading if op.new_heading is not None else op.new_text


@dataclass
class _Branch:
    scope: dict | None            # None | DSL | {"complement_of": DSL}
    start: date
    end: date | None
    ops: list[Any] = field(default_factory=list)


@dataclass
class _Seg:
    a: date
    b: date | None
    heading: str | None
    body: str | None
    status: str
    prov: tuple[UUID, ...]


def _segments(branch: _Branch, base_h: str | None, base_b: str | None, node: NodeInput,
              windows: Mapping[UUID, Window], artifacts, precedence,
              ) -> tuple[list[_Seg], ConflictCertificate | None, list[str]]:
    notes: list[str] = []
    evs: list[tuple[Any, date, date | None]] = []
    for op in branch.ops:                                  # branch.ops giữ thứ tự canonical
        w = windows.get(op.id)
        if w is None:
            continue
        a = max(w.start, branch.start)
        b = min_end(w.end, branch.end)
        if b is not None and a >= b:
            continue
        evs.append((op, a, b))
    bounds = {branch.start} | {a for _, a, _ in evs} | {b for _, _, b in evs if b is not None}
    if branch.end is not None:
        bounds.add(branch.end)
    pts = sorted(d for d in bounds
                 if d >= branch.start and (branch.end is None or d <= branch.end))
    segs: list[_Seg] = []
    for i, a in enumerate(pts):
        b = pts[i + 1] if i + 1 < len(pts) else branch.end
        if b is not None and a >= b:
            continue
        cover = [op for op, wa, wb in evs if wa <= a and (wb is None or wb > a)]
        heading, body = base_h, base_b
        for setters, pick in ((tuple(o for o in cover if _sets_body(o)), "body"),
                              (tuple(o for o in cover if _sets_heading(o)), "heading")):
            if not setters:
                continue
            winner, incomp, ranks = winning_op(setters, artifacts, precedence)
            if winner is None:
                return [], certificate_for(node.id, incomp, ranks, artifacts, (a, b)), notes
            displaced = {ranks[o.id] for o in setters if ranks[o.id] != ranks[winner.id]}
            if displaced:
                notes.append(f"tier1-auto node={node.id} seg={a.isoformat()}: rank "
                             f"{ranks[winner.id]} thắng rank {sorted(displaced)} (cấp trên thắng)")
            if pick == "body":
                body = winner.new_text
            else:
                heading = _heading_text(winner)
        kinds = {sv(o.kind) for o in cover}
        status = "repealed" if "repeal" in kinds else ("suspended" if "suspend" in kinds
                                                       else "active")
        segs.append(_Seg(a, b, heading, body, status, tuple(o.id for o in cover)))
    merged: list[_Seg] = []
    for s in segs:
        p = merged[-1] if merged else None
        if p and p.b == s.a and (p.heading, p.body, p.status, p.prov) == \
                (s.heading, s.body, s.status, s.prov):
            p.b = s.b
        else:
            merged.append(s)
    return merged, None, notes


def _apply_dinh_chinh(segs: list[_Seg], dc_ops: Sequence[Any], notes: list[str]) -> None:
    """Hồi tố về ĐẦU cửa sổ của version bị đính chính (D-12) — không đổi biên cửa sổ."""
    for op in dc_ops:
        target = next((s for s in segs if s.a <= op.valid_from and
                       (s.b is None or op.valid_from < s.b)), None)
        if target is None:
            target = next((s for s in segs if s.a >= op.valid_from), segs[-1] if segs else None)
        if target is None:
            notes.append(f"dinh_chinh {op.id}: node không có version nào để đính chính — bỏ qua")
            continue
        if op.new_text is not None and sv(op.target_part) == "body":
            target.body = op.new_text
        if op.new_heading is not None or sv(op.target_part) == "heading":
            target.heading = _heading_text(op)
        target.prov = target.prov + (op.id,)


def fold_node(node: NodeInput, node_ops: Sequence[Any], windows: Mapping[UUID, Window],
              artifacts: Mapping[str, ArtifactInput], precedence: Sequence[Any],
              ) -> tuple[tuple[Version, ...] | ConflictCertificate, list[str]]:
    """Fold MỘT node (op đã sort canonical) → versions | certificate (KHÔNG chọn bừa)."""
    notes: list[str] = []
    phase1 = [o for o in node_ops if sv(o.kind) in ("amend", "insert", "suspend", "repeal")]
    phase2 = [o for o in node_ops if sv(o.kind) == "dinh_chinh"]
    inserts = [o for o in phase1 if sv(o.kind) == "insert"]
    if inserts:                                            # node sinh bởi op insert (02 §3)
        w0 = windows[inserts[0].id]
        start, node_end = w0.start, w0.end
        base_h, base_b = None, None
    else:
        eff = artifacts[node.artifact_id].effective_date
        if eff is None:
            return (), notes
        start, node_end = eff, None
        base_h, base_b = node.heading, node.body

    branches = [_Branch(scope=None, start=start, end=node_end)]
    for op in phase1:
        pred = canonical_scope(op.scope_predicate)
        if pred is None:
            for b in branches:
                b.ops.append(op)
            continue
        routed = False
        for b in branches:
            if b.scope is not None and scopes_equal(b.scope, pred):
                routed = True                              # cohort miễn trừ: giữ nguyên
            elif b.scope is not None and is_complement_of(b.scope, pred):
                b.ops.append(op)
                routed = True
        if routed:
            continue
        t = op.valid_from
        splits: list[_Branch] = []
        for b in branches:
            if b.scope is None and t >= b.start and (b.end is None or b.end > t):
                keep_end = b.end
                b.end = t
                splits.append(_Branch(scope=pred, start=t, end=keep_end, ops=list(b.ops)))
                splits.append(_Branch(scope=complement(pred), start=t, end=keep_end,
                                      ops=list(b.ops) + [op]))
        if splits:
            branches.extend(splits)
        else:
            notes.append(f"scope-split v1: op {op.id} predicate lồng nhánh đã tách — bỏ qua")

    out: list[Version] = []
    for br in branches:
        segs, cert, seg_notes = _segments(br, base_h, base_b, node, windows,
                                          artifacts, precedence)
        notes.extend(seg_notes)
        if cert is not None:
            return cert, notes
        _apply_dinh_chinh(segs, phase2, notes)
        sh = scope_hash(br.scope)
        out.extend(Version(node_id=node.id, version=0, heading=s.heading, body=s.body,
                           status=s.status, valid_from=s.a, valid_to=s.b,
                           scope_predicate=canonical_scope(br.scope), scope_hash=sh,
                           provenance=s.prov) for s in segs)
    out.sort(key=lambda v: (v.valid_from, v.scope_hash, v.status,
                            v.valid_to or date.max))
    return tuple(replace(v, version=i + 1) for i, v in enumerate(out)), notes


def fold_corpus(nodes: Iterable[NodeInput], ops: Iterable[Any],
                artifacts: Iterable[ArtifactInput] | Mapping[str, ArtifactInput],
                precedence: Sequence[Any] | None = None,
                k_cutoff: datetime | None = None) -> CorpusFold:
    """Fold toàn corpus tại K (D-02: chỉ op ratified có ingested_at <= K)."""
    arts = dict(artifacts) if isinstance(artifacts, Mapping) \
        else {a.id: a for a in artifacts}
    prec = list(precedence) if precedence is not None else default_precedence()
    elig = eligible_ops(list(ops), k_cutoff)
    windows, pending, closed = resolve_windows(elig)
    dated = [o for o in elig if o.valid_from is not None]
    skipped = [o for o in elig if o.valid_from is None]
    dated.sort(key=lambda o: canonical_key(o, arts, prec))

    by_node: dict[UUID, list[Any]] = defaultdict(list)
    for o in dated:
        if o.target_node is not None and sv(o.kind) in NODE_KINDS:
            by_node[o.target_node].append(o)

    cf = CorpusFold()
    notes = [f"op {o.id} kind={sv(o.kind)} thiếu valid_from — không áp được" for o in skipped]
    certs: list[ConflictCertificate] = []
    for node in sorted(nodes, key=lambda n: str(n.id)):
        if arts[node.artifact_id].is_oracle:
            continue                                       # VBHN: chỉ để diff (D-22, R-7)
        res, n_notes = fold_node(node, by_node.get(node.id, []), windows, arts, prec)
        notes.extend(n_notes)
        if isinstance(res, ConflictCertificate):
            certs.append(res)
        elif res:
            cf.versions[node.id] = res
    cf.certificates = tuple(sorted(certs, key=lambda c: (str(c.node_id), c.window_from)))
    cf.open_suspensions = pending_windows(pending)
    cf.closed_windows = tuple(sorted((a, b) for a, b in closed))
    cf.screening_seeds = tuple(
        ScreeningSeed(o.id, o.source_artifact, o.valid_from)
        for o in dated if sv(o.kind) == "blanket_derogation")
    cf.norm_events = tuple(
        NormEvent(norm_id=o.target_norm, source_artifact=o.source_artifact,
                  valid_from=o.valid_from, op_id=o.id)
        for o in dated if sv(o.kind) == "norm_decl" and o.target_norm is not None)
    cf.notes = tuple(notes)
    return cf


# --------------------------------------------------------------------------- helpers

def materialize_at(versions: Sequence[Version], as_of: date,
                   cohort: Any = None, status: str | None = None) -> list[Version]:
    """Version hiệu lực tại as_of (mọi nhánh scope khớp cohort; cohort thiếu ⇒ mọi nhánh)."""
    out = [v for v in versions
           if v.valid_from <= as_of and (v.valid_to is None or as_of < v.valid_to)
           and (status is None or v.status == status)
           and applicability_matches(v.scope_predicate, cohort)]
    return sorted(out, key=lambda v: v.version)


def active_intervals(versions: Sequence[Version]) -> list[tuple[date, date | None]]:
    """Khoảng operative (status active) — k8-10 Đ8 TT39 phải là [] (interval ∅)."""
    ivs = sorted((v.valid_from, v.valid_to) for v in versions if v.status == "active")
    merged: list[list] = []
    for a, b in ivs:
        if merged and merged[-1][1] is not None and merged[-1][1] >= a:
            merged[-1][1] = None if b is None else max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def ever_active(versions: Sequence[Version]) -> bool:
    return any(v.status == "active" and (v.valid_to is None or v.valid_to > v.valid_from)
               for v in versions)


def verify_tiling(versions_by_node: Mapping[UUID, Sequence[Version]]) -> list[str]:
    """INV-4: mỗi (node, scope_hash) cửa sổ không chồng lấn, phủ liên tục từ hiệu lực đầu;
    hợp mọi nhánh của node cũng phải liên tục (split không được để lỗ)."""
    problems: list[str] = []
    for node_id, versions in versions_by_node.items():
        by_scope: dict[str, list[Version]] = defaultdict(list)
        for v in versions:
            if v.valid_to is not None and v.valid_to <= v.valid_from:
                problems.append(f"{node_id}: cửa sổ rỗng/âm {v.valid_from}..{v.valid_to}")
            by_scope[v.scope_hash].append(v)
        for sh, vs in by_scope.items():
            vs = sorted(vs, key=lambda v: v.valid_from)
            for prev, cur in zip(vs, vs[1:]):
                if prev.valid_to is None or prev.valid_to != cur.valid_from:
                    problems.append(f"{node_id}/scope={sh or 'universal'}: "
                                    f"{prev.valid_from}..{prev.valid_to} ↛ {cur.valid_from}")
        spans = sorted((v.valid_from, v.valid_to) for v in versions)
        horizon = spans[0][0]
        for a, b in spans:
            if a > horizon:
                problems.append(f"{node_id}: lỗ phủ {horizon} → {a}")
                break
            if b is None:
                horizon = date.max
                break
            horizon = max(horizon, b)
    return problems


def state_digest(cf: CorpusFold) -> str:
    """Digest tất định toàn kết quả fold (INV-3/INV-9 — modulo run_id vì fold không có run_id)."""
    return digest_of({"versions": {str(k): v for k, v in cf.versions.items()},
                      "certificates": cf.certificates,
                      "open_suspensions": cf.open_suspensions,
                      "closed_windows": cf.closed_windows,
                      "screening_seeds": cf.screening_seeds,
                      "norm_events": cf.norm_events,
                      "notes": cf.notes})


def versions_digest(cf: CorpusFold) -> str:
    """Digest CHỈ effective state (dùng cho test blanket-không-mutate, D-14)."""
    return digest_of({"versions": {str(k): v for k, v in cf.versions.items()},
                      "certificates": cf.certificates})
