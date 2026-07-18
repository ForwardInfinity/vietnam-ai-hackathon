"""Sweep bổ sung (R-21): văn bản KHÔNG liên quan không sinh đề xuất; LLM chỉ ĐỀ XUẤT thêm;
văn bản không phải QPPL bị loại."""
from __future__ import annotations

from engine.sweep import sweep_pending


def test_khong_lien_quan_khong_de_xuat(corpus, folded):
    tt11 = corpus.artifacts_by_id["art:11/2026/TT-NHNN"]      # omnibus LLTP — khác chủ đề
    proposals = sweep_pending(folded.open_suspensions,
                              ops_by_id={o.id: o for o in corpus.ops},
                              artifact=tt11, artifacts=corpus.artifacts_by_id)
    assert proposals == []


def test_noi_bo_khong_phai_qppl_khong_de_xuat(corpus, folded):
    shb = corpus.artifacts_by_id["art:CS-LS-01/SHB"]
    proposals = sweep_pending(folded.open_suspensions,
                              ops_by_id={o.id: o for o in corpus.ops},
                              artifact=shb, artifacts=corpus.artifacts_by_id)
    assert proposals == []


def test_llm_de_xuat_ung_vien_bo_sung(corpus, folded):
    """Rule không khớp nhưng LLM gateway đề xuất → thành proposal (vẫn proposed, người chốt)."""
    tt11 = corpus.artifacts_by_id["art:11/2026/TT-NHNN"]
    calls = []

    def fake_llm(payload):
        calls.append(payload)
        return {"candidate": True, "rationale": "quy định lại đúng các vấn đề bị ngưng",
                "confidence": 0.7}

    proposals = sweep_pending(folded.open_suspensions,
                              ops_by_id={o.id: o for o in corpus.ops},
                              artifact=tt11, artifacts=corpus.artifacts_by_id, llm=fake_llm)
    assert len(proposals) == 3 and len(calls) == 3
    assert all(str(p.op.status.value) == "proposed" for p in proposals)
    assert all(p.rationale.startswith("llm:") for p in proposals)
    assert {"predicate", "doc_key", "title", "excerpt"} <= set(calls[0])
