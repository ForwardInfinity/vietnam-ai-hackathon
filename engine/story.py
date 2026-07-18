"""4 câu chuyện EXPECTED vs ACTUAL cho QA đối chiếu bằng domain (không đọc code).

Chạy: `python -m engine.story` (hoặc `uv run python -m engine.story`).
Corpus: op fixture tự dựng theo anchor thật tại tests/fixtures/ops/ (04 §1).
Exit code 0 ⟺ cả 4 câu chuyện khớp.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from engine.fixtures import FIXTURE_DIR, load_dir
from engine.fold import active_intervals, ever_active, fold_corpus, materialize_at
from engine.scope import applicability_matches


@dataclass
class Story:
    title: str
    expected: list[str]
    actual: list[str]
    ok: bool


def _fmt_window(v) -> str:
    to = v.valid_to.strftime("%d/%m/%Y") if v.valid_to else "nay (mở)"
    return f"[{v.valid_from.strftime('%d/%m/%Y')} → {to})"


def story_1(c, cf) -> Story:
    """Timeline khoản 8 Điều 8 TT39: TT06 bổ sung (hiệu lực 01/09/2023), TT10 treo ĐÚNG
    ngày đó theo-sự-kiện → khoảng operative ∅ — 'đã từng có hiệu lực?' → CHƯA TỪNG."""
    k8 = c.node("39/2016/TT-NHNN", "dieu:8/khoan:8")
    versions = cf.versions[k8.id]
    expected = [
        "Chỉ tồn tại version SUSPENDED từ 01/09/2023, mở vô hạn (sự kiện chưa xảy ra)",
        "KHÔNG tồn tại version active; khoảng operative = ∅",
        "Kết luận: CHƯA TỪNG CÓ HIỆU LỰC",
    ]
    actual = [f"version {v.version}: {v.status} {_fmt_window(v)} — “{(v.body or '')[:40]}…”"
              for v in versions]
    verdict = "CHƯA TỪNG CÓ HIỆU LỰC" if not ever_active(versions) else "ĐÃ TỪNG CÓ HIỆU LỰC"
    actual.append(f"khoảng operative: {active_intervals(versions) or '∅'} → {verdict}")
    ok = (not ever_active(versions)
          and len(versions) == 1
          and versions[0].status == "suspended"
          and versions[0].valid_from == date(2023, 9, 1)
          and versions[0].valid_to is None)
    return Story("k8 Đ8 TT39 — treo trước khi kịp có hiệu lực (TT06 × TT10)",
                 expected, actual, ok)


def story_2(c, cf) -> Story:
    """as-of 03/2024: khoản 2 Đ20 TT22 phải trả text theo TT26/2022 NGUYÊN VẸN, dù
    TT08/2026 (đã phê chuẩn) bãi bỏ điều khoản sửa đổi đó từ 01/01/2026 (INV-5)."""
    ldr = c.node("22/2019/TT-NHNN", "dieu:20/khoan:2")
    as_of = date(2024, 3, 1)
    at = materialize_at(cf.versions[ldr.id], as_of, status="active")
    expected = [
        "Tại 01/03/2024 text hiệu lực là bản TT26/2022 (tiền gửi KBNN theo lộ trình)",
        "Cửa sổ của bản TT26 bị đóng ĐÚNG tại 01/01/2026 — quá khứ không bị viết lại",
        "KHÔNG được trả lời 'đã bị bãi bỏ' cho câu hỏi as-of 2024",
    ]
    actual = []
    ok = len(at) == 1
    if at:
        v = at[0]
        actual.append(f"text tại 03/2024: “…{(v.body or '')[-60:]}”")
        actual.append(f"cửa sổ version: {_fmt_window(v)} status={v.status}")
        ok = ok and "(bản TT26/2022)" in (v.body or "") and v.status == "active" \
            and v.valid_to == date(2026, 1, 1)
    return Story("Bãi bỏ op ≠ viết lại lịch sử — TT26/2022 dưới repeal-op TT08/2026",
                 expected, actual, ok)


def story_3(c, cf) -> Story:
    """TT32/2026 grandfather 2 tầng trên Đ7 TT39: thiếu dữ kiện cohort → trả CẢ HAI nhánh
    (piecewise mặc định, không bao giờ chọn thầm — D-04)."""
    d7 = c.node("39/2016/TT-NHNN", "dieu:7")
    as_of = date(2026, 8, 1)
    at = materialize_at(cf.versions[d7.id], as_of)          # cohort None = thiếu
    both = [v for v in at if applicability_matches(v.scope_predicate, {})]
    gf_cohort = {"contract_signed_before": "2026-06-01",
                 "not_amended_on_or_after": "2026-07-01"}
    gf = [v for v in at if applicability_matches(v.scope_predicate, gf_cohort)]
    new = [v for v in at if applicability_matches(v.scope_predicate,
                                                  {"contract_signed_before": "2026-09-01"})]
    expected = [
        "Cohort thiếu → khớp CẢ HAI nhánh (2 version cùng cửa sổ, khác scope_hash)",
        "Cohort HĐ ký trước 07/2026 chưa sửa đổi → 1 nhánh: text CŨ (bản TT12/2024)",
        "Cohort HĐ ký sau 07/2026 → 1 nhánh: text MỚI (bản TT32/2026)",
    ]
    actual = [
        f"cohort thiếu: {len(both)} nhánh, scope_hash = "
        f"{[v.scope_hash[:6] or 'univ' for v in both]}",
        f"cohort grandfather: {len(gf)} nhánh — “…{(gf[0].body or '')[-20:]}”" if gf else "∅",
        f"cohort ký sau: {len(new)} nhánh — “…{(new[0].body or '')[-20:]}”" if new else "∅",
    ]
    ok = (len(both) == 2 and len({v.scope_hash for v in both}) == 2
          and len(gf) == 1 and "(bản TT12/2024)" in (gf[0].body or "")
          and len(new) == 1 and "(bản TT32/2026)" in (new[0].body or ""))
    return Story("Grandfather 2 tầng TT32/2026 — cohort thiếu ⇒ CẢ HAI nhánh", expected,
                 actual, ok)


def story_4(c, cf) -> Story:
    """DC-01/2026 đính chính '07' → '10 ngày làm việc' cho Đ7a: hồi tố về ĐẦU cửa sổ —
    as-of 01/02/2026 (TRƯỚC ngày đính chính 05/02/2026) vẫn phải thấy số ĐÃ đính chính."""
    d7a = c.node("39/2016/TT-NHNN", "dieu:7a")
    as_of = date(2026, 2, 1)
    at = materialize_at(cf.versions[d7a.id], as_of, status="active")
    dc_op = c.op("op:dc01-fix-d7a")
    expected = [
        "Text tại 01/02/2026 (trước ngày đính chính): “10 ngày làm việc” — KHÔNG phải “07”",
        "Cửa sổ version bắt đầu 15/01/2026 (đầu cửa sổ bản gốc, không tách version mới)",
        "Provenance chứa op dinh_chinh",
    ]
    actual = []
    ok = len(at) == 1
    if at:
        v = at[0]
        actual.append(f"text: “{v.body}”")
        actual.append(f"cửa sổ: {_fmt_window(v)}")
        actual.append(f"provenance có op dinh_chinh: {dc_op.id in v.provenance}")
        ok = ok and "10 ngày làm việc" in (v.body or "") and "07 ngày" not in (v.body or "") \
            and v.valid_from == date(2026, 1, 15) and dc_op.id in v.provenance
    return Story("Đính chính hồi tố DC-01/2026 — áp cho cả TRƯỚC ngày đính chính",
                 expected, actual, ok)


def main(argv: list[str] | None = None) -> int:
    c = load_dir(FIXTURE_DIR)
    cf = fold_corpus(c.nodes, c.ops, c.artifacts)
    stories = [f(c, cf) for f in (story_1, story_2, story_3, story_4)]
    for i, s in enumerate(stories, 1):
        print(f"\n=== Câu chuyện {i}: {s.title}")
        print("  EXPECTED:")
        for line in s.expected:
            print(f"    - {line}")
        print("  ACTUAL:")
        for line in s.actual:
            print(f"    - {line}")
        print(f"  => {'KHỚP ✓' if s.ok else 'LỆCH ✗'}")
    n_ok = sum(s.ok for s in stories)
    print(f"\nTổng: {n_ok}/{len(stories)} câu chuyện khớp.")
    return 0 if n_ok == len(stories) else 1


if __name__ == "__main__":
    raise SystemExit(main())
