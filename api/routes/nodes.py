"""GET /v1/nodes/{key}/timeline · /v1/nodes/{key}/graph · /v1/norms/{id} · /v1/artifacts/{doc_key}.

`{key}` = UUID node HOẶC `"<doc_key>~<path>"` (vd `39/2016/TT-NHNN~dieu:8/khoan:2`) —
đường alias→timeline của D-27. Mọi query lọc audience qua api.gate (MỘT CỬA, INV-12):
role customer không nhận một byte nào từ artifact internal/restricted — kể cả provenance.
"""
from __future__ import annotations

import uuid as uuidlib
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from api import db, gate
from api.auth import get_role
from api.ratify_logic import unified_diff
from api.view_models import (
    AliasWindow,
    ArtifactOut,
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
    NormIncarnation,
    NormOut,
    OpProvenance,
    SuspensionBand,
    TimelineOut,
    VersionOut,
)

router = APIRouter(tags=["nodes"])

_NODE_COLS = """n.id AS node_id, n.path, n.label, n.role, n.page_anchor,
                a.doc_key, a.audience, a.title AS doc_title"""


def _resolve_nodes(conn, key: str, role: str) -> list[dict]:
    """key → hàng node (đã lọc audience). Không thấy/không được thấy → []."""
    clause, params = gate.audience_clause(role)
    try:
        node_id = uuidlib.UUID(key)
        return conn.execute(
            f"""SELECT {_NODE_COLS} FROM node n JOIN artifact a ON a.id = n.artifact_id
                WHERE n.id = %s AND {clause}""",
            [node_id, *params],
        ).fetchall()
    except ValueError:
        pass
    if "~" not in key:
        raise HTTPException(
            status_code=422,
            detail="key phải là UUID node hoặc '<doc_key>~<path>' (vd '39/2016/TT-NHNN~dieu:8/khoan:2')",
        )
    doc_key, path = key.split("~", 1)
    rows = conn.execute(
        f"""SELECT DISTINCT {_NODE_COLS} FROM alias al
            JOIN node n ON n.id = al.node_id
            JOIN artifact a ON a.id = n.artifact_id
            WHERE al.doc_key = %s AND al.path = %s AND {clause}""",
        [doc_key, path, *params],
    ).fetchall()
    if rows:
        return rows
    return conn.execute(  # fallback: địa chỉ lúc sinh (alias chưa được F3 sinh)
        f"""SELECT {_NODE_COLS} FROM node n JOIN artifact a ON a.id = n.artifact_id
            WHERE a.doc_key = %s AND n.path = %s AND {clause}""",
        [doc_key, path, *params],
    ).fetchall()


def _provenance_map(conn, op_ids: list, role: str) -> dict[str, OpProvenance]:
    """op_id → OpProvenance, ĐÃ REDACT op có source artifact ngoài entitlements (INV-12)."""
    if not op_ids:
        return {}
    clause, params = gate.audience_clause(role, alias="sa")
    rows = conn.execute(
        f"""SELECT o.id, o.kind, o.source_quote, o.valid_from, o.valid_to, o.valid_to_event,
                   o.status, o.extractor, o.ratified_by, o.ratify_batch, o.superseded_by,
                   sa.doc_key AS source_doc_key, rb.approved_by AS batch_approved_by
            FROM op o
            JOIN artifact sa ON sa.id = o.source_artifact
            LEFT JOIN ratify_batch rb ON rb.id = o.ratify_batch
            WHERE o.id = ANY(%s) AND {clause}""",
        [list(op_ids), *params],
    ).fetchall()
    return {str(r["id"]): OpProvenance(**r) for r in rows}


@router.get("/nodes/{key:path}/timeline", response_model=TimelineOut)
def node_timeline(key: str, role: str = Depends(get_role)):
    """Mọi version (kể cả suspended/repealed/CHƯA-TỪNG-active) + dải treo + provenance + diff."""
    with db.tx() as conn:
        nodes = _resolve_nodes(conn, key, role)
        if not nodes:
            raise HTTPException(status_code=404, detail="Không thấy node cho key này (hoặc ngoài quyền audience).")
        node = nodes[0]  # INV-11: một (doc_key, path, ngày) → một node; nhiều node = các hiện thân, lấy mới nhất
        if len(nodes) > 1:
            node = sorted(nodes, key=lambda r: str(r["node_id"]))[-1]

        versions = conn.execute(
            """SELECT node_id, version, heading, body, status, valid_from, valid_to,
                      scope_predicate, scope_hash, retrievable, run_id, provenance
               FROM node_version WHERE node_id = %s
               ORDER BY scope_hash, valid_from, version""",
            [node["node_id"]],
        ).fetchall()

        aliases = conn.execute(
            "SELECT doc_key, path, valid_from, valid_to FROM alias WHERE node_id = %s ORDER BY valid_from NULLS FIRST",
            [node["node_id"]],
        ).fetchall()

        all_op_ids = sorted({str(op) for v in versions for op in (v["provenance"] or [])})
        prov_map = _provenance_map(conn, all_op_ids, role)

        # pending_event cho op treo-theo-sự-kiện (D-11)
        pev_rows = conn.execute(
            "SELECT ref, predicate, status FROM pending_event WHERE kind = 'open_suspension' AND ref = ANY(%s::uuid[])",
            [all_op_ids or ["00000000-0000-0000-0000-000000000000"]],
        ).fetchall()
        pev_by_op = {str(r["ref"]): r for r in pev_rows}

        active_scopes = {v["scope_hash"] for v in versions if v["status"] == "active"}
        out_versions: list[VersionOut] = []
        suspensions: list[SuspensionBand] = []
        prev_body_by_scope: dict[str, str | None] = {}

        for v in versions:
            prov = [prov_map[str(op)] for op in (v["provenance"] or []) if str(op) in prov_map]
            diff = None
            prev = prev_body_by_scope.get(v["scope_hash"])
            if prev is not None:
                diff = unified_diff(prev, v["body"])
            prev_body_by_scope[v["scope_hash"]] = v["body"]

            never_active = v["status"] == "suspended" and v["scope_hash"] not in active_scopes
            out_versions.append(
                VersionOut(
                    **{k: v[k] for k in ("node_id", "version", "heading", "body", "status",
                                          "valid_from", "valid_to", "scope_predicate",
                                          "scope_hash", "retrievable", "run_id")},
                    never_active=never_active,
                    provenance=prov,
                    diff_from_prev=diff,
                )
            )
            if v["status"] == "suspended":
                event = next(
                    (pev_by_op[str(op)] for op in (v["provenance"] or []) if str(op) in pev_by_op), None
                )
                suspensions.append(
                    SuspensionBand(
                        valid_from=v["valid_from"],
                        valid_to=v["valid_to"],
                        event_predicate=event["predicate"] if event else None,
                        event_status=event["status"] if event else None,
                    )
                )

        return TimelineOut(
            key=key,
            node_id=node["node_id"],
            doc_key=node["doc_key"],
            path=node["path"],
            role=node["role"],
            heading=out_versions[-1].heading if out_versions else node["label"],
            audience=node["audience"],
            aliases=[AliasWindow(**a) for a in aliases],
            versions=out_versions,
            suspensions=suspensions,
            source_link=f"/api/v1/artifacts/{node['doc_key']}",
            page_anchor=node["page_anchor"],
            note=None if versions else "Chưa có node_version nào (chờ replay F4) — timeline trống là trung thực.",
        )


@router.get("/nodes/{key:path}/graph", response_model=GraphOut)
def node_graph(
    key: str,
    depth: int = Query(default=1, ge=1, le=2),
    as_of: date | None = Query(default=None),
    role: str = Depends(get_role),
):
    """Edges có kiểu: outbound + where-used (inbound), depth ≤ 2, lọc audience hai đầu."""
    with db.tx() as conn:
        seeds = _resolve_nodes(conn, key, role)
        if not seeds:
            raise HTTPException(status_code=404, detail="Không thấy node cho key này (hoặc ngoài quyền audience).")
        center_ids = [r["node_id"] for r in seeds]
        clause_sa, params_sa = gate.audience_clause(role, alias="sa")
        clause_da, params_da = gate.audience_clause(role, alias="da")

        note = None
        version_at: dict[str, set[int]] = {}
        if as_of is not None:
            vrows = conn.execute(
                """SELECT node_id, version FROM node_version
                   WHERE valid_from <= %s AND (valid_to IS NULL OR %s < valid_to)""",
                [as_of, as_of],
            ).fetchall()
            for r in vrows:
                version_at.setdefault(str(r["node_id"]), set()).add(r["version"])
            if not vrows:
                note = "as_of được yêu cầu nhưng chưa có snapshot version nào — hiển thị mọi edge (chờ F4 replay)."

        seen_nodes: set[str] = {str(i) for i in center_ids}
        edges: list[GraphEdgeOut] = []
        seen_edges: set[str] = set()
        frontier = list(center_ids)

        for _hop in range(depth):
            if not frontier:
                break
            out_rows = conn.execute(
                f"""SELECT e.* FROM edge e
                    JOIN node dn0 ON dn0.id = e.src_node  -- src đã trong graph (đã gate)
                    LEFT JOIN node dn ON dn.id = e.dst_node
                    LEFT JOIN artifact da ON da.id = dn.artifact_id
                    WHERE e.src_node = ANY(%s) AND (e.dst_node IS NULL OR {clause_da})""",
                [frontier, *params_da],
            ).fetchall()
            in_rows = conn.execute(
                f"""SELECT e.* FROM edge e
                    JOIN node sn ON sn.id = e.src_node
                    JOIN artifact sa ON sa.id = sn.artifact_id
                    WHERE e.dst_node = ANY(%s) AND {clause_sa}""",
                [frontier, *params_sa],
            ).fetchall()

            next_frontier: list = []
            for r, direction in [(r, "outbound") for r in out_rows] + [(r, "inbound") for r in in_rows]:
                eid = str(r["id"])
                if eid in seen_edges:
                    continue
                src_versions = version_at.get(str(r["src_node"]))
                if as_of is not None and src_versions and r["src_version"] not in src_versions:
                    continue  # re-project theo as_of: chỉ edge của version hiệu lực (D-13)
                seen_edges.add(eid)
                edges.append(GraphEdgeOut(**{k: r[k] for k in (
                    "id", "src_node", "src_version", "dst_node", "dst_norm",
                    "frontier_ref", "kind", "raw_citation", "confidence")}, direction=direction))
                for nid in (r["src_node"], r["dst_node"]):
                    if nid is not None and str(nid) not in seen_nodes:
                        seen_nodes.add(str(nid))
                        next_frontier.append(nid)
            frontier = next_frontier

        clause_a, params_a = gate.audience_clause(role)
        nrows = conn.execute(
            f"""SELECT n.id AS node_id, n.path, n.label, n.role, a.doc_key, a.audience,
                       (SELECT heading FROM node_version nv WHERE nv.node_id = n.id
                        ORDER BY version DESC LIMIT 1) AS heading
                FROM node n JOIN artifact a ON a.id = n.artifact_id
                WHERE n.id = ANY(%s::uuid[]) AND {clause_a}""",
            [list(seen_nodes), *params_a],
        ).fetchall()
        gate.assert_no_leak(role, [r["audience"] for r in nrows])  # defense-in-depth INV-12
        visible_ids = {str(r["node_id"]) for r in nrows}
        edges = [e for e in edges  # edge chỉ nêu khi CẢ HAI đầu node (nếu có) đều visible
                 if str(e.src_node) in visible_ids
                 and (e.dst_node is None or str(e.dst_node) in visible_ids)]

        norm_ids = sorted({str(e.dst_norm) for e in edges if e.dst_norm})
        norms: list[dict] = []
        if norm_ids:
            norms = conn.execute(
                f"""SELECT DISTINCT nm.id, nm.topic FROM norm nm
                    JOIN artifact a ON a.id = nm.artifact_id
                    WHERE nm.id = ANY(%s::uuid[]) AND {clause_a}""",
                [norm_ids, *params_a],
            ).fetchall()

        return GraphOut(
            key=key,
            center_nodes=center_ids,
            depth=depth,
            as_of=as_of,
            nodes=[GraphNodeOut(**r, is_center=r["node_id"] in center_ids) for r in nrows],
            edges=edges,
            norms=[dict(n) for n in norms],
            note=note,
        )


@router.get("/norms/{norm_id}", response_model=NormOut)
def norm_chain(norm_id: uuidlib.UUID, role: str = Depends(get_role)):
    """Chuỗi kế vị của một Norm (D-09) + correlation NON-BINDING (D-08)."""
    with db.tx() as conn:
        clause, params = gate.audience_clause(role)
        rows = conn.execute(
            f"""SELECT nm.id, nm.topic, nm.artifact_id, nm.valid_from, nm.valid_to, nm.correlation,
                       a.doc_key, a.title, a.doc_type, a.issuer
                FROM norm nm JOIN artifact a ON a.id = nm.artifact_id
                WHERE nm.id = %s AND {clause}
                ORDER BY nm.valid_from NULLS FIRST""",
            [norm_id, *params],
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Không thấy norm (hoặc ngoài quyền audience).")
        return NormOut(
            id=norm_id,
            topic=rows[0]["topic"],
            incarnations=[NormIncarnation(**{k: r[k] for k in (
                "artifact_id", "doc_key", "title", "doc_type", "issuer",
                "valid_from", "valid_to", "correlation")}) for r in rows],
        )


@router.get("/artifacts/{doc_key:path}", response_model=ArtifactOut)
def artifact_source(doc_key: str, role: str = Depends(get_role)):
    """Văn bản gốc (L0) cho citation panel 'link văn bản gốc' — audience-gated."""
    with db.tx() as conn:
        clause, params = gate.audience_clause(role)
        row = conn.execute(
            f"""SELECT id, doc_key, doc_type, issuer, title, issued_date, effective_date,
                       audience, channel, is_oracle, synthetic, ingested_at, text
                FROM artifact a WHERE doc_key = %s AND {clause}""",
            [doc_key, *params],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không thấy văn bản (hoặc ngoài quyền audience).")
        return ArtifactOut(**row)
