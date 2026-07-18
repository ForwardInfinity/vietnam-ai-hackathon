"""Conflict: incomparable → certificate unsat-core (D-33); precedence có cửa sổ (D-15);
nhãn D-34 (chat_hon_ve_minh TỰ LOẠI); ownership fork (D-35)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from api import schemas
from engine.conflict import (default_precedence, fork_for, label_pair, precedence_rank)
from engine.fold import fold_corpus
from engine.model import ArtifactInput, ConflictCertificate, NodeInput


def _art(id_, doc_type, issuer, issued, eff):
    return ArtifactInput(id=id_, doc_key=id_.removeprefix("art:"), doc_type=doc_type,
                         issuer=issuer, issued_date=issued, effective_date=eff)


def _op(art, seq, node_id, text, vf, kind="amend"):
    return schemas.Op(id=uuid4(), kind=kind, source_artifact=art, source_quote="q",
                      seq=seq, target_node=node_id, new_text=text, valid_from=vf,
                      status="ratified", extractor="test",
                      ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_incomparable_same_rank_different_issuer_yields_certificate():
    """Hai thông tư của HAI BỘ khác nhau cùng amend một node, cửa sổ chồng nhau —
    Đ156 không phân định (không cùng cơ quan, cùng hạng) → certificate, KHÔNG chọn bừa."""
    node_id = uuid4()
    arts = {
        "art:X": _art("art:X", "thong_tu", "NHNN", date(2023, 1, 1), date(2023, 2, 1)),
        "art:Y": _art("art:Y", "thong_tu", "BTC", date(2023, 3, 1), date(2023, 4, 1)),
        "art:BASE": _art("art:BASE", "thong_tu", "NHNN", date(2020, 1, 1), date(2020, 2, 1)),
    }
    nodes = [NodeInput(id=node_id, artifact_id="art:BASE", doc_key="BASE", path="dieu:1",
                       body="gốc")]
    ops = [_op("art:X", 1, node_id, "text NHNN", date(2023, 2, 1)),
           _op("art:Y", 1, node_id, "text BTC", date(2023, 4, 1))]
    cf = fold_corpus(nodes, ops, arts)
    assert node_id not in cf.versions                    # node treo lại ở certificate
    assert len(cf.certificates) == 1
    cert = cf.certificates[0]
    assert isinstance(cert, ConflictCertificate) and cert.tier == 2
    assert set(cert.member_ops) == {ops[0].id, ops[1].id}    # unsat-core
    assert cert.doctrine["art156"] == "khong_phan_dinh"
    assert cert.doctrine["same_issuer"] is False
    assert cert.window_from == date(2023, 4, 1)          # vùng chồng lấn

    # cùng ca nhưng CÙNG cơ quan → lex posterior tự phân định, không certificate
    arts["art:Y2"] = _art("art:Y2", "thong_tu", "NHNN", date(2023, 3, 1), date(2023, 4, 1))
    ops2 = [_op("art:X", 1, node_id, "text 2023-02", date(2023, 2, 1)),
            _op("art:Y2", 1, node_id, "text 2023-04", date(2023, 4, 1))]
    cf2 = fold_corpus(nodes, ops2, arts)
    assert cf2.certificates == ()
    assert [v.body for v in cf2.versions[node_id]] == ["gốc", "text 2023-02", "text 2023-04"]


def test_tier1_cap_tren_thang_auto_resolved():
    """Khác hạng (nghị định vs thông tư) → tier-1 cấp trên thắng, có note, không certificate."""
    node_id = uuid4()
    arts = {
        "art:ND": _art("art:ND", "nghi_dinh", "CP", date(2023, 1, 1), date(2023, 2, 1)),
        "art:TT": _art("art:TT", "thong_tu", "NHNN", date(2023, 3, 1), date(2023, 4, 1)),
        "art:BASE": _art("art:BASE", "thong_tu", "NHNN", date(2020, 1, 1), date(2020, 2, 1)),
    }
    nodes = [NodeInput(id=node_id, artifact_id="art:BASE", doc_key="BASE", path="dieu:1",
                       body="gốc")]
    ops = [_op("art:ND", 1, node_id, "text nghị định", date(2023, 2, 1)),
           _op("art:TT", 1, node_id, "text thông tư", date(2023, 4, 1))]
    cf = fold_corpus(nodes, ops, arts)
    assert cf.certificates == ()
    final = cf.versions[node_id][-1]
    assert final.body == "text nghị định"                # cấp trên thắng trên vùng chồng
    assert any("tier1-auto" in n for n in cf.notes)


def test_precedence_windowed_and_parameterized():
    """Precedence là bảng CÓ cửa sổ (D-15): rank tra theo thời điểm; tham số hóa được."""
    rows = default_precedence()
    assert precedence_rank("nghi_dinh", "CP", date(2023, 1, 1), rows) < \
        precedence_rank("thong_tu", "NHNN", date(2023, 1, 1), rows)
    assert precedence_rank("noi_bo", "SHB.QLRR", date(2023, 1, 1), rows) > \
        precedence_rank("thong_tu", "NHNN", date(2023, 1, 1), rows)
    assert precedence_rank("la_gi_do", "AI_BIET", date(2023, 1, 1), rows) == 99  # default

    class Row:
        def __init__(self, doc_type, issuer, rank, valid_from=None, valid_to=None):
            self.doc_type, self.issuer, self.rank = doc_type, issuer, rank
            self.valid_from, self.valid_to = valid_from, valid_to
            self.source_node = None

    custom = [Row("thong_tu", None, 7, valid_from=date(2016, 7, 1)),
              Row("thong_tu", None, 5, valid_to=date(2016, 7, 1))]   # luật BHVBQPPL đổi
    assert precedence_rank("thong_tu", "NHNN", date(2016, 6, 1), custom) == 5
    assert precedence_rank("thong_tu", "NHNN", date(2016, 8, 1), custom) == 7


def test_label_pair_d34():
    """chat_hon_ve_minh (siết nghĩa vụ CỦA ngân hàng) = tuân thủ → TỰ LOẠI;
    chat_hon_ve_doi_tac → vào queue; khac_pham_vi → loại."""
    assert label_pair("i", "e", llm=lambda p: {"label": "chat_hon_ve_minh"}) is None
    assert label_pair("i", "e", llm=lambda p: {"label": "khac_pham_vi"}) is None
    assert label_pair("i", "e", llm=lambda p: {"label": "chat_hon_ve_doi_tac"}) \
        == "chat_hon_ve_doi_tac"
    assert label_pair("i", "e", llm=lambda p: {"label": "mau_thuan"}) == "mau_thuan"
    assert label_pair("i", "e", llm=None) == "mau_thuan"     # fallback bảo thủ: đưa người xét
    with pytest.raises(ValueError):
        label_pair("i", "e", llm=lambda p: {"label": "nhãn_bịa"})


def test_fork_for_d35():
    assert fork_for("SHB.QLRR", "SHB.CSTD") == "internal_internal"
    assert fork_for("SHB.QLRR", "NHNN") == "internal_external"
    assert fork_for("NHNN", "QH") == "external_external"
    assert fork_for("SHB.QLRR", "NHNN", frontier=True) == "advisory"
