"""INV-COMP-02 — ngày áp dụng quy định Phiếu lý lịch tư pháp nhất quán (fixture TT11/2026).

TT11 có hiệu lực PHÂN KỲ theo chủ đề (02 §3): các quy định về Phiếu LLTP hiệu lực
01/07/2026 ≠ ngày chung. Mọi node active nhắc "Phiếu lý lịch tư pháp" kèm một ngày áp dụng
phải nêu CÙNG một ngày — lệch nhau là mầm trả-lời-hai-mặt → violation tier-3.
"""
from __future__ import annotations

import re
from datetime import date

from engine.invariants import EffectiveState, Violation, register

_CTX = "lý lịch tư pháp"
_D_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_D_WORDS = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)


def _dates(text: str) -> set[date]:
    """Ngày GẮN VỚI ngữ cảnh LLTP: cụm 'lý lịch tư pháp' phải đứng TRƯỚC ngày trong
    cửa sổ 120 ký tự (mẫu “quy định về Phiếu LLTP … từ ngày D”) — ngày hiệu lực chung
    đứng liền kề phía trước không bị vơ nhầm."""
    low = text.lower()
    out = set()
    for rx in (_D_SLASH, _D_WORDS):
        for m in rx.finditer(text):
            if _CTX not in low[max(0, m.start() - 120):m.start()]:
                continue
            d, mth, y = (int(g) for g in m.groups())
            try:
                out.add(date(y, mth, d))
            except ValueError:
                pass
    return out


def check(state: EffectiveState) -> list[Violation]:
    seen: dict[date, list[tuple[tuple, str]]] = {}
    for node, art, v in state.active():
        text = " ".join(t for t in (v.heading, v.body) if t)
        if _CTX not in text.lower():
            continue
        for d in _dates(text):
            seen.setdefault(d, []).append(((v.node_id, v.version), art.doc_key))
    if len(seen) <= 1:
        return []
    listing = "; ".join(f"{d.isoformat()} ({', '.join(doc for _, doc in refs)})"
                        for d, refs in sorted(seen.items()))
    members = tuple(ref for refs in seen.values() for ref, _ in refs)
    return [Violation(
        invariant_id="INV-COMP-02",
        reason=f"Ngày áp dụng quy định Phiếu lý lịch tư pháp không nhất quán: {listing}",
        members=members)]


register("INV-COMP-02", check)
