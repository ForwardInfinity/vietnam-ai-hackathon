"""Query builder MỘT CỬA cho snapshot (R-28, D-27, D-44, INV-12).

MỌI truy vấn đọc `node_version` của TOÀN HỆ đi qua module này — không file nào
khác được SELECT trên snapshot (test cấu trúc quét source bảo đảm điều đó).

Predicate duy nhất cho candidate set (R-28):
    run_id pinned ∧ retrievable ∧ status='active' ∧ hiệu-lực-tại-t
    ∧ scope-khớp-cohort (cohort thiếu ⇒ match mọi nhánh) ∧ audience ∈ entitlements

Đường riêng (D-27):
  - pinpoint/history: alias→timeline — thấy CẢ version treo/đã đóng, vẫn pinned
    run + audience filter + loại node amending/oracle (retrievable).
  - pending: nhánh valid_from tương lai tách riêng, dán nhãn — không trộn vào
    candidate set hiện hành.

Hai hiện thân cùng một ngữ nghĩa: PgStore (SQL — sản phẩm) và MemStore (thuần
Python — unit test + demo offline). Bảng chân trị predicate chạy trên CẢ HAI để
chứng minh chúng trùng nhau.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Protocol

# ---------------------------------------------------------------------------
# Audience → entitlements (D-44, R-36): lọc Ở TẦNG truy vấn, không rải endpoint
# ---------------------------------------------------------------------------

ENTITLEMENTS: dict[str, tuple[str, ...]] = {
    "customer": ("public",),
    "employee": ("public", "internal"),
    # role vận hành substrate (admin console F6) — thấy cả restricted
    "curator": ("public", "internal", "restricted"),
}


def entitlements_for(audience: str) -> tuple[str, ...]:
    """Persona/role → tập audience_t được đọc. Role lạ → ValueError (không đoán quyền)."""
    try:
        return ENTITLEMENTS[audience]
    except KeyError:
        raise ValueError(f"audience không hợp lệ: {audience!r}") from None


# ---------------------------------------------------------------------------
# Row shapes — hàng snapshot trả ra từ một cửa
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotRow:
    node_id: str
    version: int
    heading: str | None
    body: str
    status: str                    # nv_status_t
    valid_from: date
    valid_to: date | None          # nửa-mở [from, to)
    scope_predicate: dict[str, Any] | None
    scope_hash: str
    provenance: tuple[str, ...]
    run_id: str
    path: str
    role: str                      # node_role_t
    artifact_id: str
    doc_key: str
    audience: str                  # audience_t của artifact
    title: str | None = None
    retrievable: bool = True
    embedding: tuple[float, ...] | None = None

    @property
    def key(self) -> tuple[str, int]:
        return (self.node_id, self.version)

    @property
    def text(self) -> str:
        head = (self.heading or "").strip()
        return f"{head}\n{self.body}".strip()


@dataclass(frozen=True)
class EdgeRow:
    src_node: str
    src_version: int
    kind: str                      # edge_kind_t
    dst_node: str | None = None
    dst_norm: str | None = None
    frontier_ref: str | None = None
    raw_citation: str | None = None
    confidence: float = 1.0

    @property
    def unresolved(self) -> bool:
        """Cả 3 đích NULL (backlog R-10) hoặc confidence 0 — chưa resolve."""
        return (self.dst_node is None and self.dst_norm is None
                and self.frontier_ref is None) or self.confidence == 0.0


@dataclass(frozen=True)
class ConflictRow:
    id: str
    member_node_ids: tuple[str, ...]
    tier: int
    label: str | None
    reason: str
    status: str
    resolved_by_op: str | None = None
    resolution_valid_from: date | None = None   # valid_from của op giải (NQ01…)

    def open_at(self, as_of: date) -> bool:
        """Mở tại as_of: status open, HOẶC đã resolved nhưng op giải chưa hiệu
        lực tại as_of (Đ468 vs TT39 trước NQ01/2019 — 02 §6.2)."""
        if self.status == "open":
            return True
        if self.status == "resolved" and self.resolution_valid_from is not None:
            return as_of < self.resolution_valid_from
        return False


@dataclass(frozen=True)
class CoverageRow:
    channel: str
    last_seq: str | None
    last_checked: datetime | None


@dataclass(frozen=True)
class SuspensionRef:
    """Metadata node đang treo (KHÔNG mang body vào banner — INV-8)."""
    node_id: str
    doc_key: str
    path: str
    valid_from: date
    valid_to: date | None
    pending_open: bool             # còn pending_event open_suspension mở


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    k_cutoff: datetime | None = None


@dataclass(frozen=True)
class OpBrief:
    id: str
    kind: str
    source_doc_key: str
    valid_from: date | None


# ---------------------------------------------------------------------------
# Applicability DSL đóng (D-25) — cohort thiếu ⇒ match mọi nhánh (R-28)
# ---------------------------------------------------------------------------

_SCOPE_FIELDS = ("contract_signed_before", "not_amended_on_or_after", "entity_class")


def _as_date(v: Any) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def applicability_matches(scope: dict[str, Any] | None, cohort: dict[str, Any] | None) -> bool:
    """Version scope có thể áp cho cohort không (bảo thủ: không loại khi thiếu dữ kiện).

    - scope NULL/rỗng → áp mọi chủ thể.
    - cohort thiếu field tương ứng → KHÔNG loại nhánh (piecewise mặc định D-04).
    - contract_signed_before: cohort.csb ≤ scope.csb ⇒ chắc chắn thuộc nhánh.
    - not_amended_on_or_after: cohort.naooa ≤ scope.naooa ⇒ thỏa.
    - entity_class: bằng nhau.
    """
    if not scope:
        return True
    cohort = cohort or {}
    for fld in _SCOPE_FIELDS:
        sv = scope.get(fld)
        if sv is None:
            continue
        cv = cohort.get(fld)
        if cv is None:
            continue  # thiếu dữ kiện → match nhánh (piecewise sẽ xử lý)
        if fld == "entity_class":
            if str(cv) != str(sv):
                return False
        else:
            if _as_date(cv) > _as_date(sv):  # type: ignore[operator]
                return False
    return True


def certain_match(scope: dict[str, Any] | None, cohort: dict[str, Any] | None) -> bool:
    """Cohort có ĐỦ dữ kiện xác quyết thuộc nhánh scope này (không nhờ bảo thủ)."""
    if not scope:
        return True
    cohort = cohort or {}
    for fld in _SCOPE_FIELDS:
        sv = scope.get(fld)
        if sv is None:
            continue
        if cohort.get(fld) is None:
            return False
    return applicability_matches(scope, cohort)


def _cohort_dict(cohort: Any) -> dict[str, Any]:
    if cohort is None:
        return {}
    if hasattr(cohort, "model_dump"):
        return {k: v for k, v in cohort.model_dump().items() if v is not None}
    return {k: v for k, v in dict(cohort).items() if v is not None}


# ---------------------------------------------------------------------------
# Surface path helper ('dieu:8/khoan:2' → 'khoản 2 Điều 8') — dùng cho index/citation
# ---------------------------------------------------------------------------

_UNIT_VI = {"dieu": "Điều", "khoan": "khoản", "diem": "điểm", "tiet": "tiết",
            "phuluc": "Phụ lục", "muc": "Mục", "chuong": "Chương"}


def surface_of_path(path: str) -> str:
    parts = []
    for seg in path.split("/"):
        unit, _, label = seg.partition(":")
        parts.append(f"{_UNIT_VI.get(unit, unit)} {label}".strip())
    return " ".join(reversed(parts))  # 'khoản 2 Điều 8' — thứ tự trích dẫn VN


# ---------------------------------------------------------------------------
# SQL — predicate MỘT CỬA (R-28). Mọi mảnh WHERE bắt buộc nằm ở hằng dưới đây.
# ---------------------------------------------------------------------------

_SELECT = """
SELECT nv.node_id::text, nv.version, nv.heading, nv.body, nv.status::text,
       nv.valid_from, nv.valid_to, nv.scope_predicate, nv.scope_hash,
       nv.provenance::text[], nv.run_id::text,
       n.path, n.role::text, n.artifact_id, a.doc_key, a.audience::text, a.title,
       nv.retrievable
FROM node_version nv
JOIN node n     ON n.id = nv.node_id
JOIN artifact a ON a.id = n.artifact_id
"""

# Mảnh scope: version scope NULL → áp mọi chủ thể; field cohort NULL → không loại nhánh
_SCOPE_MATCH_SQL = """
  AND (nv.scope_predicate IS NULL OR (
        ((nv.scope_predicate->>'contract_signed_before') IS NULL
          OR %(csb)s::date IS NULL
          OR %(csb)s::date <= (nv.scope_predicate->>'contract_signed_before')::date)
    AND ((nv.scope_predicate->>'not_amended_on_or_after') IS NULL
          OR %(naooa)s::date IS NULL
          OR %(naooa)s::date <= (nv.scope_predicate->>'not_amended_on_or_after')::date)
    AND ((nv.scope_predicate->>'entity_class') IS NULL
          OR %(entity_class)s::text IS NULL
          OR (nv.scope_predicate->>'entity_class') = %(entity_class)s::text)
  ))
"""

_AUDIENCE_SQL = "  AND a.audience::text = ANY(%(entitlements)s)\n"

# Candidate set hiện hành — predicate duy nhất (R-28)
CANDIDATE_SQL = (
    _SELECT
    + """WHERE nv.run_id = %(run_id)s
  AND nv.retrievable
  AND nv.status = 'active'
  AND nv.valid_from <= %(as_of)s
  AND (nv.valid_to IS NULL OR %(as_of)s < nv.valid_to)
"""
    + _SCOPE_MATCH_SQL
    + _AUDIENCE_SQL
    + "ORDER BY a.doc_key, n.path, nv.scope_hash, nv.version"
)

# Nhánh pending (mode pending / phát hiện thay đổi sắp hiệu lực) — TÁCH RIÊNG, có nhãn
PENDING_SQL = (
    _SELECT
    + """WHERE nv.run_id = %(run_id)s
  AND nv.retrievable
  AND nv.status = 'active'
  AND nv.valid_from > %(as_of)s
  AND (%(node_ids)s::text[] IS NULL OR nv.node_id::text = ANY(%(node_ids)s))
"""
    + _SCOPE_MATCH_SQL
    + _AUDIENCE_SQL
    + "ORDER BY nv.valid_from, a.doc_key, n.path"
)

# Timeline theo alias (D-27): mọi version, kể cả suspended/repealed/không-bao-giờ-active
TIMELINE_SQL = (
    _SELECT
    + """WHERE nv.run_id = %(run_id)s
  AND nv.retrievable
  AND a.doc_key = %(doc_key)s
  AND (n.id IN (SELECT al.node_id FROM alias al
                WHERE al.doc_key = %(doc_key)s AND al.path = %(path)s)
       OR n.path = %(path)s)
"""
    + _AUDIENCE_SQL
    + "ORDER BY nv.valid_from, nv.version"
)

# Re-projection cho closure: version active tại as_of của một tập node
VERSIONS_AT_SQL = (
    _SELECT
    + """WHERE nv.run_id = %(run_id)s
  AND nv.retrievable
  AND nv.status = 'active'
  AND nv.node_id::text = ANY(%(node_ids)s)
  AND nv.valid_from <= %(as_of)s
  AND (nv.valid_to IS NULL OR %(as_of)s < nv.valid_to)
"""
    + _SCOPE_MATCH_SQL
    + _AUDIENCE_SQL
)

# Trạng thái node tại as_of (không lấy body — dùng cho cờ treo/đóng, INV-8 an toàn)
STATUS_AT_SQL = """
SELECT nv.status::text
FROM node_version nv JOIN node n ON n.id = nv.node_id JOIN artifact a ON a.id = n.artifact_id
WHERE nv.run_id = %(run_id)s AND nv.node_id::text = %(node_id)s
  AND nv.valid_from <= %(as_of)s AND (nv.valid_to IS NULL OR %(as_of)s < nv.valid_to)
  AND a.audience::text = ANY(%(entitlements)s)
ORDER BY nv.status = 'active' DESC LIMIT 1
"""

SUSPENSIONS_SQL = """
SELECT nv.node_id::text, a.doc_key, n.path, nv.valid_from, nv.valid_to,
       EXISTS (SELECT 1 FROM pending_event pe JOIN op o ON o.id = pe.ref
               WHERE pe.kind = 'open_suspension' AND pe.status = 'open'
                 AND o.id::text = ANY(nv.provenance::text[])) AS pending_open
FROM node_version nv JOIN node n ON n.id = nv.node_id JOIN artifact a ON a.id = n.artifact_id
WHERE nv.run_id = %(run_id)s AND nv.status = 'suspended'
  AND nv.valid_from <= %(as_of)s AND (nv.valid_to IS NULL OR %(as_of)s < nv.valid_to)
  AND a.audience::text = ANY(%(entitlements)s)
"""

EDGES_SQL = """
SELECT e.src_node::text, e.src_version, e.kind::text, e.dst_node::text, e.dst_norm::text,
       e.frontier_ref, e.raw_citation, e.confidence
FROM edge e
WHERE e.src_node::text = ANY(%(node_ids)s) OR e.dst_node::text = ANY(%(node_ids)s)
"""

CONFLICTS_SQL = """
SELECT c.id::text, c.member_versions, c.tier, c.label::text, c.reason, c.status::text,
       c.resolved_by_op::text, o.valid_from AS resolution_valid_from
FROM conflict c LEFT JOIN op o ON o.id = c.resolved_by_op
"""

NODE_AUDIENCE_SQL = """
SELECT n.id::text, a.audience::text FROM node n JOIN artifact a ON a.id = n.artifact_id
WHERE n.id::text = ANY(%(node_ids)s)
"""

CONSOLIDATION_SQL = "SELECT node_id::text FROM v_consolidation_pending WHERE node_id IS NOT NULL"

COVERAGE_SQL = "SELECT channel, last_seq, last_checked FROM coverage ORDER BY channel"

DOC_KEYS_SQL = "SELECT doc_key FROM artifact WHERE NOT is_oracle AND audience::text = ANY(%(entitlements)s) ORDER BY doc_key"

OPS_BRIEF_SQL = """
SELECT o.id::text, o.kind::text, a.doc_key, o.valid_from
FROM op o JOIN artifact a ON a.id = o.source_artifact
WHERE o.id::text = ANY(%(op_ids)s)
"""

# R-19 (hook on_snapshot_written — dùng bởi retrieval.dense trong transaction replay F4)
EMBEDDING_BACKLOG_SQL = """
SELECT nv.node_id::text, nv.version, coalesce(nv.heading,'') || E'\n' || coalesce(nv.body,'')
FROM node_version nv
WHERE nv.run_id = %(run_id)s AND nv.retrievable AND nv.embedding IS NULL
"""

EMBEDDING_WRITE_SQL = """
UPDATE node_version SET embedding = %(vec)s::vector
WHERE node_id = %(node_id)s AND version = %(version)s
"""


def embedding_backlog(conn, run_id) -> list[tuple[str, int, str]]:
    return list(conn.execute(EMBEDDING_BACKLOG_SQL, {"run_id": run_id}).fetchall())


def write_embedding(conn, node_id: str, version: int, vec: list[float]) -> None:
    """CHỈ gọi trong transaction replay của F4 (guard lawstate.replay — R-1)."""
    literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    conn.execute(EMBEDDING_WRITE_SQL, {"vec": literal, "node_id": node_id, "version": version})


LATEST_RUN_SQL = """
SELECT run_id::text, k_cutoff FROM replay_run
WHERE %(as_known)s::timestamptz IS NULL OR k_cutoff <= %(as_known)s::timestamptz
ORDER BY k_cutoff DESC NULLS LAST LIMIT 1
"""

ANSWER_LOG_INSERT_SQL = """
INSERT INTO answer_log (session_id, question, audience, as_of, as_known, tier,
                        claims, retrieved, conflicts, banners, run_id)
VALUES (%(session_id)s, %(question)s, %(audience)s::audience_t, %(as_of)s, %(as_known)s,
        %(tier)s, %(claims)s::jsonb, %(retrieved)s::jsonb, %(conflicts)s::uuid[],
        %(banners)s::jsonb, %(run_id)s)
RETURNING qa_id::text
"""


# ---------------------------------------------------------------------------
# Store protocol — interface duy nhất mà retrieval/answering nhìn thấy snapshot
# ---------------------------------------------------------------------------

class SnapshotStore(Protocol):
    run: RunInfo | None

    def candidates(self, as_of: date, cohort: Any, entitlements: tuple[str, ...]) -> list[SnapshotRow]: ...
    def versions_at(self, node_ids: Iterable[str], as_of: date, cohort: Any,
                    entitlements: tuple[str, ...]) -> dict[str, list[SnapshotRow]]: ...
    def pending_versions(self, as_of: date, entitlements: tuple[str, ...],
                         node_ids: Iterable[str] | None = None) -> list[SnapshotRow]: ...
    def timeline(self, doc_key: str, path: str, entitlements: tuple[str, ...]) -> list[SnapshotRow]: ...
    def edges_touching(self, node_ids: Iterable[str]) -> list[EdgeRow]: ...
    def node_visible(self, node_id: str, entitlements: tuple[str, ...]) -> bool: ...
    def version_status_at(self, node_id: str, as_of: date,
                          entitlements: tuple[str, ...]) -> str | None: ...
    def suspensions_at(self, as_of: date, entitlements: tuple[str, ...]) -> list[SuspensionRef]: ...
    def open_conflicts(self) -> list[ConflictRow]: ...
    def consolidation_pending(self) -> set[str]: ...
    def coverage(self) -> list[CoverageRow]: ...
    def doc_keys(self, entitlements: tuple[str, ...]) -> list[str]: ...
    def ops_brief(self, op_ids: Iterable[str]) -> dict[str, OpBrief]: ...
    def write_answer_log(self, record: dict[str, Any]) -> str | None: ...


# ---------------------------------------------------------------------------
# PgStore — hiện thân SQL (một cửa thật)
# ---------------------------------------------------------------------------

class PgStore:
    def __init__(self, conn, run: RunInfo):
        self._conn = conn
        self.run = run

    # -- helpers ------------------------------------------------------------

    def _rows(self, sql: str, params: dict[str, Any]) -> list[SnapshotRow]:
        cur = self._conn.execute(sql, params)
        out = []
        for r in cur.fetchall():
            out.append(SnapshotRow(
                node_id=r[0], version=r[1], heading=r[2], body=r[3] or "", status=r[4],
                valid_from=r[5], valid_to=r[6], scope_predicate=r[7], scope_hash=r[8] or "",
                provenance=tuple(r[9] or ()), run_id=r[10], path=r[11], role=r[12],
                artifact_id=r[13], doc_key=r[14], audience=r[15], title=r[16],
                retrievable=r[17]))
        return out

    @staticmethod
    def _scope_params(cohort: Any) -> dict[str, Any]:
        c = _cohort_dict(cohort)
        return {"csb": c.get("contract_signed_before"),
                "naooa": c.get("not_amended_on_or_after"),
                "entity_class": c.get("entity_class")}

    # -- protocol -----------------------------------------------------------

    def candidates(self, as_of, cohort, entitlements):
        params = {"run_id": self.run.run_id, "as_of": as_of,
                  "entitlements": list(entitlements), **self._scope_params(cohort)}
        return self._rows(CANDIDATE_SQL, params)

    def versions_at(self, node_ids, as_of, cohort, entitlements):
        ids = list(node_ids)
        if not ids:
            return {}
        params = {"run_id": self.run.run_id, "as_of": as_of, "node_ids": ids,
                  "entitlements": list(entitlements), **self._scope_params(cohort)}
        out: dict[str, list[SnapshotRow]] = {}
        for row in self._rows(VERSIONS_AT_SQL, params):
            out.setdefault(row.node_id, []).append(row)
        return out

    def pending_versions(self, as_of, entitlements, node_ids=None):
        params = {"run_id": self.run.run_id, "as_of": as_of,
                  "node_ids": list(node_ids) if node_ids is not None else None,
                  "entitlements": list(entitlements),
                  "csb": None, "naooa": None, "entity_class": None}
        return self._rows(PENDING_SQL, params)

    def timeline(self, doc_key, path, entitlements):
        params = {"run_id": self.run.run_id, "doc_key": doc_key, "path": path,
                  "entitlements": list(entitlements)}
        return self._rows(TIMELINE_SQL, params)

    def edges_touching(self, node_ids):
        ids = list(node_ids)
        if not ids:
            return []
        cur = self._conn.execute(EDGES_SQL, {"node_ids": ids})
        return [EdgeRow(src_node=r[0], src_version=r[1], kind=r[2], dst_node=r[3],
                        dst_norm=r[4], frontier_ref=r[5], raw_citation=r[6],
                        confidence=r[7]) for r in cur.fetchall()]

    def node_visible(self, node_id, entitlements):
        cur = self._conn.execute(NODE_AUDIENCE_SQL, {"node_ids": [node_id]})
        row = cur.fetchone()
        return bool(row) and row[1] in entitlements

    def version_status_at(self, node_id, as_of, entitlements):
        cur = self._conn.execute(STATUS_AT_SQL, {
            "run_id": self.run.run_id, "node_id": node_id, "as_of": as_of,
            "entitlements": list(entitlements)})
        row = cur.fetchone()
        return row[0] if row else None

    def suspensions_at(self, as_of, entitlements):
        cur = self._conn.execute(SUSPENSIONS_SQL, {
            "run_id": self.run.run_id, "as_of": as_of, "entitlements": list(entitlements)})
        return [SuspensionRef(node_id=r[0], doc_key=r[1], path=r[2], valid_from=r[3],
                              valid_to=r[4], pending_open=r[5]) for r in cur.fetchall()]

    def open_conflicts(self):
        cur = self._conn.execute(CONFLICTS_SQL)
        out = []
        for r in cur.fetchall():
            members = tuple(str(m.get("node_id")) for m in (r[1] or []))
            out.append(ConflictRow(id=r[0], member_node_ids=members, tier=r[2],
                                   label=r[3], reason=r[4], status=r[5],
                                   resolved_by_op=r[6], resolution_valid_from=r[7]))
        return out

    def consolidation_pending(self):
        cur = self._conn.execute(CONSOLIDATION_SQL)
        return {r[0] for r in cur.fetchall()}

    def coverage(self):
        cur = self._conn.execute(COVERAGE_SQL)
        return [CoverageRow(channel=r[0], last_seq=r[1], last_checked=r[2])
                for r in cur.fetchall()]

    def doc_keys(self, entitlements):
        cur = self._conn.execute(DOC_KEYS_SQL, {"entitlements": list(entitlements)})
        return [r[0] for r in cur.fetchall()]

    def ops_brief(self, op_ids):
        ids = list(op_ids)
        if not ids:
            return {}
        cur = self._conn.execute(OPS_BRIEF_SQL, {"op_ids": ids})
        return {r[0]: OpBrief(id=r[0], kind=r[1], source_doc_key=r[2], valid_from=r[3])
                for r in cur.fetchall()}

    def write_answer_log(self, record):
        import json as _json
        params = dict(record)
        for k in ("claims", "retrieved", "banners"):
            params[k] = _json.dumps(params.get(k) or [], ensure_ascii=False, default=str)
        params.setdefault("session_id", None)
        params.setdefault("as_known", None)
        params["conflicts"] = params.get("conflicts") or None
        cur = self._conn.execute(ANSWER_LOG_INSERT_SQL, params)
        qa_id = cur.fetchone()[0]
        self._conn.commit()
        return qa_id


def resolve_run(conn, as_known: datetime | None = None) -> RunInfo | None:
    """Run mới nhất có k_cutoff ≤ as_known (trục K); None = chưa có snapshot."""
    cur = conn.execute(LATEST_RUN_SQL, {"as_known": as_known})
    row = cur.fetchone()
    return RunInfo(run_id=row[0], k_cutoff=row[1]) if row else None


def pg_store(conn, as_known: datetime | None = None) -> "PgStore | None":
    run = resolve_run(conn, as_known)
    return PgStore(conn, run) if run else None


# ---------------------------------------------------------------------------
# MemStore — cùng ngữ nghĩa, thuần Python (unit test / demo offline)
# ---------------------------------------------------------------------------

class MemStore:
    def __init__(self, rows: list[SnapshotRow], edges: list[EdgeRow] | None = None,
                 node_audience: dict[str, str] | None = None,
                 conflicts: list[ConflictRow] | None = None,
                 consolidation: set[str] | None = None,
                 coverage_rows: list[CoverageRow] | None = None,
                 aliases: list[tuple[str, str, str]] | None = None,  # (doc_key, path, node_id)
                 suspension_pending_ops: set[str] | None = None,
                 ops: dict[str, OpBrief] | None = None,
                 run: RunInfo | None = None):
        self._rows = list(rows)
        self._edges = list(edges or [])
        self._node_audience = dict(node_audience or {})
        for r in rows:  # audience suy từ row nếu không khai riêng
            self._node_audience.setdefault(r.node_id, r.audience)
        self._conflicts = list(conflicts or [])
        self._consolidation = set(consolidation or set())
        self._coverage = list(coverage_rows or [])
        self._aliases = list(aliases or [])
        self._susp_pending_ops = set(suspension_pending_ops or set())
        self._ops = dict(ops or {})
        self.run = run or RunInfo(run_id="00000000-0000-0000-0000-0000000000ff")
        self.answer_logs: list[dict[str, Any]] = []

    # -- predicate thuần Python (phải trùng ngữ nghĩa SQL — test chéo) ------

    @staticmethod
    def _valid_at(r: SnapshotRow, as_of: date) -> bool:
        return r.valid_from <= as_of and (r.valid_to is None or as_of < r.valid_to)

    def _visible(self, r: SnapshotRow, entitlements: tuple[str, ...]) -> bool:
        return r.audience in entitlements

    def candidates(self, as_of, cohort, entitlements):
        c = _cohort_dict(cohort)
        return sorted(
            (r for r in self._rows
             if r.run_id == self.run.run_id and r.retrievable and r.status == "active"
             and self._valid_at(r, as_of) and applicability_matches(r.scope_predicate, c)
             and self._visible(r, entitlements)),
            key=lambda r: (r.doc_key, r.path, r.scope_hash, r.version))

    def versions_at(self, node_ids, as_of, cohort, entitlements):
        ids = set(node_ids)
        out: dict[str, list[SnapshotRow]] = {}
        for r in self.candidates(as_of, cohort, entitlements):
            if r.node_id in ids:
                out.setdefault(r.node_id, []).append(r)
        return out

    def pending_versions(self, as_of, entitlements, node_ids=None):
        ids = set(node_ids) if node_ids is not None else None
        return sorted(
            (r for r in self._rows
             if r.run_id == self.run.run_id and r.retrievable and r.status == "active"
             and r.valid_from > as_of and self._visible(r, entitlements)
             and (ids is None or r.node_id in ids)),
            key=lambda r: (r.valid_from, r.doc_key, r.path))

    def timeline(self, doc_key, path, entitlements):
        alias_nodes = {nid for dk, p, nid in self._aliases if dk == doc_key and p == path}
        return sorted(
            (r for r in self._rows
             if r.run_id == self.run.run_id and r.retrievable and r.doc_key == doc_key
             and (r.node_id in alias_nodes or r.path == path)
             and self._visible(r, entitlements)),
            key=lambda r: (r.valid_from, r.version))

    def edges_touching(self, node_ids):
        ids = set(node_ids)
        return [e for e in self._edges if e.src_node in ids or e.dst_node in ids]

    def node_visible(self, node_id, entitlements):
        aud = self._node_audience.get(node_id)
        return aud is not None and aud in entitlements

    def version_status_at(self, node_id, as_of, entitlements):
        statuses = [r.status for r in self._rows
                    if r.node_id == node_id and r.run_id == self.run.run_id
                    and self._valid_at(r, as_of) and self._visible(r, entitlements)]
        if not statuses:
            return None
        return "active" if "active" in statuses else statuses[0]

    def suspensions_at(self, as_of, entitlements):
        out = []
        for r in self._rows:
            if (r.run_id == self.run.run_id and r.status == "suspended"
                    and self._valid_at(r, as_of) and self._visible(r, entitlements)):
                pending = bool(set(r.provenance) & self._susp_pending_ops)
                out.append(SuspensionRef(node_id=r.node_id, doc_key=r.doc_key, path=r.path,
                                         valid_from=r.valid_from, valid_to=r.valid_to,
                                         pending_open=pending))
        return out

    def open_conflicts(self):
        return list(self._conflicts)

    def consolidation_pending(self):
        return set(self._consolidation)

    def coverage(self):
        return list(self._coverage)

    def doc_keys(self, entitlements):
        return sorted({r.doc_key for r in self._rows if r.audience in entitlements})

    def ops_brief(self, op_ids):
        return {oid: self._ops[oid] for oid in op_ids if oid in self._ops}

    def write_answer_log(self, record):
        import uuid as _uuid
        self.answer_logs.append(dict(record))
        return str(_uuid.uuid4())
