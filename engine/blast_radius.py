"""Blast-radius qua where-used (S4.8, R-23, D-36).

Khi op ratified: inbound edge tới target (kể cả `chu_de` qua Norm của artifact chứa target)
→ notification cho CHỦ CÓ TÊN. Severity `interruptive` bắt-ack là NGOẠI LỆ HIẾM — CHỈ khi
op definitional; còn lại `advisory` digest (chống bão ack). Biểu mẫu nhận propagation như
mọi tài liệu (doc_type `bieu_mau` không có đường tắt).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from api import schemas
from engine.model import ArtifactInput, NodeInput, sv


def resolve_target_node(op: Any, ops_by_id: Mapping[UUID, Any]) -> UUID | None:
    """target node trực tiếp; op-nhắm-op → node của op đích (một tầng)."""
    if op.target_node is not None:
        return op.target_node
    if op.target_op is not None:
        target = ops_by_id.get(op.target_op)
        return target.target_node if target is not None else None
    return None


def where_used(target_node: UUID | None, target_artifact: str | None,
               edges: Iterable[Any],
               norm_memberships: Mapping[UUID, set[str]] | None = None) -> list[Any]:
    """Inbound edges: trỏ thẳng node, hoặc trỏ Norm mà artifact chứa target là hiện thân."""
    hits = []
    for e in edges:
        if target_node is not None and e.dst_node == target_node:
            hits.append(e)
        elif (e.dst_norm is not None and norm_memberships is not None
              and target_artifact is not None
              and target_artifact in norm_memberships.get(e.dst_norm, set())):
            hits.append(e)
    return hits


def notifications_for_op(
    op: Any, *,
    ops_by_id: Mapping[UUID, Any],
    nodes_by_id: Mapping[UUID, NodeInput],
    artifacts: Mapping[str, ArtifactInput],
    edges: Sequence[Any],
    norm_memberships: Mapping[UUID, set[str]] | None = None,
) -> list[schemas.Notification]:
    """→ một notification mỗi node đang cite target (affected = BÊN CITE có thể stale)."""
    target = resolve_target_node(op, ops_by_id)
    target_artifact = nodes_by_id[target].artifact_id if target in nodes_by_id else None
    severity = "interruptive" if sv(op.risk_class) == "definitional" else "advisory"  # D-36
    out: list[schemas.Notification] = []
    seen: set[UUID] = set()
    for e in where_used(target, target_artifact, edges, norm_memberships):
        if e.src_node in seen:
            continue
        seen.add(e.src_node)
        src = nodes_by_id.get(e.src_node)
        src_art = artifacts.get(src.artifact_id) if src else None
        out.append(schemas.Notification(
            op_id=op.id,
            affected_node=e.src_node,
            affected_doc=src.doc_key if src else None,
            owner=src_art.owner if src_art else None,
            severity=severity))
    return sorted(out, key=lambda n: (str(n.affected_doc), str(n.affected_node)))
