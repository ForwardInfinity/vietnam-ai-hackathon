"""LLM THẬT (heavy + llm_live — chạy thủ công: uv run pytest -m llm_live tests/ingest).

Bộ theo yêu cầu task: TT06 (enumeration + insert), TT10 (ngưng ≠ bãi bỏ + sự kiện),
TT11-omnibus (context-stack + phân kỳ). Corpus thật nếu có; F2 chưa land → fixtures mini
(vẫn xác thực máy prompt/schema/merge với model thật).
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = [pytest.mark.heavy, pytest.mark.llm_live]

if not (os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_EXTRACT_API_KEY")
        or os.getenv("LLM_API_KEY")):
    pytest.skip("không có API key cho role extract — bỏ llm_live", allow_module_level=True)

from answer.llm_gateway import get_gateway                     # noqa: E402
from ingest import manifest as mf                              # noqa: E402
from ingest.orchestrator import ingest_corpus_pure             # noqa: E402
from tests.ingest.fixture_corpus import FIXTURE_ENTRIES, fixture_texts  # noqa: E402

TARGET_DOCS = ("06/2023/TT-NHNN", "10/2023/TT-NHNN", "11/2026/TT-NHNN")


@pytest.fixture(scope="module")
def live_corpus():
    entries = mf.load_manifest()
    texts: dict[str, str] = {}
    for e in entries:
        f = mf.find_file(e)
        if f is not None:
            texts[e["doc_key"]] = f.read_text(encoding="utf-8", errors="replace")
    if not all(dk in texts for dk in TARGET_DOCS):
        entries, texts = FIXTURE_ENTRIES, fixture_texts()
    gw = get_gateway()
    return ingest_corpus_pure(entries, texts, gateway=gw)


def test_live_tt06_llm_agrees_on_inserts(live_corpus):
    store, bundles = live_corpus
    ops = bundles["06/2023/TT-NHNN"].ops
    tt39_ops = [o for o in ops if o.kind in ("amend", "insert")
                and o.target_doc_key == "39/2016/TT-NHNN"]
    assert len(tt39_ops) >= 3, "TT06 phải sinh nhiều op amend/insert nhắm TT39"
    agreed = [o for o in tt39_ops if o.rule_llm_agree]
    assert agreed, "LLM thật phải đồng thuận với rule trên ít nhất 1 op (VD1 few-shot)"
    assert any(o.queue == "batch" for o in agreed), \
        "op cơ học rule↔LLM khớp phải batch-eligible (D-19)"


def test_live_tt10_suspend_not_repeal(live_corpus):
    store, bundles = live_corpus
    ops = bundles["10/2023/TT-NHNN"].ops
    sus = [o for o in ops if o.kind == "suspend"]
    assert len(sus) == 3
    assert all(o.valid_to_event for o in sus), "sự kiện chưa định danh phải vào valid_to_event"
    assert not [o for o in ops if o.kind == "repeal"], "LLM gộp ngưng→bãi bỏ là fail bẫy #3"


def test_live_tt11_omnibus_chapter_binding(live_corpus):
    store, bundles = live_corpus
    ops = bundles["11/2026/TT-NHNN"].ops
    tt39_targets = [o for o in ops if o.target_doc_key == "39/2016/TT-NHNN"]
    tt22_targets = [o for o in ops if o.target_doc_key == "22/2019/TT-NHNN"]
    assert tt39_targets and tt22_targets, \
        "context-stack theo Chương phải tách đích TT39 vs TT22 (bẫy #9)"
    divergent = [o for o in ops if str(o.valid_from) == "2026-07-01"
                 and "divergent_effective_date" in o.red_flags]
    assert divergent, "phân kỳ hiệu lực Phiếu LLTP 01/07/2026 ≠ ngày chung (bẫy #10)"
    assert all(o.queue == "per_op" for o in divergent), \
        "ngày-cần-phân-loại → per-op review (D-19)"
