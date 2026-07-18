"""Scope split & applicability — DSL ĐÓNG 3 predicate (D-25), chiều s TRONG khóa (D-04).

Quy ước (khớp 02 §4, GF-01/02/03):
- `op.scope_predicate` = cohort ĐƯỢC MIỄN TRỪ khỏi op (điều khoản chuyển tiếp: cohort P
  "ký trước AND chưa sửa đổi" TIẾP TỤC theo text cũ). Fold tách: nhánh scope=P giữ nguyên,
  nhánh scope=complement(P) áp op — hai version song song cùng cửa sổ, khác scope_hash.
- Nhánh bù lưu trong node_version.scope_predicate dạng {"complement_of": P} — biểu diễn
  DẪN XUẤT của engine (jsonb), KHÔNG phải form mới của DSL op (DSL op vẫn đóng 3 predicate).
- `applicability_matches` ba trị: cohort thiếu dữ kiện để phân định ⇒ match MỌI nhánh
  (mặc định piecewise, không bao giờ chọn thầm — D-04).

Ngữ nghĩa trường cohort (cohort dùng chính DSL — api.schemas.Cohort):
- contract_signed_before c: "HĐ ký trước c" (cận trên loại trừ của ngày ký).
  Khớp predicate `contract_signed_before: D` ⟺ c <= D; c > D ⟹ KHÔNG thỏa.
- not_amended_on_or_after n: "chưa sửa đổi kể từ n trở đi".
  Thỏa predicate `not_amended_on_or_after: D` ⟺ n <= D; n > D ⟹ KHÔNG BIẾT (khoảng [D,n) mù).
- entity_class: so sánh bằng.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Mapping

FIELDS = ("contract_signed_before", "not_amended_on_or_after", "entity_class")
COMPLEMENT_KEY = "complement_of"


def _as_date(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return v
    return v


def _as_dict(scope: Any) -> dict[str, Any] | None:
    if scope is None:
        return None
    if hasattr(scope, "model_dump"):
        scope = scope.model_dump()
    if not isinstance(scope, Mapping):
        raise TypeError(f"scope_predicate không hợp lệ: {scope!r}")
    return dict(scope)


def canonical_scope(scope: Any) -> dict[str, str] | None:
    """Chuẩn hóa về dict ISO-string chỉ gồm field DSL có giá trị; rỗng → None."""
    d = _as_dict(scope)
    if d is None:
        return None
    if COMPLEMENT_KEY in d:
        inner = canonical_scope(d[COMPLEMENT_KEY])
        return {COMPLEMENT_KEY: inner} if inner else None
    out: dict[str, str] = {}
    for k in FIELDS:
        v = d.get(k)
        if v is not None:
            out[k] = str(v.isoformat() if isinstance(v, date) else v)
    unknown = set(d) - set(FIELDS) - {COMPLEMENT_KEY}
    if unknown:
        raise ValueError(f"DSL đóng D-25: predicate lạ {sorted(unknown)}")
    return out or None


def complement(scope: Any) -> dict[str, Any]:
    inner = canonical_scope(scope)
    if inner is None or COMPLEMENT_KEY in inner:
        raise ValueError("complement chỉ áp cho predicate DSL thuận")
    return {COMPLEMENT_KEY: inner}


def is_complement_of(scope: Any, predicate: Any) -> bool:
    c = canonical_scope(scope)
    return bool(c) and c.get(COMPLEMENT_KEY) == canonical_scope(predicate)


def scopes_equal(a: Any, b: Any) -> bool:
    return canonical_scope(a) == canonical_scope(b)


def scope_hash(scope: Any) -> str:
    """'' cho universal (khớp DEFAULT '' của DDL); ngược lại sha256-16 của JSON canonical."""
    c = canonical_scope(scope)
    if c is None:
        return ""
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _eval_field(name: str, pv: Any, cv: Any) -> bool | None:
    if cv is None:
        return None
    pv, cv = _as_date(pv), _as_date(cv)
    if name == "contract_signed_before":
        return cv <= pv
    if name == "not_amended_on_or_after":
        return True if cv <= pv else None      # n > D: không đảm bảo được [D, n) → không biết
    if name == "entity_class":
        return cv == pv
    return None


def eval_predicate(predicate: Any, cohort: Any) -> bool | None:
    """AND ba trị trên các field CÓ MẶT trong predicate: False trội, rồi None, rồi True."""
    p = canonical_scope(predicate) or {}
    c = {k: v for k, v in (_as_dict(cohort) or {}).items() if v is not None}
    results = [_eval_field(k, pv, c.get(k)) for k, pv in p.items()]
    if any(r is False for r in results):
        return False
    if any(r is None for r in results):
        return None
    return True


def applicability_matches(version_scope: Any, cohort: Any) -> bool:
    """Version có áp cho cohort không — permissive khi không phân định được (R-28)."""
    s = canonical_scope(version_scope)
    if s is None:
        return True
    if COMPLEMENT_KEY in s:
        return eval_predicate(s[COMPLEMENT_KEY], cohort) is not True
    return eval_predicate(s, cohort) is not False
