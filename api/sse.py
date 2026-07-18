"""SSE cho POST /v1/ask (S6): meta → token → citation → banner → tier → done.

Contract stream (F6 sở hữu bề mặt; F5 sở hữu nội dung Answer):
  event: meta      data: {run_id, as_of, as_known, audience, coverage[]}
  event: token     data: {text}                      (0..n — thân trả lời tuần tự)
  event: citation  data: Basis JSON                  (0..n — mỗi căn cứ một event)
  event: banner    data: Banner JSON                 (0..n — ĐÚNG thứ tự code lắp R-31)
  event: tier      data: {tier, explain_vi, refusal_reason?}
  event: done      data: {qa_id, answer: Answer JSON đầy đủ}   (client render 4 mục từ đây)

JSON mode (Accept khác text/event-stream) giữ nguyên contract F1: trả Answer JSON.
"""
from __future__ import annotations

import json
from typing import Iterator

from api.schemas import Answer

TIER_EXPLAIN_VI = {
    "A": "Đã kiểm chứng sạch: mọi trích dẫn khớp snapshot, judge pass, không cờ nào.",
    "B": "Đã qua gate cứng, kèm banner (conflict/pending/cohort/consolidation hoặc judge chưa hiệu chuẩn).",
    "C": "Sources-only: chỉ trích dẫn ghim — văn tổng hợp không qua được gate cứng (INV-7).",
    "D": "Từ chối + route chuyên gia: thiếu căn cứ đã compile hoặc ngoài coverage.",
}


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _token_chunks(text: str, size: int = 24) -> Iterator[str]:
    """Chia text thành chunk ~size ký tự tại ranh giới khoảng trắng (stream mượt)."""
    words = text.split(" ")
    buf: list[str] = []
    length = 0
    for w in words:
        buf.append(w)
        length += len(w) + 1
        if length >= size:
            yield " ".join(buf) + " "
            buf, length = [], 0
    if buf:
        yield " ".join(buf)


def answer_to_events(ans: Answer) -> Iterator[str]:
    """Phân rã một Answer thành chuỗi SSE ĐÚNG TRÌNH TỰ S6."""
    dumped = json.loads(ans.model_dump_json())

    yield sse_event(
        "meta",
        {
            "run_id": dumped.get("run_id"),
            "as_of": dumped.get("as_of"),
            "as_known": dumped.get("as_known"),
            "audience": dumped.get("audience"),
            "coverage": dumped.get("coverage", []),
        },
    )

    if ans.tier == "D" and ans.refusal_reason:
        for chunk in _token_chunks(ans.refusal_reason):
            yield sse_event("token", {"text": chunk})
    else:
        for blk in ans.answer:
            header = ""
            if blk.interval_from or blk.interval_to or blk.cohort:
                parts = []
                if blk.interval_from or blk.interval_to:
                    parts.append(f"[{blk.interval_from or '…'} → {blk.interval_to or 'nay'}]")
                if blk.cohort:
                    parts.append(f"({blk.cohort})")
                header = " ".join(parts) + "\n"
            if header:
                yield sse_event("token", {"text": header})
            for chunk in _token_chunks(blk.text_vi):
                yield sse_event("token", {"text": chunk})
            yield sse_event("token", {"text": "\n\n"})

    for basis in dumped.get("bases", []):
        yield sse_event("citation", basis)

    for banner in dumped.get("banners", []):  # thứ tự đã do code lắp (R-31)
        yield sse_event("banner", banner)

    tier_payload = {"tier": ans.tier, "explain_vi": TIER_EXPLAIN_VI.get(ans.tier, "")}
    if ans.refusal_reason:
        tier_payload["refusal_reason"] = ans.refusal_reason
    yield sse_event("tier", tier_payload)

    yield sse_event("done", {"qa_id": dumped.get("qa_id"), "answer": dumped})
