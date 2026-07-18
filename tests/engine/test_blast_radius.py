"""Blast-radius (R-23, D-36): where-used → notification cho chủ có tên;
interruptive CHỈ khi definitional; chu_de qua Norm; op-nhắm-op resolve một tầng."""
from __future__ import annotations

from uuid import uuid4

from api import schemas
from engine.blast_radius import notifications_for_op, resolve_target_node, where_used
from engine.fixtures import fid


def _edges(corpus):
    """Edge dựng trong test (edge thật là của F3): QT-TD-01 mục 3.2 cite Đ7 TT39 pinpoint
    + cite theo mảng (chu_de → Norm cho-vay)."""
    qt = corpus.node("QT-TD-01/SHB", "muc:3.2")
    d7 = corpus.node("39/2016/TT-NHNN", "dieu:7")
    norm_cho_vay = fid("norm:cho-vay")
    return [
        schemas.Edge(src_node=qt.id, src_version=1, dst_node=d7.id, kind="dinh_nghia",
                     raw_citation="Điều 7 Thông tư 39/2016/TT-NHNN"),
        schemas.Edge(src_node=qt.id, src_version=1, dst_norm=norm_cho_vay, kind="chu_de",
                     raw_citation="quy định của NHNN về hoạt động cho vay"),
    ], norm_cho_vay


def test_notifications_owner_and_severity(corpus):
    edges, _ = _edges(corpus)
    d7 = corpus.node("39/2016/TT-NHNN", "dieu:7")
    nodes_by_id = {n.id: n for n in corpus.nodes}
    op = corpus.op("op:tt12-amend-d7")

    # prescriptive (mặc định) → advisory digest, KHÔNG interruptive (chống bão ack)
    notifs = notifications_for_op(op, ops_by_id={o.id: o for o in corpus.ops},
                                  nodes_by_id=nodes_by_id,
                                  artifacts=corpus.artifacts_by_id, edges=edges)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.owner == "Phòng Chính sách tín dụng"        # chủ CÓ TÊN
    assert n.affected_doc == "QT-TD-01/SHB"
    assert str(n.severity.value) == "advisory"

    # op definitional → interruptive (ngoại lệ hiếm D-36)
    op_def = op.model_copy(update={"risk_class": "definitional"})
    notifs = notifications_for_op(op_def, ops_by_id={}, nodes_by_id=nodes_by_id,
                                  artifacts=corpus.artifacts_by_id, edges=edges)
    assert str(notifs[0].severity.value) == "interruptive"


def test_chu_de_qua_norm(corpus):
    """Edge chu_de trỏ Norm: op chạm node của artifact-hiện-thân Norm → citing doc nhận notice."""
    edges, norm_id = _edges(corpus)
    d7 = corpus.node("39/2016/TT-NHNN", "dieu:7")
    hits = where_used(d7.id, "art:39/2016/TT-NHNN", edges,
                      norm_memberships={norm_id: {"art:39/2016/TT-NHNN"}})
    assert len(hits) == 2                                # pinpoint + chu_de
    hits_no_norm = where_used(d7.id, "art:39/2016/TT-NHNN", edges, norm_memberships=None)
    assert len(hits_no_norm) == 1


def test_resolve_target_qua_op(corpus):
    """Op nhắm op (TT08 bãi bỏ op của TT26): blast-radius resolve về node đích của op cũ."""
    repeal = corpus.op("op:tt08-repeal-tt26op")
    ops_by_id = {o.id: o for o in corpus.ops}
    target = resolve_target_node(repeal, ops_by_id)
    assert target == corpus.node("22/2019/TT-NHNN", "dieu:20/khoan:2").id
