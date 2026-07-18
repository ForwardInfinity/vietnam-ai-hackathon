"""Closure theo edge có kiểu, re-projected tại as_of (R-29, D-29).

Từ top-12 seed: mở rộng depth ≤ 2, budget 24 node / 12k token, THỨ TỰ bắt buộc:
  (1) `ngoai_le`  — LUÔN, HAI CHIỀU (trả lời nêu quy tắc mà thiếu ngoại lệ là
       failure đắt thứ nhì sau staleness);
  (2) `chuyen_tiep` — khớp cohort; cohort mơ hồ → pull + flag `cohort_ambiguous`;
  (3) `dinh_nghia` — cho term có mặt trong context;
  (4) `tham_quyen` — khi cần (KHÔNG gate, thêm nếu còn budget).

`closure_complete` := không rơi mandatory vì budget ∧ không chạm mandatory
unresolved. ¬complete ⇒ Tier D `closure_incomplete` (caller quyết).
Edge `chu_de`(Norm) nuôi blast-radius — KHÔNG BAO GIỜ gate closure.

Mọi text kéo thêm đều đi qua store.versions_at (một cửa: active-tại-t + audience
+ cohort) — node đích bị ẩn theo audience mà edge là mandatory ⇒ incomplete
(degrade an toàn, không leak byte — INV-12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from retrieval.query_builder import EdgeRow, SnapshotRow, SnapshotStore, _cohort_dict

MAX_NODES = 24
MAX_TOKENS = 12_000
MAX_DEPTH = 2

MANDATORY_KINDS = ("ngoai_le", "chuyen_tiep", "dinh_nghia")


@dataclass
class ClosureNode:
    row: SnapshotRow
    depth: int
    via: str                      # 'seed' | edge kind


@dataclass
class ClosureResult:
    nodes: list[ClosureNode]
    complete: bool
    reasons: list[str] = field(default_factory=list)   # vì sao incomplete
    flags: set[str] = field(default_factory=set)        # cohort_ambiguous, open_suspension

    @property
    def rows(self) -> list[SnapshotRow]:
        return [n.row for n in self.nodes]


def _tokens(text: str) -> int:
    return len(text.split())


def _term_present(edge: EdgeRow, context_text: str) -> bool:
    """dinh_nghia mandatory khi term được định nghĩa CÓ MẶT trong context (D-29).
    raw_citation mang term; thiếu raw_citation → bảo thủ coi là có mặt."""
    if not edge.raw_citation:
        return True
    return edge.raw_citation.strip().lower() in context_text.lower()


def close_over(seeds: list[SnapshotRow], store: SnapshotStore, as_of: date,
               cohort: Any, entitlements: tuple[str, ...],
               max_nodes: int = MAX_NODES, max_tokens: int = MAX_TOKENS,
               max_depth: int = MAX_DEPTH) -> ClosureResult:
    cohort_d = _cohort_dict(cohort)
    cohort_unknown = not cohort_d

    nodes: list[ClosureNode] = []
    seen_keys: set[tuple[str, int]] = set()   # (node_id, version) — nhánh scope song song
    seen: set[str] = set()                     # node-level, cho dedup edge expansion
    token_used = 0
    reasons: list[str] = []
    flags: set[str] = set()

    def _try_add(row: SnapshotRow, depth: int, via: str, mandatory: bool) -> bool:
        nonlocal token_used
        if row.key in seen_keys:
            return True
        cost = _tokens(row.text)
        if len(nodes) + 1 > max_nodes or token_used + cost > max_tokens:
            if mandatory:
                reasons.append(f"budget_drop:{via}:{row.doc_key}#{row.path}")
            return False
        nodes.append(ClosureNode(row=row, depth=depth, via=via))
        seen_keys.add(row.key)
        seen.add(row.node_id)
        token_used += cost
        return True

    # Seeds: top-12 luôn vào trước (12 ≤ 24); nếu token budget cắt seed thì đó là
    # cắt phần retrieval, không phải rơi mandatory closure.
    for r in seeds:
        _try_add(r, depth=0, via="seed", mandatory=False)

    context_text = "\n".join(n.row.text for n in nodes)
    frontier: list[SnapshotRow] = [n.row for n in nodes]

    for depth in range(1, max_depth + 1):
        if not frontier:
            break
        frontier_ids = {r.node_id for r in frontier}
        frontier_vers = {}
        for r in frontier:  # một node có thể sống nhiều nhánh scope cùng lúc (D-04)
            frontier_vers.setdefault(r.node_id, set()).add(r.version)
        edges = store.edges_touching(frontier_ids)

        # Gom ứng viên theo phase; edge chỉ tính khi thuộc ĐÚNG phiên bản đang sống
        # (re-projection D-13: edge dẫn xuất theo phiên bản node nguồn).
        def _live_outbound(e: EdgeRow) -> bool:
            return e.src_version in frontier_vers.get(e.src_node, ())

        phases: list[tuple[str, list[tuple[EdgeRow, str]]]] = [
            ("ngoai_le", []), ("chuyen_tiep", []), ("dinh_nghia", []), ("tham_quyen", [])]
        phase_map = dict(phases)

        for e in edges:
            if e.kind == "ngoai_le":
                # HAI CHIỀU: outbound (rule → ngoại lệ) lẫn inbound (ngoại lệ → rule)
                if _live_outbound(e) and e.dst_node not in seen:
                    phase_map["ngoai_le"].append((e, "out"))
                elif e.dst_node in frontier_ids and e.src_node not in seen:
                    phase_map["ngoai_le"].append((e, "in"))
            elif e.kind in ("chuyen_tiep", "dinh_nghia", "tham_quyen"):
                if _live_outbound(e) and (e.dst_node is None or e.dst_node not in seen):
                    phase_map[e.kind].append((e, "out"))
            # chu_de / frontier: nuôi blast-radius / advisory — KHÔNG closure

        next_frontier: list[SnapshotRow] = []
        for kind, cand in phases:
            for e, direction in cand:
                mandatory = kind in MANDATORY_KINDS
                if kind == "dinh_nghia":
                    mandatory = _term_present(e, context_text)
                    if not mandatory:
                        continue  # term không có mặt → không cần kéo
                if kind == "chuyen_tiep" and cohort_unknown:
                    flags.add("cohort_ambiguous")  # mơ hồ → pull + flag (R-29)

                # unresolved (backlog R-10, confidence 0) chạm mandatory ⇒ incomplete
                if e.unresolved:
                    if mandatory:
                        reasons.append(f"unresolved:{kind}:{e.raw_citation or e.src_node}")
                    continue
                target = e.src_node if direction == "in" else e.dst_node
                if target is None:
                    # đích là Norm/frontier: danh tính chủ đề, không có text node để kéo
                    continue

                if not store.node_visible(target, entitlements):
                    if mandatory:
                        reasons.append(f"audience_hidden:{kind}:{target}")
                    continue

                versions = store.versions_at([target], as_of, cohort, entitlements).get(target, [])
                if not versions:
                    # không có version active tại as_of: treo/đóng/chưa hiệu lực —
                    # trạng thái hợp lệ, không phải closure thiếu; treo → flag
                    st = store.version_status_at(target, as_of, entitlements)
                    if st == "suspended":
                        flags.add("open_suspension")
                    continue
                for row in versions:  # nhiều nhánh scope → kéo cả (piecewise)
                    if _try_add(row, depth=depth, via=kind, mandatory=mandatory):
                        next_frontier.append(row)
                        context_text += "\n" + row.text

        frontier = next_frontier

    return ClosureResult(nodes=nodes, complete=not reasons, reasons=reasons, flags=flags)
