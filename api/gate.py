"""MỘT CỬA audience cho tầng API (INV-12, D-44).

Mọi endpoint đọc chạm dữ liệu dẫn xuất từ artifact (timeline, graph, norms,
citation panel, artifact text) PHẢI lấy mệnh đề lọc từ module này — KHÔNG endpoint
nào tự viết filter audience.

TODO(F5): `retrieval/query_builder.py` là MỘT CỬA chính thức khi F5 merge.
Module này import nó nếu có; chưa có thì dùng fallback cùng ngữ nghĩa bên dưới.
Khi F5 merge: nếu chữ ký của họ khác, sửa DUY NHẤT file này (một chỗ đổi).
"""
from __future__ import annotations

from typing import Sequence

# Entitlements theo S5.6/R-36: customer = {public}; employee = {public, internal};
# curator (vận hành substrate) = thêm restricted.
_ENTITLEMENTS: dict[str, tuple[str, ...]] = {
    "customer": ("public",),
    "employee": ("public", "internal"),
    "curator": ("public", "internal", "restricted"),
}

try:  # pragma: no cover - đường F5 (chưa merge tại thời điểm F6)
    from retrieval.query_builder import entitlements_for as _f5_entitlements  # type: ignore

    _SOURCE = "retrieval.query_builder"

    def entitlements_for(role: str) -> tuple[str, ...]:
        return tuple(_f5_entitlements(role))

except ImportError:  # fallback F6 — cùng bảng, một chỗ sở hữu
    _SOURCE = "api.gate (fallback — chờ F5 retrieval/query_builder)"

    def entitlements_for(role: str) -> tuple[str, ...]:
        return _ENTITLEMENTS.get(role, _ENTITLEMENTS["customer"])


def gate_source() -> str:
    """Cho build-status/debug: đang dùng cửa nào."""
    return _SOURCE


def audience_clause(role: str, alias: str = "a") -> tuple[str, list]:
    """Mệnh đề SQL lọc audience trên bảng artifact (alias mặc định `a`).

    Dùng: sql = f"... WHERE {clause}"; params += clause_params
    """
    ents = list(entitlements_for(role))
    return (f"{alias}.audience = ANY(%s::audience_t[])", [ents])


def audience_visible(role: str, audience: str | None) -> bool:
    """Check phía Python cho dữ liệu đã fetch (vd redact provenance ops)."""
    if audience is None:
        return False
    return audience in entitlements_for(role)


def assert_no_leak(role: str, audiences: Sequence[str | None]) -> None:
    """Defense-in-depth: raise nếu response sắp chứa artifact ngoài entitlements."""
    for aud in audiences:
        if not audience_visible(role, aud):
            raise RuntimeError(f"INV-12 guard: audience {aud!r} lọt qua filter cho role {role!r}")
