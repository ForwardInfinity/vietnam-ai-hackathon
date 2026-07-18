"""Tier function TOTAL (R-34, D-31) + freshness (R-35, D-32) — verification nhóm 7."""
from datetime import date, datetime, timedelta, timezone

import pytest

from answer import freshness
from answer.tiers import TierInputs, decide_tier
from retrieval.query_builder import CoverageRow


def _i(**kw):
    base = dict(retrieval_floor=True, in_coverage=True, closure_complete=True,
                composer_refusal=False, hard_pass=True, flags=frozenset(),
                judge_state="calibrated", judge_all_pass=True)
    base.update(kw)
    return TierInputs(**base)


# ---------------------------------------------------------------- D trước hết

@pytest.mark.parametrize("kw,reason", [
    (dict(retrieval_floor=False), "no_retrieval_floor"),
    (dict(in_coverage=False), "outside_coverage"),
    (dict(closure_complete=False), "closure_incomplete"),
    (dict(composer_refusal=True), "composer_refusal"),
])
def test_tier_d_each_condition(kw, reason):
    d = decide_tier(_i(**kw))
    assert d.tier == "D" and reason in d.reasons


def test_tier_d_wins_over_everything():
    d = decide_tier(_i(closure_complete=False, hard_pass=False,
                       flags=frozenset({"in_conflict"})))
    assert d.tier == "D"


# ---------------------------------------------------------------- C = ¬hard_pass

def test_tier_c_hard_fail():
    assert decide_tier(_i(hard_pass=False)).tier == "C"


def test_tier_c_beats_flags_and_judge():
    d = decide_tier(_i(hard_pass=False, flags=frozenset({"pending_change"}),
                       judge_state="off"))
    assert d.tier == "C" and d.reasons == ("hard_verifier_fail",)


# ---------------------------------------------------------------- B

@pytest.mark.parametrize("flag", ["in_conflict", "cohort_ambiguous",
                                  "consolidation_pending", "pending_change",
                                  "open_suspension"])
def test_tier_b_each_flag(flag):
    d = decide_tier(_i(flags=frozenset({flag})))
    assert d.tier == "B" and flag in d.reasons


def test_tier_b_judge_uncalibrated_caps():
    d = decide_tier(_i(judge_state="uncalibrated"))
    assert d.tier == "B" and d.judge_capped


def test_tier_b_judge_off_caps():
    d = decide_tier(_i(judge_state="off"))
    assert d.tier == "B" and d.judge_capped


def test_tier_b_judge_fail_caps():
    d = decide_tier(_i(judge_all_pass=False))
    assert d.tier == "B" and "judge_fail" in d.reasons


# ---------------------------------------------------------------- A

def test_tier_a_requires_everything():
    d = decide_tier(_i())
    assert d.tier == "A" and not d.judge_capped and d.reasons == ()


def test_unknown_flag_raises_total_domain():
    with pytest.raises(ValueError):
        decide_tier(_i(flags=frozenset({"made_up_flag"})))


def test_totality_over_bool_grid():
    """Hàm total: mọi tổ hợp bool đều cho ra đúng một tier hợp lệ."""
    from itertools import product
    for rf, cov, clo, ref, hard, flagged, js in product(
            (True, False), (True, False), (True, False), (True, False),
            (True, False), (True, False), ("calibrated", "uncalibrated", "off")):
        d = decide_tier(_i(retrieval_floor=rf, in_coverage=cov, closure_complete=clo,
                           composer_refusal=ref, hard_pass=hard,
                           flags=frozenset({"in_conflict"} if flagged else set()),
                           judge_state=js, judge_all_pass=js == "calibrated"))
        assert d.tier in ("A", "B", "C", "D")
        if not (rf and cov and clo and not ref):
            assert d.tier == "D"
        elif not hard:
            assert d.tier == "C"
        elif flagged or js != "calibrated":
            assert d.tier == "B"
        else:
            assert d.tier == "A"


# ---------------------------------------------------------------- freshness

NOW = datetime(2026, 7, 18, tzinfo=timezone.utc)


def _cov(channel="congbao", checked=NOW):
    return CoverageRow(channel=channel, last_seq="59/2026", last_checked=checked)


def test_no_coverage_rows_out_of_coverage():
    assert freshness.in_coverage([], date(2024, 1, 1)) is False


def test_past_as_of_in_coverage():
    assert freshness.in_coverage([_cov()], date(2018, 1, 1)) is True


def test_today_within_ttl():
    assert freshness.in_coverage([_cov()], NOW.date()) is True


def test_beyond_ttl_horizon_out():
    horizon = NOW.date() + timedelta(days=freshness.ttl_for("congbao"))
    assert freshness.in_coverage([_cov()], horizon) is True
    assert freshness.in_coverage([_cov()], horizon + timedelta(days=1)) is False


def test_ttl_static_config():
    assert freshness.ttl_for("congbao") == 7
    assert freshness.ttl_for("internal_registry") == 30
    assert freshness.ttl_for("kênh_lạ") == freshness.FALLBACK_TTL_DAYS


def test_attestation_vi_lists_channels():
    s = freshness.attestation_vi([_cov(), _cov(channel="internal_registry")])
    assert "congbao" in s and "internal_registry" in s and "59/2026" in s
