"""orchestrator.py — ingest_artifact(file) → {nodes, aliases, edges, proposed_ops}.

Thứ tự R-3 (bắt buộc): artifact L0 (sha256, tem K) → chuẩn hóa → parse cây →
node + alias + dates → role → edge (R-8..R-10) → op extraction (R-11..R-14) →
router (R-15) → ghi op status='proposed' → coverage (R-6).

VBHN `is_oracle=true`: CHỈ parse để diff (R-7) — không op, không edge; F4 chặn
retrieval qua artifact.is_oracle.

Pure pipeline (`build_bundle`) tách khỏi persist (`persist_bundle`) — demo/tests
chạy không cần Postgres; DB mode dùng psycopg conn do caller đưa vào.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

try:
    from psycopg.types.json import Jsonb
except ImportError:                       # pure mode không cần psycopg
    Jsonb = dict                          # type: ignore[assignment,misc]

from ingest import manifest as mf
from ingest.alias import DbStore, MemoryStore, Store
from ingest.citation import CitationContext, extract_edges
from ingest.model import IngestBundle, ParsedNode, ProposedOp
from ingest.normalize import normalize
from ingest.op_extract import ExtractionContext, extract_ops
from ingest.ratify import insert_proposed_op, route_op
from ingest.roles import assign_roles
from ingest.tree_parser import parse_document

logger = logging.getLogger("lawstate.ingest.orchestrator")


@dataclass
class IngestResult:
    doc_key: str
    artifact_id: str
    nodes: int
    aliases: int
    edges: int
    proposed_ops: int
    backlog: list[dict[str, Any]] = field(default_factory=list)   # op 0-target, edge unresolved
    bundle: IngestBundle | None = None


def _iso(d: Any) -> date | None:
    if d is None or isinstance(d, date):
        return d
    return date.fromisoformat(str(d))


def build_bundle(raw: bytes | str, meta: dict[str, Any], store: Store,
                 gateway: Any = None) -> IngestBundle:
    """Pipeline thuần: KHÔNG ghi DB. `meta` tối thiểu {doc_key}; phần còn lại suy luận."""
    if isinstance(raw, bytes):
        sha = hashlib.sha256(raw).hexdigest()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
    else:
        sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        text = raw

    text = normalize(text)
    doc = parse_document(text)

    doc_key = meta.get("doc_key") or doc.doc_key
    if not doc_key:
        raise ValueError("Không xác định được doc_key (header 'Số:' và meta đều thiếu)")
    meta = dict(meta)
    meta["doc_key"] = doc_key
    meta.setdefault("doc_type", mf.infer_doc_type(doc_key, doc.title))
    meta.setdefault("issuer", mf.infer_issuer(doc_key, meta["doc_type"]))
    meta.setdefault("title", doc.title)
    meta.setdefault("audience", "internal" if "/SHB" in doc_key else "public")
    meta.setdefault("is_oracle", meta["doc_type"] == "vbhn")
    meta["issued_date"] = _iso(meta.get("issued_date")) or doc.issued_date
    meta["effective_date"] = _iso(meta.get("effective_date")) or doc.effective_date

    assign_roles(doc, meta["doc_type"])
    for n in doc.nodes:
        n.artifact_doc_key = doc_key

    bundle = IngestBundle(doc=doc, meta=meta, sha256=sha, nodes=list(doc.nodes))

    # alias: mọi node sinh cùng văn bản — cửa sổ mở từ ngày hiệu lực (fallback ban hành)
    alias_from = meta["effective_date"] or meta["issued_date"] or date(1900, 1, 1)
    for n in doc.nodes:
        if n.level != "preamble":
            bundle.aliases.append((doc_key, n.path, n.id, alias_from))

    if meta.get("is_oracle"):
        logger.info("%s là VBHN is_oracle — chỉ parse để diff (R-7): bỏ edge/op", doc_key)
        return bundle

    cctx = CitationContext(doc_key=doc_key, issued_date=meta["issued_date"],
                           effective_date=meta["effective_date"], store=store)
    bundle.edges = extract_edges(doc, cctx, gateway=gateway)

    ectx = ExtractionContext(doc_key=doc_key, issued_date=meta["issued_date"],
                             effective_date=meta["effective_date"], store=store, doc=doc)
    ops, born = extract_ops(doc, ectx, gateway=gateway)
    bundle.ops = ops
    bundle.nodes.extend(born)
    return bundle


class _RoutingStore:
    """Store + edge trong bundle hiện tại (chưa persist) — cho check definitional R-15."""

    def __init__(self, store: Store, bundle: IngestBundle) -> None:
        self._store = store
        self._bundle = bundle

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def has_inbound_dinh_nghia(self, node_id: Any) -> bool:
        if any(e.dst_node == node_id and e.kind == "dinh_nghia" for e in self._bundle.edges):
            return True
        return self._store.has_inbound_dinh_nghia(node_id)


def route_bundle(bundle: IngestBundle, store: Store, llm_enabled: bool) -> None:
    """Router R-15 trên toàn bundle — gọi SAU khi edge đã vào store/DB."""
    rstore = _RoutingStore(store, bundle)
    for op in bundle.ops:
        route_op(op, rstore, doc_effective=bundle.meta.get("effective_date"),
                 llm_enabled=llm_enabled)


# ============================================================================
# Persist (psycopg conn) — đúng thứ tự R-3
# ============================================================================

def persist_bundle(conn: Any, bundle: IngestBundle, raw: bytes | None = None) -> IngestResult:
    meta = bundle.meta
    doc_key = bundle.doc_key
    exists = conn.execute("SELECT id FROM artifact WHERE id = %s OR doc_key = %s",
                          (bundle.sha256, doc_key)).fetchone()
    if exists:
        raise ValueError(f"artifact {doc_key} (sha={bundle.sha256[:12]}…) đã tồn tại — "
                         "L0 append-only, không re-ingest (INV-1)")

    conn.execute(
        """INSERT INTO artifact (id, doc_key, doc_type, issuer, title, issued_date,
                                 effective_date, audience, owner, review_by, channel,
                                 is_oracle, synthetic, raw, text)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (bundle.sha256, doc_key, meta["doc_type"], meta["issuer"], meta.get("title"),
         meta.get("issued_date"), meta.get("effective_date"),
         meta.get("audience", "internal"), meta.get("owner"), meta.get("review_by"),
         meta.get("channel"), meta.get("is_oracle", False), meta.get("synthetic", False),
         raw, bundle.doc.text))
    return persist_contents(conn, bundle)


def persist_contents(conn: Any, bundle: IngestBundle) -> IngestResult:
    """Ghi nội dung bundle SAU bước artifact L0 (dùng khi artifact đã được lưu
    trước — đường /admin/ingest của F6)."""
    meta = bundle.meta
    doc_key = bundle.doc_key

    # nodes (kể cả node born_of_op thuộc artifact KHÁC — insert tạo node đích R-12)
    id_by_key: dict[tuple[str, str], Any] = {}
    for n in bundle.nodes:
        target_doc = n.artifact_doc_key or doc_key
        if target_doc == doc_key:
            artifact_id = bundle.sha256
        else:
            row = conn.execute("SELECT id FROM artifact WHERE doc_key = %s",
                               (target_doc,)).fetchone()
            if row is None:
                logger.warning("node %s thuộc doc %s chưa có trong kho — bỏ (op sẽ unresolved)",
                               n.path, target_doc)
                continue
            artifact_id = row[0]
        parent_id = id_by_key.get((target_doc, n.parent_path)) if n.parent_path else None
        # page_anchor mang heading/body gốc — quy ước F3→F4 (engine/README: base text
        # của fold đọc từ node.page_anchor.heading/body do F3 ghi lúc parse)
        anchor = Jsonb({"heading": n.heading, "body": n.body})
        conn.execute(
            """INSERT INTO node (id, artifact_id, parent_id, path, label, seq, role, page_anchor)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (n.id, artifact_id, parent_id, n.path, n.label or None,
             None if n.born_of_op else n.seq, n.role, anchor))
        id_by_key[(target_doc, n.path)] = n.id

    store = DbStore(conn)
    written_node_ids = set(id_by_key.values())
    for (dk, path, node_id, vf) in bundle.aliases:
        if node_id in written_node_ids:
            store.add_alias(dk, path, node_id, vf)

    for e in bundle.edges:
        if e.src_node is None:
            continue
        conn.execute(
            """INSERT INTO edge (src_node, src_version, dst_node, dst_norm, frontier_ref,
                                 kind, raw_citation, resolved_against, confidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (e.src_node, e.src_version, e.dst_node, e.dst_norm, e.frontier_ref,
             e.kind, e.raw_citation, e.resolved_against, e.confidence))

    route_bundle(bundle, store, llm_enabled=bundle.meta.get("llm_enabled", False))

    backlog: list[dict[str, Any]] = []
    written_ops = 0
    for op in bundle.ops:
        if not op.check_ok():
            backlog.append({"type": "op_unresolved", "kind": op.kind,
                            "source_quote": op.source_quote[:200],
                            "target_surface": op.target_surface,
                            "red_flags": op.red_flags})
            continue
        insert_proposed_op(conn, op, bundle.sha256)
        written_ops += 1
    for e in bundle.edges:
        if not e.resolved and e.src_node is not None:
            backlog.append({"type": "edge_unresolved", "kind": e.kind,
                            "raw_citation": e.raw_citation[:200]})

    channel = meta.get("channel") or "manual"
    conn.execute(
        """INSERT INTO coverage (channel, last_seq, last_checked)
           VALUES (%s, %s, now())
           ON CONFLICT (channel) DO UPDATE
           SET last_seq = EXCLUDED.last_seq, last_checked = now()""",
        (channel, meta.get("coverage_seq") or doc_key))

    return IngestResult(doc_key=doc_key, artifact_id=bundle.sha256,
                        nodes=sum(1 for n in bundle.nodes if (n.artifact_doc_key or doc_key) == doc_key),
                        aliases=len(bundle.aliases), edges=len(bundle.edges),
                        proposed_ops=written_ops, backlog=backlog, bundle=bundle)


def ingest_artifact(conn: Any, file: str | Path, meta: dict[str, Any] | None = None,
                    gateway: Any = None) -> IngestResult:
    """API chính DB-mode. `meta` thiếu → đọc từ corpus/manifest.json theo doc_key parse được."""
    p = Path(file)
    raw = p.read_bytes()
    meta = dict(meta or {})
    if "doc_key" not in meta:
        probe = parse_document(normalize(raw.decode("utf-8", errors="replace")))
        entry = mf.entry_for(probe.doc_key) if probe.doc_key else None
        meta = {**mf.artifact_meta(entry, probe.title), **meta} if entry \
            else {**meta, "doc_key": probe.doc_key}
    store = DbStore(conn)
    bundle = build_bundle(raw, meta, store, gateway=gateway)
    bundle.meta["llm_enabled"] = gateway is not None
    return persist_bundle(conn, bundle, raw=raw)


def ingest_corpus_pure(entries: list[dict[str, Any]], texts: dict[str, str],
                       gateway: Any = None) -> tuple[MemoryStore, dict[str, IngestBundle]]:
    """Chạy toàn corpus qua MemoryStore theo thứ tự issued_date (demo/exit tests).
    → (store, bundles theo doc_key)."""
    store = MemoryStore()
    bundles: dict[str, IngestBundle] = {}
    _TYPE_RANK = {"bo_luat": 0, "luat": 0, "nghi_quyet_hdtp": 1, "thong_tu": 2,
                  "vbhn": 3, "quyet_dinh": 4, "cong_van": 4,   # đính chính SAU đích cùng ngày
                  "quy_trinh_noi_bo": 5, "chinh_sach_noi_bo": 5, "bieu_mau": 5,
                  "dien_giai_noi_bo": 5}
    def sort_key(e: dict[str, Any]) -> tuple:
        return (str(e.get("issued_date") or "9999"),
                _TYPE_RANK.get(str(e.get("doc_type")), 9), e.get("doc_key", ""))
    for entry in sorted(entries, key=sort_key):
        doc_key = entry["doc_key"]
        if doc_key not in texts:
            continue
        meta = mf.artifact_meta(entry)
        bundle = build_bundle(texts[doc_key], meta, store, gateway=gateway)
        route_bundle(bundle, store, llm_enabled=gateway is not None)
        store.register_bundle(bundle)
        bundles[doc_key] = bundle
    return store, bundles
