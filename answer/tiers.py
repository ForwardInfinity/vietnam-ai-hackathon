"""Thang tier — hàm TOTAL đúng công thức R-34 (D-31).

D  nếu ¬retrieval_floor ∨ ngoài coverage ∨ closure_incomplete ∨ composer refusal
C  nếu ¬hard_pass (sau 1 regen) — sources-only, KHÔNG văn tổng hợp (INV-7)
B  nếu hard_pass ∧ (flags≠∅ ∨ judge chưa-κ/off/fail)
A  nếu hard_pass ∧ judge pass ∧ flags=∅

flags := {in_conflict, cohort_ambiguous, consolidation_pending, pending_change,
          open_suspension}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TierT = Literal["A", "B", "C", "D"]

VALID_FLAGS = frozenset({"in_conflict", "cohort_ambiguous", "consolidation_pending",
                         "pending_change", "open_suspension"})

JudgeState = Literal["calibrated", "uncalibrated", "off"]


@dataclass(frozen=True)
class TierInputs:
    retrieval_floor: bool          # có candidate sau hybrid không
    in_coverage: bool              # as_of nằm trong coverage attestation + TTL
    closure_complete: bool         # R-29
    composer_refusal: bool         # composer trả refusal (thiếu căn cứ)
    hard_pass: bool                # verifier cứng (sau tối đa 1 regen)
    flags: frozenset[str] = frozenset()
    judge_state: JudgeState = "uncalibrated"
    judge_all_pass: bool = False   # mọi claim entails (chỉ có nghĩa khi calibrated)


@dataclass(frozen=True)
class TierDecision:
    tier: TierT
    reasons: tuple[str, ...]
    judge_capped: bool             # có cap B vì judge chưa-κ/off/fail không


def decide_tier(i: TierInputs) -> TierDecision:
    unknown = i.flags - VALID_FLAGS
    if unknown:
        raise ValueError(f"flag không hợp lệ: {sorted(unknown)}")

    reasons: list[str] = []
    if not i.retrieval_floor:
        reasons.append("no_retrieval_floor")
    if not i.in_coverage:
        reasons.append("outside_coverage")
    if not i.closure_complete:
        reasons.append("closure_incomplete")
    if i.composer_refusal:
        reasons.append("composer_refusal")
    if reasons:
        return TierDecision(tier="D", reasons=tuple(reasons), judge_capped=False)

    if not i.hard_pass:
        return TierDecision(tier="C", reasons=("hard_verifier_fail",), judge_capped=False)

    judge_capped = i.judge_state != "calibrated" or not i.judge_all_pass
    if i.flags or judge_capped:
        rs = tuple(sorted(i.flags)) + (("judge_" + i.judge_state,) if i.judge_state != "calibrated"
                                       else (() if i.judge_all_pass else ("judge_fail",)))
        return TierDecision(tier="B", reasons=rs, judge_capped=judge_capped)

    return TierDecision(tier="A", reasons=(), judge_capped=False)
