"""Demo CLI — in Answer đầy đủ 4 mục + tier + banner trên snapshot seed.

    # offline hoàn toàn (MemStore + OfflineComposer — không cần Postgres/LLM):
    uv run python -m answer.demo "Điều kiện vay vốn hiện nay?" --as-of 2024-03-01

    # trên Postgres (tự seed fixture nếu trống):
    uv run python -m answer.demo "..." --db postgresql://... --seed

    # composer + judge LLM thật (cần key trong .env):
    uv run python -m answer.demo "..." --llm

Câu đại diện để thử:
  1. "Điều kiện vay vốn hiện nay là gì?"                        (hiện hành)
  2. "Có được vay để góp vốn vào công ty TNHH không?" --as-of 2024-03-01   (suspension)
  3. "Lãi suất cho vay tại ngày 01/03/2024?"                    (cohort thiếu → piecewise)
  4. "Lãi suất cho vay cho hợp đồng ký tháng 6/2021 chưa sửa đổi, tại ngày 01/03/2024?"
  5. "Khoản 8 Điều 8 Thông tư 39/2016/TT-NHNN đã từng có hiệu lực chưa?"  (pinpoint lịch sử)
  6. "Trần lãi suất 20%/năm có áp dụng cho khoản vay ngân hàng không?" --as-of 2018-06-01
  7. "Sắp tới điều kiện vay vốn có gì thay đổi?"                (pending)
  Thêm --audience customer để xem giọng phổ thông + disclaimer + escalate.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from answer.compiler import SessionCtx
from answer.compose import OfflineComposer
from answer.demo_seed import mem_store, seed_postgres
from answer.service import answer_question
from api.schemas import Answer


def _print_answer(ans: Answer) -> None:
    w = 78
    print("═" * w)
    print(f"  TIER {ans.tier}  |  audience={ans.audience}  |  as_of={ans.as_of}"
          f"  |  run={str(ans.run_id)[:8]}…" if ans.run_id else f"  TIER {ans.tier} (no run)")
    print("═" * w)
    for b in ans.banners:
        print(f"  ▐ [{b.kind}] {b.text_vi}")
    if ans.banners:
        print("─" * w)

    print("■ TRẢ LỜI")
    if ans.refusal_reason:
        print(f"  [TỪ CHỐI — Tier D] {ans.refusal_reason}")
    elif not ans.answer:
        print("  (sources-only — Tier C: chỉ trích dẫn ghim ở mục Căn cứ, không văn tổng hợp)")
    for blk in ans.answer:
        cond = []
        if blk.cohort:
            cond.append(f"chủ thể: {blk.cohort}")
        if blk.interval_from:
            end = blk.interval_to.strftime("%d/%m/%Y") if blk.interval_to else "nay"
            cond.append(f"{blk.interval_from.strftime('%d/%m/%Y')} → {end}")
        if cond:
            print(f"  ◆ [{' | '.join(cond)}]")
        for line in blk.text_vi.splitlines():
            print(f"    {line}")

    print("\n■ CĂN CỨ")
    if not ans.bases:
        print("  (không có)")
    for b in ans.bases:
        window = ""
        if b.valid_from:
            end = b.valid_to.strftime("%d/%m/%Y") if b.valid_to else "nay"
            window = f" | hiệu lực {b.valid_from.strftime('%d/%m/%Y')} → {end}"
        print(f"  {b.ref} {b.citation_vi} [{b.status}]{window}")
        if b.provenance_vi:
            print(f"      ↳ {b.provenance_vi}")
        if b.quote:
            print(f"      “{b.quote[:300]}{'…' if len(b.quote) > 300 else ''}”")

    print("\n■ XUNG ĐỘT")
    if not ans.conflicts:
        print("  (không chạm vùng xung đột nào)")
    for c in ans.conflicts:
        print(f"  ⚠ tier-{c.tier} [{c.label}] {c.reason}")
        if c.member_refs:
            print(f"      thành viên: {', '.join(c.member_refs)}")

    print("\n■ THAY ĐỔI SẮP HIỆU LỰC")
    if not ans.upcoming_changes:
        print("  (không có trong phạm vi coverage)")
    for u in ans.upcoming_changes:
        print(f"  → từ {u.effective_from.strftime('%d/%m/%Y')}: {u.description_vi}")

    print("\n■ FRESHNESS (coverage attestation)")
    if not ans.coverage:
        print("  (chưa quét kênh nào)")
    for cv in ans.coverage:
        checked = cv.last_checked.strftime("%d/%m/%Y %H:%M") if cv.last_checked else "?"
        print(f"  kênh {cv.channel}: đến {cv.last_seq or '?'} (kiểm {checked})")
    if ans.qa_id:
        print(f"\n  answer_log qa_id = {ans.qa_id}")
    print("═" * w)


def main() -> None:
    ap = argparse.ArgumentParser(description="LawState demo — hỏi trên snapshot seed")
    ap.add_argument("question")
    ap.add_argument("--as-of", dest="as_of", type=date.fromisoformat, default=None)
    ap.add_argument("--audience", choices=["employee", "customer"], default="employee")
    ap.add_argument("--db", default=os.getenv("DEMO_DATABASE_URL")
                    or os.getenv("TEST_DATABASE_URL"),
                    help="Postgres URL (bỏ trống → MemStore offline)")
    ap.add_argument("--seed", action="store_true", help="seed fixture vào Postgres nếu chưa có")
    ap.add_argument("--llm", action="store_true", help="dùng composer LLM thật qua gateway")
    args = ap.parse_args()

    if args.db:
        import psycopg
        from retrieval.query_builder import pg_store
        conn = psycopg.connect(args.db)
        if args.seed:
            if seed_postgres(conn):
                print("(đã seed snapshot fixture vào Postgres)", file=sys.stderr)
        store = pg_store(conn)
        if store is None:
            print("Postgres chưa có replay_run nào — chạy với --seed để nạp fixture.",
                  file=sys.stderr)
            sys.exit(2)
    else:
        store = mem_store()
        print("(MemStore offline — thêm --db postgresql://… để chạy trên Postgres)",
              file=sys.stderr)

    composer = None if args.llm else OfflineComposer()
    ctx = SessionCtx(audience=args.audience, as_of=args.as_of)
    ans = answer_question(args.question, ctx, store=store, composer=composer)
    _print_answer(ans)


if __name__ == "__main__":
    main()
