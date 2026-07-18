"""Verifier CỨNG — code, LUÔN bật, không tắt được (R-32, D-30, INV-7).

Ba kiểm tra sound trên output composer so với ĐÚNG context đã cấp:
  1. Mọi tag [n] trong answer_vi và mọi claim.refs ∈ tập ref của context.
  2. Mọi đoạn trong ngoặc kép ("…", “…”, «…») khớp fuzzy ≥ 0.9 với text snapshot
     của ref được claim trích.
  3. Mọi CON SỐ trong claim tồn tại EXACT trong text ref (so theo digit-run đầy
     đủ — '15' không được ăn theo '2015'). Số người dùng đưa trong câu hỏi
     (as_of, mốc họ nêu) được whitelist — chúng là khung câu hỏi, không phải
     khẳng định cần bằng chứng.

Fail → caller regenerate đúng 1 lần → fail nữa → Tier C sources-only
(chỉ trích dẫn ghim, KHÔNG một chữ văn tổng hợp nào được render — INV-7).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from api.schemas import ComposerOutput

FUZZY_THRESHOLD = 0.9
MIN_QUOTE_CHARS = 10  # dưới ngưỡng này coi là nhấn mạnh từ, không phải trích dẫn

_TAG_RE = re.compile(r"\[(\d+)\]")
_QUOTE_RE = re.compile(r'"([^"]{%d,}?)"|“([^”]{%d,}?)”|«([^»]{%d,}?)»'
                       % (MIN_QUOTE_CHARS, MIN_QUOTE_CHARS, MIN_QUOTE_CHARS))
_DIGIT_RUN_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class HardFailure:
    kind: str          # ref_outside_context | quote_mismatch | number_mismatch | tag_unbacked
    detail: str


@dataclass
class HardVerdict:
    passed: bool
    failures: list[HardFailure] = field(default_factory=list)

    def feedback(self) -> str:
        return "; ".join(f"{f.kind}: {f.detail}" for f in self.failures)


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def digit_runs(s: str) -> set[str]:
    return set(_DIGIT_RUN_RE.findall(s))


def fuzzy_best_ratio(quote: str, text: str) -> float:
    """Ratio tốt nhất của quote so với các cửa sổ trượt trên text (đủ cho span
    vài trăm ký tự; corpus node ngắn)."""
    q, t = _norm_ws(quote), _norm_ws(text)
    if not q or not t:
        return 0.0
    if q.lower() in t.lower():
        return 1.0
    w = len(q)
    if len(t) <= w:
        return SequenceMatcher(None, q.lower(), t.lower()).ratio()
    best, step = 0.0, max(10, w // 5)
    for start in range(0, len(t) - w + 1, step):
        r = SequenceMatcher(None, q.lower(), t[start:start + w + step].lower()).ratio()
        if r > best:
            best = r
            if best >= 0.999:
                break
    return best


def _quotes_in(text: str) -> list[str]:
    return [next(g for g in m.groups() if g) for m in _QUOTE_RE.finditer(text)]


def verify(out: ComposerOutput, context_texts: dict[str, str],
           question_numbers: set[str] | None = None) -> HardVerdict:
    """context_texts: ref '[n]' → FULL text đã cấp cho composer (header + body)."""
    failures: list[HardFailure] = []
    refs = set(context_texts)
    question_numbers = question_numbers or set()

    # (1) tag & ref hợp lệ
    for tag in _TAG_RE.findall(out.answer_vi or ""):
        if f"[{tag}]" not in refs:
            failures.append(HardFailure("ref_outside_context", f"tag [{tag}] không có trong context"))
    for c in out.claims:
        if not c.refs:
            failures.append(HardFailure("ref_outside_context", f"claim {c.id} không trích nguồn nào"))
        for r in c.refs:
            if r not in refs:
                failures.append(HardFailure("ref_outside_context", f"claim {c.id} trích {r} ngoài context"))
    for b in out.bases:
        if b.ref not in refs:
            failures.append(HardFailure("ref_outside_context", f"basis {b.ref} ngoài context"))

    # (2) quote fuzzy ≥ 0.9 với snapshot; (3) con số exact
    for c in out.claims:
        cited = [context_texts[r] for r in c.refs if r in refs]
        cited_all = "\n".join(cited)
        for q in _quotes_in(c.text):
            if not cited or max((fuzzy_best_ratio(q, t) for t in cited), default=0.0) < FUZZY_THRESHOLD:
                failures.append(HardFailure(
                    "quote_mismatch", f"claim {c.id}: “{q[:80]}…” không khớp ≥{FUZZY_THRESHOLD} với nguồn đã trích"))
        claim_wo_tags = _TAG_RE.sub(" ", c.text)
        source_runs = digit_runs(cited_all) | question_numbers
        for run in digit_runs(claim_wo_tags):
            if run not in source_runs:
                failures.append(HardFailure(
                    "number_mismatch", f"claim {c.id}: con số '{run}' không tồn tại exact trong ref đã trích"))

    # quote trần trong answer_vi (ngoài claim): so với toàn context
    all_ctx = "\n".join(context_texts.values())
    claim_quotes = {q for c in out.claims for q in _quotes_in(c.text)}
    for q in _quotes_in(out.answer_vi or ""):
        if q in claim_quotes:
            continue
        if fuzzy_best_ratio(q, all_ctx) < FUZZY_THRESHOLD:
            failures.append(HardFailure("quote_mismatch", f"answer_vi: “{q[:80]}…” không khớp snapshot"))

    return HardVerdict(passed=not failures, failures=failures)
