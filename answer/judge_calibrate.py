"""Đo κ của judge trên bộ hiệu chuẩn (R-33) — chạy THỦ CÔNG, gọi LLM trả tiền.

    uv run python -m answer.judge_calibrate            # gọi judge thật, ghi kappa.json
    uv run python -m answer.judge_calibrate --dry-run  # chỉ in thống kê bộ cặp

κ ≥ 0.8 mới mở đường Tier A; mặc định repo ship kappa.json = null (chưa-đạt →
mọi answer cap Tier B + banner). KHÔNG chạy trong CI.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from answer.judge_soft import (JUDGE_SCHEMA, _SYSTEM_JUDGE, cohen_kappa,
                               load_calibration, write_kappa)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="không gọi LLM, chỉ thống kê bộ cặp")
    args = ap.parse_args()

    pairs = load_calibration()
    print(f"Bộ hiệu chuẩn: {len(pairs)} cặp — phân bố nhãn: {Counter(p['label'] for p in pairs)}")
    if args.dry_run:
        return

    from answer.llm_gateway import get_gateway
    gw = get_gateway()
    gold, pred = [], []
    for i, p in enumerate(pairs, 1):
        user = json.dumps({"claim": p["claim"], "evidence": p["evidence"]}, ensure_ascii=False)
        try:
            res = gw.complete_json("judge", _SYSTEM_JUDGE, user, JUDGE_SCHEMA)
            v = res.get("verdict", "fails")
        except Exception as exc:  # đo trung thực: lỗi = fails
            print(f"  [{i}] lỗi gateway: {exc}")
            v = "fails"
        gold.append(p["label"])
        pred.append(v)
        if v != p["label"]:
            print(f"  [{i}] {p['id']}: gold={p['label']} judge={v}")

    kappa = cohen_kappa(gold, pred)
    agree = sum(1 for a, b in zip(gold, pred) if a == b)
    print(f"\nAgreement {agree}/{len(gold)} — Cohen κ = {kappa:.3f} (ngưỡng 0.8)")
    write_kappa(round(kappa, 4), len(gold),
                note="đo bằng answer.judge_calibrate trên judge_calibration.json")
    print("Đã ghi answer/calibration/kappa.json")


if __name__ == "__main__":
    main()
