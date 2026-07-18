"""Freshness = coverage attestation theo kênh + run_id pin + TTL config tĩnh (R-35, D-32).

KHÔNG hứa freshness với thế giới — chỉ chứng thực "đã quét kênh nào, đến đâu":
"Công báo đến số N ngày D; registry nội bộ đến D'". TTL v1 là config tĩnh theo
mảng (hook đo động học để sau).
"""
from __future__ import annotations

from datetime import date, timedelta

from api.schemas import CoverageAttestation
from retrieval.query_builder import CoverageRow

# TTL tĩnh theo kênh (ngày) — quá TTL mà hỏi về hiện tại/tương lai ⇒ ngoài coverage
DEFAULT_TTL_DAYS: dict[str, int] = {
    "congbao": 7,
    "sbv": 7,
    "internal_registry": 30,
}
FALLBACK_TTL_DAYS = 14


def ttl_for(channel: str) -> int:
    return DEFAULT_TTL_DAYS.get(channel, FALLBACK_TTL_DAYS)


def attestations(rows: list[CoverageRow]) -> list[CoverageAttestation]:
    return [CoverageAttestation(channel=r.channel, last_seq=r.last_seq,
                                last_checked=r.last_checked) for r in rows]


def attestation_vi(rows: list[CoverageRow]) -> str:
    """'Công báo đến số 59/2026 (kiểm 18/07/2026); internal_registry đến …'"""
    parts = []
    for r in rows:
        seq = f"đến {r.last_seq}" if r.last_seq else "chưa có mốc"
        checked = f" (kiểm {r.last_checked.date().strftime('%d/%m/%Y')})" if r.last_checked else ""
        parts.append(f"{r.channel} {seq}{checked}")
    return "; ".join(parts) if parts else "chưa quét kênh nào"


def in_coverage(rows: list[CoverageRow], as_of: date, today: date | None = None) -> bool:
    """as_of nằm trong vùng hệ dám chứng thực:
    - không có kênh nào từng quét → NGOÀI coverage (không có gì để chứng thực);
    - as_of ≤ mốc-kiểm-mới-nhất + TTL kênh → trong;
    - hỏi về quá khứ xa hơn mốc quét: vẫn trong (trạng thái lịch sử đã compile)."""
    if not rows:
        return False
    horizon = None
    for r in rows:
        if r.last_checked is None:
            continue
        h = r.last_checked.date() + timedelta(days=ttl_for(r.channel))
        horizon = h if horizon is None else max(horizon, h)
    if horizon is None:
        return False
    return as_of <= horizon
