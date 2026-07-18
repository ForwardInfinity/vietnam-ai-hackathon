"""Auth hackathon theo S6: header role (employee/customer/curator); /admin/* đòi curator.

- `X-Role`: danh tính THÔ (ai gọi). Thiếu header → mặc định least-privilege = customer.
- `X-Actor`: người thao tác (curator id/tên) — BẮT BUỘC cho mọi call mutating ở /admin
  (INV-6: không đường nào tạo op ratified thiếu người ký).
- Persona hiệu dụng cho /ask: role customer KHÔNG BAO GIỜ được nâng lên employee,
  employee/curator được phép hạ xuống persona customer (preview).

Pilot: thay bằng OIDC — chỉ đổi 2 dependency này, endpoint giữ nguyên.
"""
from __future__ import annotations

from typing import Literal

from fastapi import Depends, Header, HTTPException

Role = Literal["employee", "customer", "curator"]
VALID_ROLES = ("employee", "customer", "curator")


def get_role(x_role: str | None = Header(default=None)) -> str:
    if x_role is None or x_role == "":
        return "customer"  # least privilege khi không khai danh tính
    role = x_role.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"X-Role không hợp lệ: {x_role!r} (employee|customer|curator)")
    return role


def require_curator(role: str = Depends(get_role)) -> str:
    if role != "curator":
        raise HTTPException(status_code=403, detail="/admin/* yêu cầu role curator (header X-Role: curator)")
    return role


def get_actor(x_actor: str | None = Header(default=None)) -> str | None:
    actor = (x_actor or "").strip()
    return actor or None


def require_actor(actor: str | None = Depends(get_actor)) -> str:
    """Call mutating admin PHẢI có người ký (INV-6). 422 khi thiếu."""
    if not actor:
        raise HTTPException(
            status_code=422,
            detail="Thiếu header X-Actor (người thao tác) — mọi quyết định ratify phải có người ký (INV-6).",
        )
    return actor


def effective_persona(role: str, requested: str) -> str:
    """Persona hiệu dụng cho answering: customer role bị ghim customer bất kể body."""
    if role == "customer":
        return "customer"
    return "customer" if requested == "customer" else "employee"
