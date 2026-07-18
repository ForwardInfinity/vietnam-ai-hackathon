# CONTRACTS — F1 đóng băng cho các session song song

> Người tạo: session F1. Các session F2-F7 chạy song song trên worktree và TIÊU THỤ
> các contract dưới đây. Spec gốc: `docs/` (01 là hiến pháp — không mở lại D-n).

## Giao thức đổi contract

- **Additive** (thêm model mới, thêm field optional, thêm test, thêm endpoint mới): làm thẳng, ghi rõ trong commit.
- **Breaking** (đổi/xóa field, đổi kiểu, đổi semantics, đổi DDL/trigger, đổi chữ ký gateway, đổi tên Makefile target, đổi layout compose): **DỪNG — báo user, chờ duyệt**. Không workaround lệch spec; thấy D-n bất khả thi cũng DỪNG và báo phân tích.
- Trước MỌI push: `make smoke` phải xanh (<60s, không cần Docker/model). Push lên master ⇒ tự deploy production.

## Thứ đã đóng băng

| Artifact | Nội dung | Ghi chú |
|---|---|---|
| `db/init.sql` | DDL S2 **nguyên văn** (16 bảng, 12 enum, view) + trigger R-1 | Đổi DDL = đổi `docs/03` trước, và là breaking |
| `api/schemas.py` | Enum khớp từng giá trị SQL; 16 model bảng 1:1; `ScopePredicate` (DSL đóng D-25, extra=forbid); `CompiledQuestion` (S5.1); `ExtractedOp`/`ExtractionResult` (R-11); `ComposerOutput` (R-31); `Answer` + `AskRequest` (00-VISION §3) | Pydantic model = LLM output contract (D-42) |
| `answer/llm_gateway.py` | `get_gateway()` · `LLMGateway.complete_json(role, system, user, schema) -> dict` · `check_family_guard()` · `model_family()` · `LLMGatewayError`/`FamilyGuardError` | MỌI call LLM đi qua đây (D-41) — không module nào tự gọi HTTP tới LLM |
| `docker-compose.yml` | 4 service: `postgres` · `api` (uvicorn `--root-path /api`) · `ui` · `caddy`; HF cache host mount vào api | Thêm service = additive; đổi tên/port = breaking |
| `deploy/Caddyfile` | `/health`→api · `/api/*`→api (strip) · `/admin*`→placeholder (F6 thay) · còn lại→ui | F6 đổi `/admin*` sang admin Streamlit: additive |
| `Makefile` | `smoke` (gate merge, not-heavy) · `test` (not-llm_live) · `up` | |
| API hiện có | `GET /health` · `POST /v1/ask` (JSON, kiểu `Answer`) | F5 nâng `/v1/ask` lên SSE theo S6: breaking có kiểm soát — báo user trước |
| `build_status.json` | Mỗi session cập nhật dòng của mình khi xong milestone | UI trang Build status đọc file này |

## LLM gateway — hợp đồng sử dụng

```python
from answer.llm_gateway import get_gateway
out: dict = get_gateway().complete_json(
    role="extract" | "compose" | "judge",   # KHÔNG có role khác
    system="...", user="...",
    schema={...},                            # JSON Schema — output validate + retry 1 lần
)
```

- Env per-role: `LLM_{EXTRACT|COMPOSE|JUDGE}_{MODEL|BASE_URL|API_KEY|JSON_MODE}`.
  Defaults (đã verify): extract/compose = `google/gemini-2.5-flash` @ OpenRouter, `json_schema`;
  judge = `deepseek-chat` @ api.deepseek.com, `json_object` (schema nhúng system prompt).
- Key fallback theo provider: `OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` / `LLM_API_KEY`.
- Guard: judge KHÁC HỌ extract/compose (so prefix tên model) — raise lúc boot (api lifespan).
- Temperature LUÔN 0. Invalid JSON/schema → retry đúng 1 lần → `LLMGatewayError` (caller thoái lui tier, không nuốt lỗi).
- OpenRouter 402/429 → tự fallback `<model>:free` + log warning (một lần).

## DB — giao thức ghi

- `artifact`, `answer_log`: append-only tuyệt đối (trigger chặn UPDATE/DELETE).
- `op`: `proposed` sửa/xóa tự do; sau ratify bất biến — sửa lỗi = op MỚI + set `status='superseded', superseded_by=<new>` trên op cũ (transition duy nhất được trigger cho phép, không đổi cột nào khác — D-20).
- `node_version`: UPDATE/DELETE chỉ trong transaction replay của F4: `SET LOCAL lawstate.replay = 'on'` (INSERT tự do — replay ghi version mới với `run_id` mới).
- Không code path nào ghi effective state ngoài op đã ratify (D-03, INV-6).

## Test markers & CI

| Marker | Ý nghĩa | Smoke | CI | Thủ công |
|---|---|---|---|---|
| (không marker) | unit thuần, không tài nguyên ngoài | ✅ | ✅ | ✅ |
| `heavy` | cần DB/network/model — **tự skip khi thiếu tài nguyên** (vd `TEST_DATABASE_URL`) | ❌ | ✅ lane riêng (chỉ có Postgres service — test cần model phải tự skip) | ✅ |
| `llm_live` | gọi LLM trả tiền | ❌ | ❌ | `uv run pytest -m llm_live` |

- CI (`.github/workflows/deploy.yml`): job `test` = smoke + `pytest -m "heavy and not llm_live"` với `TEST_DATABASE_URL` trỏ service container pgvector; job `deploy` (chỉ master, test xanh) build trên VPS xong mới thay container, rồi verify `https://152-42-242-127.sslip.io/health` từ ngoài — fail là job đỏ, stack cũ vẫn chạy.
- `tests/test_db_triggers.py` DROP SCHEMA cascade — `TEST_DATABASE_URL` chỉ được trỏ DB vứt được.

## Ownership path (S8) — ai sở hữu gì

| Path | Session | Spec |
|---|---|---|
| `corpus/` (văn bản + `manifest.json` đếm tay) | F2 | 04 |
| `ingest/` (fetch, normalize, tree_parser, citation, op_extract, roles) | F3 | 02, S4.1-S4.3 |
| `engine/` (fold, windows, scope, snapshot, conflict, sweep, oracle_diff, blast_radius, invariants/) | F4 | S4.5-S4.8 |
| `retrieval/` (bm25, dense, fuse, closure, query_builder — MỘT CỬA audience) | F5 | S5.2-S5.3 |
| `answer/` (compiler, compose, verify_hard, judge_soft, tiers, freshness; `llm_gateway.py` F1 đã xong) | F5 | S5.1, S5.4-S5.6 |
| `api/` (endpoint mới theo S6; `main.py`/`schemas.py` nền F1) | F5/F6 mở rộng | S6 |
| `ui/` (`chat_app.py` F1 khung — F5/F6 nâng cấp; `admin_app.py` F6 — làm TRƯỚC chat, R-17) | F5/F6 | S7 |
| `eval/` (golden.yaml, runner, baseline_naive, metrics) | F7 | 04 |
| `db/`, `deploy/`, `.github/`, `Makefile`, gateway | F1 (đóng băng) | S2, S8 |

## Vận hành

- Local dev: `cp .env.example .env` điền key → `make up` (compose) hoặc `uv run uvicorn api.main:app` + `uv run streamlit run ui/chat_app.py`.
- Production: mọi commit master tự deploy VPS `/opt/app` → https://152-42-242-127.sslip.io (UI `/`, API `/api/docs`, health `/health`, admin `/admin`).
- Secrets: `.env` đã gitignore; key CHỈ nằm ở `.env` local, GitHub secrets, `/opt/app/.env` trên VPS. Repo PUBLIC — không key nào vào git/log/báo cáo.
