"""Context pack + banner + piecewise render (R-30, R-31)."""
from datetime import date

from answer.compose import (CUSTOMER_DISCLAIMER, FLAG_BANNER_ORDER, OfflineComposer,
                            assemble_banners, build_context_pack, build_piecewise_blocks,
                            clarify_question_for, detect_branch_groups, format_interval,
                            scope_desc, surface_of_path)
from api.schemas import ComposerClaim, ComposerOutput
from retrieval.query_builder import OpBrief, SnapshotRow

GF = {"contract_signed_before": "2023-09-01", "not_amended_on_or_after": "2023-09-01"}


def _row(nid="n1", version=1, scope=None, shash="", prov=()):
    return SnapshotRow(
        node_id=nid, version=version, heading="Điều 13. Lãi suất cho vay",
        body="Nội dung lãi suất.", status="active", valid_from=date(2023, 9, 1),
        valid_to=None, scope_predicate=scope, scope_hash=shash, provenance=tuple(prov),
        run_id="r1", path="dieu:13", role="rule", artifact_id="a",
        doc_key="39/2016/TT-NHNN", audience="public")


# ------------------------------------------------------------------ header R-30

def test_context_header_has_all_fields():
    ops = {"op1": OpBrief("op1", "amend", "06/2023/TT-NHNN", date(2023, 9, 1))}
    pack = build_context_pack([_row(prov=["op1"])], ops)
    h = pack[0].header
    for frag in ("[1]", "39/2016/TT-NHNN", "dieu:13", "Điều 13",
                 "01/09/2023 → nay", "active", "scope: mọi chủ thể",
                 "sửa đổi bởi 06/2023/TT-NHNN"):
        assert frag in h, f"header thiếu {frag}: {h}"


def test_surface_and_interval_helpers():
    assert surface_of_path("dieu:8/khoan:2/diem:a") == "điểm a khoản 2 Điều 8"
    assert surface_of_path("phuluc:04") == "Phụ lục 04"
    assert format_interval(date(2017, 3, 15), date(2023, 9, 1)) == "15/03/2017 → 01/09/2023"
    assert format_interval(date(2023, 9, 1), None) == "01/09/2023 → nay"


def test_scope_desc():
    assert scope_desc(None) == "mọi chủ thể"
    s = scope_desc(GF)
    assert "trước 01/09/2023" in s and "chưa sửa đổi" in s


# ------------------------------------------------------------------ branches D-04

def test_detect_branch_groups_and_pack_labels():
    rows = [_row(version=2), _row(version=3, scope=GF, shash="gf")]
    groups = detect_branch_groups(rows)
    assert set(groups) == {"n1"}
    pack = build_context_pack(rows)
    assert pack[0].branch_label == "còn lại"
    assert "trước 01/09/2023" in pack[1].branch_label
    assert "NHÁNH" in pack[0].header


def test_clarify_question_exactly_one():
    groups = detect_branch_groups([_row(version=2), _row(version=3, scope=GF, shash="gf")])
    q = clarify_question_for(groups)
    assert q and q.count("?") == 1 and "01/09/2023" in q


def test_piecewise_blocks_branch_first_then_plain():
    rows = [_row(version=2), _row(version=3, scope=GF, shash="gf"),
            _row(nid="n2", version=1)]
    pack = build_context_pack(rows)
    out = ComposerOutput(
        answer_vi="x", refusal=None, bases=[],
        claims=[ComposerClaim(id="c1", text="chung [3]", refs=["[3]"]),
                ComposerClaim(id="c2", text="nhánh mới [1]", refs=["[1]"]),
                ComposerClaim(id="c3", text="nhánh cũ [2]", refs=["[2]"])])
    blocks = build_piecewise_blocks(out, pack)
    assert len(blocks) == 3
    assert blocks[0].cohort and blocks[1].cohort          # nhánh scope lên TRÊN
    assert blocks[-1].cohort is None                      # phần chung xuống dưới
    cohorts = {b.cohort for b in blocks}
    assert "còn lại" in cohorts


def test_piecewise_single_block_when_no_boundary():
    rows = [_row()]
    pack = build_context_pack(rows)
    out = ComposerOutput(answer_vi="toàn văn [1]", refusal=None, bases=[],
                         claims=[ComposerClaim(id="c1", text="x [1]", refs=["[1]"])])
    blocks = build_piecewise_blocks(out, pack)
    assert len(blocks) == 1 and blocks[0].text_vi == "toàn văn [1]"


def test_offline_composer_pulls_sibling_branches():
    """Không bao giờ trả lời MỘT NỬA ranh giới scope (D-04)."""
    rows = [_row(version=2), _row(nid="n2"), _row(nid="n3"), _row(nid="n4"),
            _row(version=3, scope=GF, shash="gf")]   # nhánh gf đứng CUỐI pack
    pack = build_context_pack(rows)
    out = OfflineComposer(max_claims=2).compose(None, "q", pack)
    cited = {r for c in out.claims for r in c.refs}
    assert "[1]" in cited and "[5]" in cited   # chọn [1] thì phải kéo nhánh anh em [5]


# ------------------------------------------------------------------ banner R-31

def test_banner_order_is_code_owned():
    banners = assemble_banners(
        {"pending_change", "in_conflict", "open_suspension", "cohort_ambiguous",
         "consolidation_pending"},
        judge_capped=True, audience="employee", clarify_question="Ký trước 2023?")
    kinds = [b.kind for b in banners]
    assert kinds[:5] == list(FLAG_BANNER_ORDER)     # thứ tự cố định, model không xen được
    assert kinds[5] == "judge_uncalibrated"
    assert kinds[6] == "clarify"


def test_customer_gets_disclaimer_never_clarify():
    banners = assemble_banners({"cohort_ambiguous"}, judge_capped=True,
                               audience="customer", clarify_question="Ký trước 2023?")
    kinds = [b.kind for b in banners]
    assert "clarify" not in kinds
    assert kinds[-1] == "disclaimer"
    assert banners[-1].text_vi == CUSTOMER_DISCLAIMER.text_vi


def test_no_flags_no_banners_for_employee_calibrated():
    assert assemble_banners(set(), judge_capped=False, audience="employee") == []
