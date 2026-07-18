"""Property-based (hypothesis) cho tiling (INV-4) + determinism (INV-3) — op ngẫu nhiên."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from hypothesis import given, settings, strategies as st

from api import schemas
from engine.fold import fold_corpus, state_digest, verify_tiling
from engine.model import ArtifactInput, NodeInput

NODE_ID = uuid4()
ARTS = {
    "art:A": ArtifactInput(id="art:A", doc_key="A/2020/TT-NHNN", doc_type="thong_tu",
                           issuer="NHNN", issued_date=date(2020, 1, 5),
                           effective_date=date(2020, 2, 1)),
    "art:B": ArtifactInput(id="art:B", doc_key="B/2021/TT-NHNN", doc_type="thong_tu",
                           issuer="NHNN", issued_date=date(2021, 2, 3),
                           effective_date=date(2021, 3, 1)),
}
NODES = [NodeInput(id=NODE_ID, artifact_id="art:A", doc_key="A/2020/TT-NHNN",
                   path="dieu:1", body="văn bản gốc")]


@st.composite
def op_lists(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    ops = []
    for i in range(n):
        kind = draw(st.sampled_from(["amend", "suspend", "repeal"]))
        vf = date(2020, 2, 1) + timedelta(days=draw(st.integers(0, 2500)))
        vt = None
        if kind == "suspend" and draw(st.booleans()):
            vt = vf + timedelta(days=draw(st.integers(1, 700)))
        art = draw(st.sampled_from(["art:A", "art:B"]))
        ops.append(schemas.Op(
            id=uuid4(), kind=kind, source_artifact=art, source_quote=f"op {i}",
            seq=i + 1, target_node=NODE_ID,
            new_text=f"text {i}" if kind == "amend" else None,
            valid_from=vf, valid_to=vt, status="ratified", extractor="hypothesis",
            ingested_at=datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)))
    return ops


@settings(max_examples=60, deadline=None)
@given(ops=op_lists(), seed=st.integers(0, 2**16))
def test_tiling_and_determinism_property(ops, seed):
    cf = fold_corpus(NODES, ops, ARTS)
    assert verify_tiling(cf.versions) == [], "INV-4 vỡ với op ngẫu nhiên"
    shuffled = list(ops)
    random.Random(seed).shuffle(shuffled)
    assert state_digest(fold_corpus(NODES, shuffled, ARTS)) == state_digest(cf), \
        "INV-3 vỡ: thứ tự nạp đổi kết quả"
    # phủ liên tục từ hiệu lực đầu và mọi version tham chiếu đúng node
    for vs in cf.versions.values():
        assert vs[0].valid_from == date(2020, 2, 1)
        assert all(v.node_id == NODE_ID for v in vs)
