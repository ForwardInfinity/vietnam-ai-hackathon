"""Judge mềm — LLM KHÁC HỌ composer, entailment từng claim (R-33, D-30).

Context CÔ LẬP: judge chỉ thấy {claim, cited_texts} — không thấy câu hỏi, không
thấy phần trả lời còn lại (tránh judge bị dẫn dắt bởi văn cảnh).

κ-gate: judge chỉ được TÍNH ĐIỂM (mở đường Tier A) khi đã hiệu chuẩn κ≥0.8 trên
bộ cặp Việt gán nhãn (answer/calibration/). Chưa đạt hoặc judge off → mọi answer
cap Tier B + banner — mặc định ship là CHƯA-ĐẠT (kappa.json = null).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from api.schemas import ComposerClaim

Verdict = Literal["entails", "partial", "fails"]
JudgeState = Literal["calibrated", "uncalibrated", "off"]

KAPPA_THRESHOLD = 0.8
CALIB_DIR = Path(__file__).parent / "calibration"
KAPPA_FILE = CALIB_DIR / "kappa.json"
CALIBRATION_FILE = CALIB_DIR / "judge_calibration.json"

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["entails", "partial", "fails"]}},
    "required": ["verdict"],
    "additionalProperties": False,
}

_SYSTEM_JUDGE = """Anh là giám khảo entailment cho câu trả lời pháp quy tiếng Việt.
Cho một CLAIM và các EVIDENCE (trích đoạn văn bản). Chỉ dựa vào EVIDENCE — không dùng kiến thức ngoài.
Phán quyết:
- "entails": mọi nội dung khẳng định trong claim được evidence chống lưng đầy đủ.
- "partial": claim đúng một phần nhưng thêm chi tiết/điều kiện mà evidence không nêu.
- "fails": claim mâu thuẫn evidence hoặc khẳng định điều evidence không hề nói.
Trả về JSON {"verdict": "..."}."""


def load_kappa() -> float | None:
    try:
        data = json.loads(KAPPA_FILE.read_text(encoding="utf-8"))
        return data.get("kappa")
    except Exception:
        return None


def judge_state() -> JudgeState:
    if os.getenv("JUDGE_ENABLED", "1").lower() in ("0", "false", "off"):
        return "off"
    k = load_kappa()
    if k is not None and k >= KAPPA_THRESHOLD:
        return "calibrated"
    return "uncalibrated"


def judge_claims(claims: list[ComposerClaim], context_texts: dict[str, str],
                 gateway=None) -> list[dict[str, str]]:
    """Mỗi claim một call, context cô lập {claim, cited texts}. Lỗi gateway →
    verdict 'fails' bảo thủ (caller cap B, không nuốt lỗi thành A)."""
    if gateway is None:
        from answer.llm_gateway import get_gateway
        gateway = get_gateway()
    out: list[dict[str, str]] = []
    for c in claims:
        evidence = [context_texts[r] for r in c.refs if r in context_texts]
        user = json.dumps({"claim": c.text, "evidence": evidence}, ensure_ascii=False)
        try:
            res = gateway.complete_json("judge", _SYSTEM_JUDGE, user, JUDGE_SCHEMA)
            verdict = res.get("verdict", "fails")
        except Exception:
            verdict = "fails"
        out.append({"claim_id": c.id, "verdict": verdict})
    return out


# ---------------------------------------------------------------------------
# Cohen κ (đa lớp) + bộ hiệu chuẩn
# ---------------------------------------------------------------------------

def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("hai dãy nhãn phải cùng độ dài > 0")
    n = len(labels_a)
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    ca, cb = Counter(labels_a), Counter(labels_b)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def load_calibration() -> list[dict[str, Any]]:
    data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    return data["pairs"]


def write_kappa(kappa: float | None, n: int, note: str = "") -> None:
    KAPPA_FILE.write_text(json.dumps(
        {"kappa": kappa, "n": n, "threshold": KAPPA_THRESHOLD, "note": note},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
