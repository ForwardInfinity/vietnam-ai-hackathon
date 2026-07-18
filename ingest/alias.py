"""alias.py — bảng địa chỉ bề mặt → node CÓ THỜI GIAN TÍNH (D-07, INV-11).

Hai hiện thân cùng interface `Store`:
  - MemoryStore: pure pipeline / demo / tests (không cần Postgres)
  - DbStore: orchestrator persist + resolve cross-doc trên Postgres

Resolver `resolve(doc_key, path, at_date)`:
  1. cửa sổ alias phủ at_date → node (INV-11: đúng MỘT);
  2. fallback bảng node theo (artifact.doc_key, path) — cần cho bẫy #4: TT10 (ban hành
     23/08/2023) nhắm khoản 8-10 Đ8 TT39 do TT06 ĐỀ XUẤT tạo (chưa ratify → chưa có
     alias; alias + version chỉ sinh khi ratify + replay — R-12). Fallback đánh dấu
     `provisional=True` để router biết target chưa qua phê chuẩn.

Trôi số (INV-11, bẫy #15-alias): `add_alias` đóng cửa sổ đang mở của cùng
(doc_key, path) tại valid_from mới — một địa chỉ bề mặt tại một ngày chỉ về MỘT node.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol
from uuid import UUID

DATE_MIN = date(1900, 1, 1)


@dataclass
class Resolution:
    node_id: UUID
    doc_key: str
    path: str
    role: str = "rule"
    provisional: bool = False      # resolve qua node birth (op insert chưa ratify)
    future: bool = False           # alias chỉ mở SAU at_date (node chưa kịp hiệu lực — bẫy #4)


class Store(Protocol):
    def resolve(self, doc_key: str, path: str, at: date) -> Resolution | None: ...
    def add_alias(self, doc_key: str, path: str, node_id: UUID, valid_from: date) -> None: ...
    def doc_keys(self) -> list[str]: ...
    def doc_meta(self, doc_key: str) -> dict[str, Any] | None: ...
    def find_doc(self, docno: str | None, *, issued: date | None = None,
                 title_hint: str | None = None) -> str | None: ...
    def ops_from_source_node(self, node_id: UUID) -> list[UUID]: ...
    def ops_targeting(self, node_id: UUID) -> list[UUID]: ...
    def norm_for_doc(self, doc_key: str) -> UUID | None: ...
    def has_inbound_dinh_nghia(self, node_id: UUID) -> bool: ...


# ============================================================================
# MemoryStore
# ============================================================================

@dataclass
class _AliasRow:
    doc_key: str
    path: str
    node_id: UUID
    valid_from: date
    valid_to: date | None = None


class MemoryStore:
    """Store thuần bộ nhớ — pure pipeline. Nạp bundle bằng `register_bundle`."""

    def __init__(self) -> None:
        self.aliases: list[_AliasRow] = []
        self.nodes: dict[UUID, dict[str, Any]] = {}      # id -> {doc_key, path, role, body, heading}
        self.docs: dict[str, dict[str, Any]] = {}        # doc_key -> meta
        self.ops: list[dict[str, Any]] = []              # op đề xuất/ratified đã biết
        self.norms: dict[str, UUID] = {}                 # doc_key -> norm id
        self.edges: list[dict[str, Any]] = []

    # ---- ghi ----------------------------------------------------------------

    def add_doc(self, doc_key: str, meta: dict[str, Any]) -> None:
        self.docs[doc_key] = meta

    def add_node(self, node_id: UUID, doc_key: str, path: str, role: str,
                 body: str = "", heading: str | None = None) -> None:
        self.nodes[node_id] = {"doc_key": doc_key, "path": path, "role": role,
                               "body": body, "heading": heading}

    def add_alias(self, doc_key: str, path: str, node_id: UUID, valid_from: date) -> None:
        for row in self.aliases:
            if (row.doc_key == doc_key and row.path == path and row.valid_to is None
                    and row.valid_from < valid_from and row.node_id != node_id):
                row.valid_to = valid_from          # đóng cửa sổ cũ — INV-11
        self.aliases.append(_AliasRow(doc_key, path, node_id, valid_from))

    def add_op(self, op: dict[str, Any]) -> None:
        self.ops.append(op)

    def add_edge(self, edge: dict[str, Any]) -> None:
        self.edges.append(edge)

    def register_bundle(self, bundle: Any) -> None:
        """Nạp một IngestBundle đã build vào store (mô phỏng trạng thái DB sau persist)."""
        meta = dict(bundle.meta)
        self.add_doc(bundle.doc_key, meta)
        for n in bundle.nodes:
            dk = n.artifact_doc_key or bundle.doc_key
            self.add_node(n.id, dk, n.path, n.role, n.body, n.heading)
        for (dk, path, node_id, vf) in bundle.aliases:
            self.add_alias(dk, path, node_id, vf)
        for op in bundle.ops:
            self.add_op({"id": op.id, "kind": op.kind, "source_doc": bundle.doc_key,
                         "source_node": op.source_node, "source_path": op.source_path,
                         "target_node": op.target_node, "target_op": op.target_op,
                         "status": "proposed"})
        for e in bundle.edges:
            self.add_edge({"src_node": e.src_node, "dst_node": e.dst_node, "kind": e.kind})

    # ---- đọc ----------------------------------------------------------------

    def resolve(self, doc_key: str, path: str, at: date) -> Resolution | None:
        rows = [r for r in self.aliases if r.doc_key == doc_key and r.path == path]
        for r in rows:
            if r.valid_from <= at and (r.valid_to is None or at < r.valid_to):
                nd = self.nodes.get(r.node_id, {})
                return Resolution(r.node_id, doc_key, path, nd.get("role", "rule"))
        future = [r for r in rows if r.valid_from > at]
        if len(future) == 1:
            nd = self.nodes.get(future[0].node_id, {})
            return Resolution(future[0].node_id, doc_key, path, nd.get("role", "rule"), future=True)
        # fallback bảng node (bẫy #4 — node birth do op đề xuất, chưa có alias)
        hits = [(nid, nd) for nid, nd in self.nodes.items()
                if nd["doc_key"] == doc_key and nd["path"] == path]
        if len(hits) == 1:
            nid, nd = hits[0]
            return Resolution(nid, doc_key, path, nd.get("role", "rule"), provisional=True)
        return None

    def doc_keys(self) -> list[str]:
        return list(self.docs)

    def doc_meta(self, doc_key: str) -> dict[str, Any] | None:
        return self.docs.get(doc_key)

    def find_doc(self, docno: str | None, *, issued: date | None = None,
                 title_hint: str | None = None) -> str | None:
        if docno:
            if docno in self.docs:
                return docno
            return None
        cands = []
        for dk, meta in self.docs.items():
            if issued and meta.get("issued_date") == issued:
                cands.append(dk)
        if len(cands) == 1:
            return cands[0]
        if title_hint:
            hint = " ".join(title_hint.lower().split())
            scored = []
            for dk, meta in self.docs.items():
                title = " ".join(str(meta.get("title") or "").lower().split())
                if title and (hint in title or (len(title) > 8 and title in hint)):
                    scored.append(dk)
            if len(scored) == 1:
                return scored[0]
        return None

    def ops_from_source_node(self, node_id: UUID) -> list[UUID]:
        return [o["id"] for o in self.ops if o.get("source_node") == node_id]

    def ops_targeting(self, node_id: UUID) -> list[UUID]:
        return [o["id"] for o in self.ops if o.get("target_node") == node_id]

    def norm_for_doc(self, doc_key: str) -> UUID | None:
        return self.norms.get(doc_key)

    def has_inbound_dinh_nghia(self, node_id: UUID) -> bool:
        return any(e for e in self.edges
                   if e.get("dst_node") == node_id and e.get("kind") == "dinh_nghia")

    def node_info(self, node_id: UUID) -> dict[str, Any] | None:
        return self.nodes.get(node_id)


# ============================================================================
# DbStore (psycopg) — orchestrator dùng; mọi query parameterized
# ============================================================================

class DbStore:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def resolve(self, doc_key: str, path: str, at: date) -> Resolution | None:
        row = self.conn.execute(
            """SELECT a.node_id, n.role FROM alias a JOIN node n ON n.id = a.node_id
               WHERE a.doc_key = %s AND a.path = %s AND a.valid_from <= %s
                 AND (a.valid_to IS NULL OR %s < a.valid_to)
               ORDER BY a.valid_from DESC LIMIT 1""",
            (doc_key, path, at, at)).fetchone()
        if row:
            return Resolution(row[0], doc_key, path, row[1])
        rows = self.conn.execute(
            """SELECT a.node_id, n.role FROM alias a JOIN node n ON n.id = a.node_id
               WHERE a.doc_key = %s AND a.path = %s AND a.valid_from > %s""",
            (doc_key, path, at)).fetchall()
        if len(rows) == 1:
            return Resolution(rows[0][0], doc_key, path, rows[0][1], future=True)
        rows = self.conn.execute(
            """SELECT n.id, n.role FROM node n JOIN artifact a ON a.id = n.artifact_id
               WHERE a.doc_key = %s AND n.path = %s""",
            (doc_key, path)).fetchall()
        if len(rows) == 1:
            return Resolution(rows[0][0], doc_key, path, rows[0][1], provisional=True)
        return None

    def add_alias(self, doc_key: str, path: str, node_id: UUID, valid_from: date) -> None:
        self.conn.execute(
            """UPDATE alias SET valid_to = %s
               WHERE doc_key = %s AND path = %s AND valid_to IS NULL
                 AND valid_from < %s AND node_id <> %s""",
            (valid_from, doc_key, path, valid_from, node_id))
        self.conn.execute(
            """INSERT INTO alias (doc_key, path, node_id, valid_from)
               VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (doc_key, path, node_id, valid_from))

    def doc_keys(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT doc_key FROM artifact").fetchall()]

    def doc_meta(self, doc_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT id, doc_key, doc_type, issuer, title, issued_date, effective_date, is_oracle
               FROM artifact WHERE doc_key = %s""", (doc_key,)).fetchone()
        if not row:
            return None
        return {"artifact_id": row[0], "doc_key": row[1], "doc_type": row[2], "issuer": row[3],
                "title": row[4], "issued_date": row[5], "effective_date": row[6],
                "is_oracle": row[7]}

    def find_doc(self, docno: str | None, *, issued: date | None = None,
                 title_hint: str | None = None) -> str | None:
        if docno:
            row = self.conn.execute("SELECT doc_key FROM artifact WHERE doc_key = %s",
                                    (docno,)).fetchone()
            return row[0] if row else None
        if issued:
            rows = self.conn.execute("SELECT doc_key FROM artifact WHERE issued_date = %s",
                                     (issued,)).fetchall()
            if len(rows) == 1:
                return rows[0][0]
        if title_hint:
            rows = self.conn.execute(
                "SELECT doc_key FROM artifact WHERE title ILIKE %s",
                (f"%{title_hint}%",)).fetchall()
            if len(rows) == 1:
                return rows[0][0]
        return None

    def ops_from_source_node(self, node_id: UUID) -> list[UUID]:
        return [r[0] for r in self.conn.execute(
            "SELECT id FROM op WHERE source_node = %s ORDER BY seq", (node_id,)).fetchall()]

    def ops_targeting(self, node_id: UUID) -> list[UUID]:
        return [r[0] for r in self.conn.execute(
            "SELECT id FROM op WHERE target_node = %s ORDER BY seq", (node_id,)).fetchall()]

    def norm_for_doc(self, doc_key: str) -> UUID | None:
        row = self.conn.execute(
            """SELECT nm.id FROM norm nm JOIN artifact a ON a.id = nm.artifact_id
               WHERE a.doc_key = %s LIMIT 1""", (doc_key,)).fetchone()
        return row[0] if row else None

    def has_inbound_dinh_nghia(self, node_id: UUID) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM edge WHERE dst_node = %s AND kind = 'dinh_nghia' LIMIT 1",
            (node_id,)).fetchone()
        return row is not None

    def node_info(self, node_id: UUID) -> dict[str, Any] | None:
        """Role/path + body (re-parse artifact.text — bảng node không lưu body;
        body hiệu lực là chuyện của node_version/F4, đây là body LÚC SINH)."""
        row = self.conn.execute(
            """SELECT n.path, n.role, a.doc_key, a.text FROM node n
               JOIN artifact a ON a.id = n.artifact_id WHERE n.id = %s""",
            (node_id,)).fetchone()
        if row is None:
            return None
        path, role, doc_key, text = row
        body, heading = "", None
        if text:
            from ingest.tree_parser import parse_document
            parsed = parse_document(text)
            pn = parsed.node_at(path)
            if pn is not None:
                body, heading = pn.body, pn.heading
        return {"doc_key": doc_key, "path": path, "role": role,
                "body": body, "heading": heading}
