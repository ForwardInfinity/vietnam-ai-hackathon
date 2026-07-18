# api/ — bề mặt FastAPI /v1 (S6) — F6

Nền F1 (`schemas.py` ĐÓNG BĂNG — xem CONTRACTS.md). F6 sở hữu phần còn lại của `api/**`.
F5 nối answering thật qua seam `api/integrations.py` (một file đổi chữ ký).

## Contract SSE của `POST /v1/ask` (F6 định nghĩa bề mặt — F5 tiêu thụ)

Content negotiation, ADDITIVE với contract JSON F1:

- `Accept: text/event-stream` → SSE đúng trình tự S6:

```
event: meta      data: {run_id, as_of, as_known, audience, coverage[]}
event: token     data: {text}                    (0..n — thân trả lời tuần tự)
event: citation  data: <Basis JSON>              (0..n)
event: banner    data: <Banner JSON>             (0..n, thứ tự code lắp R-31)
event: tier      data: {tier, explain_vi, refusal_reason?}
event: done      data: {qa_id, answer: <Answer JSON đầy đủ>}
```

- Accept khác → JSON `Answer` như F1. Client cũ không đổi gì.
- Encoder: `api/sse.py::answer_to_events(Answer)` — F5 chỉ cần trả `Answer` đúng schema,
  bề mặt tự phân rã event. Test trình tự: `tests/api/test_surface_smoke.py`.

## Auth (hackathon, S6)

- `X-Role: employee|customer|curator` — thiếu → customer (least privilege).
- `/v1/admin/*` đòi curator; mutation đòi thêm `X-Actor` (người ký — INV-6, 422 nếu thiếu).
- Persona hiệu dụng /ask: role customer bị ghim customer (không nâng quyền qua body).
- Production `/admin` (UI) thêm basic-auth ở Caddy: user `curator`, pass `shb-curator-2026`
  (đổi: `caddy hash-password` → thay hash trong `deploy/Caddyfile`).

## INV-12 — một cửa audience

`api/gate.py` là CỬA DUY NHẤT phát mệnh đề lọc audience cho mọi endpoint đọc
(timeline/graph/norms/artifacts). Nó tự động chuyển sang `retrieval/query_builder`
của F5 khi module đó xuất hiện (`entitlements_for`). KHÔNG viết filter audience
ở endpoint. Pentest: `tests/api/test_inv12_heavy.py` (marker nội bộ không được
xuất hiện trong bất kỳ byte nào của response customer).

## Seam tích hợp (`api/integrations.py`)

| Hàm | Task | Khi chưa merge |
|---|---|---|
| `run_ingest_pipeline(artifact_id)` | F3 `ingest.pipeline` | ingest trả `pipeline="stub"`, artifact vẫn vào L0 |
| `run_replay()` | F4 `engine.snapshot.replay` | `POST /admin/replay` → 501 + TODO |
| `notify_blast_radius(op_ids)` | F4 `engine.blast_radius` | bỏ qua (notification không tự sinh) |
| `run_answer_pipeline(req, entitlements)` | F5 `answer.pipeline` | /ask trả Tier D trung thực (log answer_log khi có run) |
| `run_eval(**kw)` | F7 `eval.runner` | `POST /eval/run` → 501 |

Chữ ký thật khác → sửa DUY NHẤT `integrations.py` (+ `gate.py` cho query_builder).

## Ghi chú ngữ nghĩa

- `{key}` của timeline/graph: UUID node hoặc `<doc_key>~<path>` (vd
  `39/2016/TT-NHNN~dieu:8/khoan:2`) — đường alias→timeline D-27.
- Decision: `approve|reject|edit` chỉ trên op `proposed`; op `ratified` bất biến —
  sửa = `supersede` (op mới + `superseded_by`, D-20). Cột `ratified_by` ghi actor
  của QUYẾT ĐỊNH (với reject: người từ chối).
- Batch (`POST /admin/batches`): router R-15 chặn op per-op lọt lô; machine-verify
  3 pattern S4.4; fail 1 op → 422, KHÔNG op nào ratify; spot-check sàn 10%.
- `answer_log`: ghi được từ khi có `replay_run` đầu tiên (cột `run_id NOT NULL`) —
  trước đó /ask không log (TODO F4, ghi trong report).
