"""INV-COMP-01 — trần lãi suất nhất quán: nội bộ SHB vs pháp quy (TT39 Đ13 / NQ01).

Trích các mệnh đề "tối đa|không vượt quá X%/năm" trong text lãi suất đang ACTIVE tại as_of,
gom theo gợi ý phân loại kỳ hạn; trần NỘI BỘ cao hơn trần PHÁP QUY cùng phân loại → violation
(nội bộ THẤP hơn = siết nghĩa vụ của mình = tuân thủ, D-34 — không bắn).
Giới hạn v1: phân loại theo keyword kỳ hạn; matcher theo mảng chủ đề là việc vòng sau.
"""
from __future__ import annotations

import re

from engine.invariants import EffectiveState, Violation, register

_RATE = re.compile(r"(?:tối\s*đa|không\s*vượt\s*quá)[^0-9%]{0,80}?(\d+(?:[.,]\d+)?)\s*%\s*/\s*năm",
                   re.IGNORECASE)
_CATEGORIES = (("ngắn hạn", "ngan_han"), ("trung hạn", "trung_han"), ("dài hạn", "dai_han"))


def _category(text: str, pos: int) -> str:
    window = text[max(0, pos - 120):pos + 40].lower()
    for needle, cat in _CATEGORIES:
        if needle in window:
            return cat
    return "chung"


def check(state: EffectiveState) -> list[Violation]:
    ceilings: dict[str, dict[str, list[tuple[float, tuple, str]]]] = {}
    for node, art, v in state.active():
        text = " ".join(t for t in (v.heading, v.body) if t)
        if "lãi suất" not in text.lower():
            continue
        side = "internal" if art.issuer.startswith("SHB") else "external"
        for m in _RATE.finditer(text):
            rate = float(m.group(1).replace(",", "."))
            cat = _category(text, m.start())
            ceilings.setdefault(cat, {}).setdefault(side, []).append(
                (rate, (v.node_id, v.version), art.doc_key))
    out: list[Violation] = []
    for cat, sides in sorted(ceilings.items()):
        if "internal" not in sides or "external" not in sides:
            continue
        ext_rate, ext_ref, ext_doc = min(sides["external"])
        for rate, ref, doc in sorted(sides["internal"]):
            if rate > ext_rate:
                out.append(Violation(
                    invariant_id="INV-COMP-01",
                    reason=(f"Trần lãi suất [{cat}] không nhất quán: {doc} quy định "
                            f"{rate:g}%/năm > trần pháp quy {ext_rate:g}%/năm ({ext_doc})"),
                    members=(ref, ext_ref)))
    return out


register("INV-COMP-01", check)
