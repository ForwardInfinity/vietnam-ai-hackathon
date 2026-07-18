# answer/ — Retrieval + Answering (F5)

Đường "câu hỏi → `Answer{content piecewise, provenance, freshness, tier}`" trên
snapshot mà engine (F4) tính ra. Spec: `docs/03-SYSTEM-SPEC.md` S5 (R-27..R-37),
quyết định nền `docs/01-DECISIONS.md` E (D-26..D-32) + D-04/D-05/D-44.

## Interface cho F6 (API/UI)

```python
from answer.service import answer_question, SessionCtx
from retrieval.query_builder import pg_store
from api.schemas import Answer

conn = psycopg.connect(DATABASE_URL)
store = pg_store(conn, as_known=None)   # pin run mới nhất theo trục K; None = chưa có snapshot
ctx = SessionCtx(
    audience="employee" | "customer",   # quyền — quyết định entitlements Ở TẦNG SQL (INV-12)
    as_of=date | None,                  # UI as-of control; mốc trong câu hỏi thắng ctx
    as_known=datetime | None,           # trục K
    cohort=Cohort(...) | None,          # form cohort UI (DSL đóng D-25); merge với text
    session_id=str | None,
)
ans: Answer = answer_question(question, ctx, store=store)
```

- `store=None` hoặc chưa có `replay_run` → Tier D trung thực (giống stub F1).
- **Seam F6 đã nối sẵn**: `answer/pipeline.py` expose
  `answer_question(req: AskRequest, entitlements=...) -> Answer` đúng chữ ký
  `api.integrations.run_answer_pipeline` tìm — `/v1/ask` (JSON + SSE) tự dùng
  pipeline thật khi có DB, fallback Tier D honest khi DB unreachable.
- **Hook R-19 cho F4**: `retrieval.dense.on_snapshot_written(conn, run_id)` —
  truyền vào `engine.snapshot.replay(on_snapshot_written=...)` để persist
  embedding vào `node_version.embedding` ngay trong transaction replay;
  BM25 không cần persist (rebuild in-process <1s — D-39).
- `composer=` inject được (mặc định: GatewayComposer nếu có key, OfflineComposer
  nếu không / `LLM_OFFLINE=1`). OfflineComposer = trích dẫn verbatim tất định.
- `return_trace=True` → `(Answer, Trace)` — bằng chứng từng stage cho adversarial test.
- Mọi câu đều ghi `answer_log` (INV-10); Tier D là demand log.

## Bất biến CODE giữ (không cấu hình nào tắt được)

| Chốt | Ở đâu |
|---|---|
| Text bị thay/treo/amending không vào candidate set (INV-8, D-05) | predicate MỘT CỬA `retrieval/query_builder.py` (`retrievable ∧ status='active' ∧ hiệu-lực-tại-t`) |
| Audience lọc tại tầng truy vấn (INV-12, D-44) | mọi SQL trong query_builder đều mang `audience = ANY(entitlements)`; test cấu trúc cấm `FROM node_version` ngoài file này |
| Không văn tổng hợp khi gate cứng fail (INV-7) | `service.py`: Tier C/D dựng `answer=[]` + trích dẫn ghim, không chạm composer output |
| Banner đúng thứ tự, model không bỏ/bịa (R-31) | `compose.assemble_banners` — conflict > cohort_ambiguous > consolidation_pending > pending_change |
| Tier function total (R-34) | `tiers.decide_tier` |
| Judge κ-gate (R-33) | `judge_soft.judge_state` — mặc định `kappa.json=null` ⇒ cap Tier B + banner |

## Các mode (R-27, D-27)

- `current` / `point_in_time`: candidate MỘT CỬA → BM25∪dense→RRF → closure gate
  → composer → verifier cứng (regen 1) → judge → tier.
- `history` / pinpoint: đường alias→timeline riêng — thấy CẢ version treo/đóng
  (k8-10 Đ8 TT39 "chưa từng có hiệu lực"), nội dung code-built verbatim.
- `pending`: nhánh `valid_from` tương lai TÁCH RIÊNG có nhãn, code-built.

## Demo

```bash
uv run python -m answer.demo "Điều kiện vay vốn hiện nay?" --as-of 2024-03-01 --audience customer
uv run python -m answer.demo "Khoản 8 Điều 8 Thông tư 39/2016/TT-NHNN đã từng có hiệu lực chưa?"
# trên Postgres + LLM thật:
uv run python -m answer.demo "..." --db $TEST_DATABASE_URL --seed --llm
```

Snapshot seed (`answer/demo_seed.py`) là fixture MỘT nguồn cho MemStore, Postgres
và tests; run thật sẽ do engine F4 ghi — interface không đổi (chỉ đổi `run_id`).

## Judge hiệu chuẩn

```bash
uv run python -m answer.judge_calibrate --dry-run   # thống kê bộ 54 cặp
uv run python -m answer.judge_calibrate             # gọi judge thật, ghi kappa.json
```
