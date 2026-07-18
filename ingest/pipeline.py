"""pipeline.py — seam cho F6 (api/integrations.run_ingest_pipeline).

`run(artifact_id)` chạy S4.1–S4.3 trên artifact ĐÃ nằm trong L0 (F6 lưu trước
qua POST /admin/ingest): normalize → parse → roles → edges → op extraction →
router → ghi node/alias/edge/op(proposed) + coverage. Trả report dict.

LLM: bật khi có API key cho role extract (INGEST_USE_LLM=0 để tắt cưỡng bức);
gateway lỗi → tự thoái lui tầng rule (không chặn ingest).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import psycopg

from ingest.alias import DbStore
from ingest.orchestrator import build_bundle, persist_contents, route_bundle

logger = logging.getLogger("lawstate.ingest.pipeline")


def _database_url() -> str:
    return os.getenv("DATABASE_URL",
                     "postgresql://lawstate:lawstate@localhost:5432/lawstate")


def _maybe_gateway() -> Any:
    if os.getenv("INGEST_USE_LLM", "1") == "0":
        return None
    has_key = any(os.getenv(k) for k in
                  ("LLM_EXTRACT_API_KEY", "OPENROUTER_API_KEY", "LLM_API_KEY"))
    if not has_key:
        logger.info("ingest.pipeline: không có API key extract — chạy tầng rule thuần")
        return None
    try:
        from answer.llm_gateway import get_gateway
        return get_gateway()
    except Exception as exc:                    # gateway cấu hình lỗi → rule thuần
        logger.warning("ingest.pipeline: gateway không khởi tạo được (%s) — rule thuần", exc)
        return None


def run(artifact_id: str, conn: Any = None, gateway: Any = "auto") -> dict[str, Any]:
    """→ {proposed_ops, nodes, aliases, edges, backlog, note}. Raise nếu artifact không tồn tại."""
    own_conn = conn is None
    if own_conn:
        conn = psycopg.connect(_database_url())
    try:
        row = conn.execute(
            """SELECT id, doc_key, doc_type, issuer, title, issued_date, effective_date,
                      audience, owner, channel, is_oracle, synthetic, text, raw
               FROM artifact WHERE id = %s""", (artifact_id,)).fetchone()
        if row is None:
            raise ValueError(f"artifact {artifact_id[:12]}… không tồn tại trong L0")
        (aid, doc_key, doc_type, issuer, title, issued, effective, audience, owner,
         channel, is_oracle, synthetic, text, raw) = _astuple(row)
        if text is None:
            if raw is None:
                raise ValueError("artifact không có text lẫn raw — không parse được (D-43)")
            text = bytes(raw).decode("utf-8", errors="replace")

        n_ops_before = conn.execute(
            "SELECT count(*) FROM op WHERE source_artifact = %s", (aid,)).fetchone()
        if _first(n_ops_before) > 0:
            raise ValueError(f"artifact {doc_key} đã có op — pipeline không chạy lại "
                             "(op append-only; sửa = op mới, D-20)")

        meta = {"doc_key": doc_key, "doc_type": doc_type, "issuer": issuer,
                "title": title, "issued_date": issued, "effective_date": effective,
                "audience": audience, "owner": owner, "channel": channel,
                "is_oracle": is_oracle, "synthetic": synthetic}
        gw = _maybe_gateway() if gateway == "auto" else gateway
        store = DbStore(conn)
        bundle = build_bundle(text, meta, store, gateway=gw)
        bundle.sha256 = aid                      # id là sha file gốc F6 đã tính
        route_bundle(bundle, store, llm_enabled=gw is not None)
        result = persist_contents(conn, bundle)
        if own_conn:
            conn.commit()
        return {
            "doc_key": doc_key,
            "proposed_ops": result.proposed_ops,
            "nodes": result.nodes,
            "aliases": result.aliases,
            "edges": result.edges,
            "backlog": result.backlog,
            "note": (f"F3 ingest: {result.nodes} node, {result.edges} edge, "
                     f"{result.proposed_ops} op đề xuất (proposed — chờ phê chuẩn), "
                     f"{len(result.backlog)} mục backlog"
                     + (" · LLM extract: bật" if gw is not None else " · LLM extract: tắt (rule thuần)")),
        }
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()


def _astuple(row: Any) -> tuple:
    """Chịu được cả tuple-row lẫn dict_row (api.db dùng dict_row)."""
    if isinstance(row, dict):
        return (row["id"], row["doc_key"], row["doc_type"], row["issuer"], row["title"],
                row["issued_date"], row["effective_date"], row["audience"], row["owner"],
                row["channel"], row["is_oracle"], row["synthetic"], row["text"], row["raw"])
    return tuple(row)


def _first(row: Any) -> int:
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]
