"""Judge mềm (R-33, D-30): κ-gate, context cô lập, bộ hiệu chuẩn."""
import json

import pytest

from answer import judge_soft
from api.schemas import ComposerClaim


# ------------------------------------------------------------------ Cohen κ

def test_kappa_perfect_agreement():
    assert judge_soft.cohen_kappa(["entails", "fails"], ["entails", "fails"]) == 1.0


def test_kappa_known_value():
    # po = 8/10, pe = 0.5 (nhãn cân bằng hai phía) → κ = (0.8-0.5)/0.5 = 0.6
    a = ["e"] * 5 + ["f"] * 5
    b = ["e", "e", "e", "e", "f", "f", "f", "f", "f", "e"]
    assert abs(judge_soft.cohen_kappa(a, b) - 0.6) < 1e-9


def test_kappa_chance_level_zero():
    a = ["e", "e", "f", "f"]
    b = ["e", "f", "e", "f"]
    assert abs(judge_soft.cohen_kappa(a, b)) < 1e-9


def test_kappa_requires_same_length():
    with pytest.raises(ValueError):
        judge_soft.cohen_kappa(["e"], ["e", "f"])


# ------------------------------------------------------------------ κ-gate state

def test_default_shipped_state_is_uncalibrated(monkeypatch):
    monkeypatch.delenv("JUDGE_ENABLED", raising=False)
    # repo ship kappa.json = null → chưa-đạt → cap Tier B (R-33)
    assert judge_soft.load_kappa() is None
    assert judge_soft.judge_state() == "uncalibrated"


def test_judge_off_via_env(monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "0")
    assert judge_soft.judge_state() == "off"


def test_calibrated_when_kappa_above_threshold(monkeypatch, tmp_path):
    f = tmp_path / "kappa.json"
    f.write_text(json.dumps({"kappa": 0.85, "n": 54}), encoding="utf-8")
    monkeypatch.setattr(judge_soft, "KAPPA_FILE", f)
    monkeypatch.delenv("JUDGE_ENABLED", raising=False)
    assert judge_soft.judge_state() == "calibrated"
    f.write_text(json.dumps({"kappa": 0.79, "n": 54}), encoding="utf-8")
    assert judge_soft.judge_state() == "uncalibrated"


# ------------------------------------------------------------------ judge_claims

class FakeGateway:
    def __init__(self, verdict="entails", raise_exc=False):
        self.verdict, self.raise_exc, self.calls = verdict, raise_exc, []

    def complete_json(self, role, system, user, schema):
        assert role == "judge"
        self.calls.append(json.loads(user))
        if self.raise_exc:
            raise RuntimeError("gateway down")
        return {"verdict": self.verdict}


def test_judge_claims_isolated_context():
    gw = FakeGateway()
    claims = [ComposerClaim(id="c1", text="trần 20%/năm [1]", refs=["[1]"])]
    ctx = {"[1]": "Điều 468... 20%/năm...", "[2]": "KHÔNG ĐƯỢC THẤY"}
    out = judge_soft.judge_claims(claims, ctx, gateway=gw)
    assert out == [{"claim_id": "c1", "verdict": "entails"}]
    # context CÔ LẬP: chỉ evidence của refs claim đó, không thấy [2], không thấy câu hỏi
    assert gw.calls[0]["evidence"] == ["Điều 468... 20%/năm..."]
    assert "KHÔNG ĐƯỢC THẤY" not in json.dumps(gw.calls[0], ensure_ascii=False)


def test_judge_gateway_error_conservative_fails():
    gw = FakeGateway(raise_exc=True)
    claims = [ComposerClaim(id="c1", text="x [1]", refs=["[1]"])]
    out = judge_soft.judge_claims(claims, {"[1]": "y"}, gateway=gw)
    assert out[0]["verdict"] == "fails"      # lỗi không được rửa thành pass


# ------------------------------------------------------------------ bộ hiệu chuẩn

def test_calibration_set_shipped_50plus_vietnamese_labeled():
    pairs = judge_soft.load_calibration()
    assert len(pairs) >= 50
    ids = [p["id"] for p in pairs]
    assert len(set(ids)) == len(ids)
    labels = {p["label"] for p in pairs}
    assert labels == {"entails", "partial", "fails"}
    for p in pairs:
        assert p["claim"].strip() and p["evidence"]
    # cân bằng nhãn tương đối (mỗi nhãn ≥ 25%)
    from collections import Counter
    c = Counter(p["label"] for p in pairs)
    assert min(c.values()) >= len(pairs) // 4
