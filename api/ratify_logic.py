"""Logic ratify THUẦN (không DB) — test được trong smoke.

- R-15: router hai hàng đợi (per-op vs batch-eligible) — proxy tính được từ dữ liệu op.
- R-16: machine-verify từng op khớp invariant_template (3 pattern S4.4) + spot-check ≥10%.
- R-17: khóa sort queue: risk (definitional trước) rồi confidence tăng dần.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# R-17: sort queue
# ---------------------------------------------------------------------------

def queue_sort_key(op: dict) -> tuple:
    """definitional trước prescriptive/None; trong nhóm: confidence tăng dần (None = 0 = nghi nhất)."""
    risk_rank = 0 if op.get("risk_class") == "definitional" else 1
    conf = op.get("confidence")
    return (risk_rank, conf if conf is not None else -1.0)


# ---------------------------------------------------------------------------
# R-15: router hai hàng đợi (proxy — F3 sẽ bổ sung metadata rule↔LLM khớp / cờ đỏ R-13)
# ---------------------------------------------------------------------------

def route_queue(op: dict, has_dinh_nghia_inbound: bool = False) -> str:
    """'per_op' | 'batch_eligible'.

    per-op nếu: risk definitional ∨ target có inbound edge dinh_nghia ∨ kind norm_decl
    ∨ valid_from cần phân loại ngữ nghĩa (NULL/valid_to_event) ∨ target không resolve duy nhất.
    Ngược lại batch-eligible khi đủ điều kiện cơ học: prescriptive + target_node resolve
    + ngày đọc thẳng. TODO(F3): thêm điều kiện rule↔LLM khớp + cờ đỏ R-13 khi metadata có.
    """
    if op.get("risk_class") == "definitional" or has_dinh_nghia_inbound:
        return "per_op"
    if op.get("kind") in ("norm_decl", "blanket_derogation"):
        return "per_op"
    if op.get("kind") == "close_window":
        return "per_op"  # đóng cửa sổ treo-theo-sự-kiện = phán đoán ngữ nghĩa (D-11)
    if op.get("valid_from") is None or op.get("valid_to_event"):
        return "per_op"
    if not (op.get("target_node") or op.get("target_op") or op.get("target_norm")):
        return "per_op"
    if op.get("risk_class") == "prescriptive":
        return "batch_eligible"
    return "per_op"  # risk chưa phân loại → người nhìn


# ---------------------------------------------------------------------------
# R-16: machine-verify op ↔ invariant_template
# ---------------------------------------------------------------------------

VALID_PATTERNS = ("phrase_replace", "uniform_field_change", "mass_repeal")


@dataclass
class VerifyResult:
    op_id: str
    ok: bool
    reason: str
    weak: bool = False  # True = pass nhưng thiếu snapshot hiện tại để đối chiếu mạnh (chờ F4)

    def as_dict(self) -> dict:
        return {"op_id": self.op_id, "ok": self.ok, "reason": self.reason, "weak": self.weak}


def validate_template(template: dict) -> str | None:
    """Trả message lỗi nếu template sai dạng, None nếu hợp lệ (S4.4)."""
    if not isinstance(template, dict):
        return "invariant_template phải là object JSON"
    pattern = template.get("pattern")
    if pattern not in VALID_PATTERNS:
        return f"pattern {pattern!r} không thuộc {VALID_PATTERNS}"
    if pattern == "phrase_replace":
        if not template.get("from") or not template.get("to"):
            return "phrase_replace cần 'from' và 'to' khác rỗng"
    elif pattern == "uniform_field_change":
        if not template.get("field_regex") or template.get("from") is None or template.get("to") is None:
            return "uniform_field_change cần 'field_regex', 'from', 'to'"
        try:
            re.compile(template["field_regex"])
        except re.error as exc:
            return f"field_regex không compile được: {exc}"
    elif pattern == "mass_repeal":
        keys = template.get("target_doc_keys")
        if not isinstance(keys, list) or not keys:
            return "mass_repeal cần 'target_doc_keys' là list khác rỗng"
    return None


def verify_op_against_template(
    template: dict, op: dict, current_text: str | None, target_doc_key: str | None
) -> VerifyResult:
    """Máy verify MỘT op khớp template (R-16). op: dict các cột bảng op."""
    op_id = str(op.get("id"))
    pattern = template.get("pattern")

    if pattern == "phrase_replace":
        frm, to = template["from"], template["to"]
        if op.get("kind") != "amend":
            return VerifyResult(op_id, False, f"phrase_replace đòi kind=amend, gặp {op.get('kind')}")
        new_text = op.get("new_text") or ""
        if not new_text:
            return VerifyResult(op_id, False, "amend thiếu new_text")
        if frm in new_text:
            return VerifyResult(op_id, False, f"new_text vẫn còn cụm cũ {frm!r}")
        if to not in new_text:
            return VerifyResult(op_id, False, f"new_text không chứa cụm mới {to!r}")
        if current_text:
            if current_text.replace(frm, to) != new_text:
                return VerifyResult(
                    op_id, False,
                    "new_text ≠ current_text.replace(from,to) — op đổi NHIỀU HƠN cụm từ khai báo",
                )
            return VerifyResult(op_id, True, "khớp exact: current.replace(from,to) == new_text")
        return VerifyResult(op_id, True, "pass cấu trúc (chưa có snapshot hiện tại để so exact)", weak=True)

    if pattern == "uniform_field_change":
        frm, to = str(template["from"]), str(template["to"])
        rx = re.compile(template["field_regex"])
        if op.get("kind") != "amend":
            return VerifyResult(op_id, False, f"uniform_field_change đòi kind=amend, gặp {op.get('kind')}")
        new_text = op.get("new_text") or ""
        new_matches = rx.findall(new_text)
        if not new_matches:
            return VerifyResult(op_id, False, f"new_text không match field_regex {template['field_regex']!r}")
        if not any(to in m for m in new_matches):
            return VerifyResult(op_id, False, f"field trong new_text không mang giá trị mới {to!r}")
        if any(frm in m for m in new_matches):
            return VerifyResult(op_id, False, f"field trong new_text vẫn mang giá trị cũ {frm!r}")
        if current_text:
            cur_matches = rx.findall(current_text)
            if cur_matches and not any(frm in m for m in cur_matches):
                return VerifyResult(op_id, False, f"current_text không có field giá trị cũ {frm!r} — op ngoài lớp")
            return VerifyResult(op_id, True, "field đổi đúng from→to, đối chiếu current_text")
        return VerifyResult(op_id, True, "field mang giá trị mới (chưa có snapshot để so field cũ)", weak=True)

    if pattern == "mass_repeal":
        keys = template["target_doc_keys"]
        if op.get("kind") != "repeal":
            return VerifyResult(op_id, False, f"mass_repeal đòi kind=repeal, gặp {op.get('kind')}")
        if op.get("new_text"):
            return VerifyResult(op_id, False, "repeal không được mang new_text")
        if target_doc_key is None:
            return VerifyResult(op_id, False, "không xác định được doc_key của target")
        if target_doc_key not in keys:
            return VerifyResult(op_id, False, f"target thuộc {target_doc_key!r} ∉ target_doc_keys khai báo")
        return VerifyResult(op_id, True, f"repeal đúng lớp văn bản {target_doc_key!r}")

    return VerifyResult(op_id, False, f"pattern {pattern!r} không hỗ trợ")


# ---------------------------------------------------------------------------
# Spot-check ≥ 10% (D-19)
# ---------------------------------------------------------------------------

def spot_check_sample(op_ids: list, rate: float = 0.1, rng: random.Random | None = None) -> list:
    """Chọn ceil(n*rate) op (tối thiểu 1 khi có op) để curator soi tay."""
    if not op_ids:
        return []
    rate = max(rate, 0.1)  # sàn theo D-19: không cho khai rate < 10%
    k = max(1, math.ceil(len(op_ids) * rate))
    rng = rng or random.Random()
    return rng.sample(list(op_ids), k)


# ---------------------------------------------------------------------------
# Diff render (FR-9: source_quote cạnh diff target hiện tại vs sau-áp)
# ---------------------------------------------------------------------------

def unified_diff(before: str | None, after: str | None, n: int = 3) -> str:
    import difflib

    a = (before or "").splitlines()
    b = (after or "").splitlines()
    return "\n".join(
        difflib.unified_diff(a, b, fromfile="hiện tại", tofile="sau-áp", lineterm="", n=n)
    )
