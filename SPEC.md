# Spec triển khai — từ thiết kế xuống code

## 0. Nguyên tắc chọn stack

Ba quy tắc sinh ra mọi lựa chọn dưới đây: (1) **hạ tầng tối thiểu** — team hackathon chết vì ops, không chết vì thiếu framework: một Postgres, một process API, một UI, không Kafka, không microservice; (2) **mọi thứ thông minh nằm trong code thuần, không nằm trong dịch vụ** — fold engine là pure function Python, test được bằng pytest, không phụ thuộc gì; (3) **lệch khỏi danh sách gợi ý của đề bài ở hai chỗ, có lý do**: bỏ Neo4j (đồ thị citation ở quy mô vài nghìn node là một bảng `edge` + recursive CTE; Neo4j là chi phí ops đổi lấy zero điểm khác biệt — visualization vẽ từ bảng edge bằng cytoscape.js), bỏ PhoBERT (không phải model sentence-embedding, giới hạn 256 token — dùng multilingual-e5 hoặc BGE-M3).

## 1. Stack chốt

| Lớp | Chọn | Ghi chú |
|---|---|---|
| DB duy nhất | **Postgres 16 + pgvector** | nodes, ops, edges, snapshots, conflicts, coverage — tất cả một chỗ; HNSW index cho dense |
| BM25 | **rank_bm25 in-process** (hoặc tantivy nếu muốn) | corpus vài nghìn node — rebuild index từ snapshot trong <1s mỗi lần ingest; tokenize bằng **pyvi/underthesea**, bảo vệ số hiệu (`39/2016/TT-NHNN`) thành 1 token bằng regex trước khi tách từ |
| Embedding | **multilingual-e5-base** (nhớ prefix `query:`/`passage:`) hoặc **BGE-M3** (8k context, dense+sparse) | chạy local bằng sentence-transformers, không cần GPU với corpus này |
| LLM | GPT-4o / Claude Sonnet qua API, **temperature 0 + JSON schema mode** cho extraction | ~vài trăm call extraction + 1–2 call/câu hỏi — chi phí không đáng kể; production của bank thì thay bằng model self-host (Qwen 72B), kiến trúc không đổi |
| API | **FastAPI + Pydantic** | Pydantic model map 1:1 với 6 đối tượng dữ liệu của thiết kế |
| UI | **Streamlit × 2 app** (chatbot + admin console) | |
| Parse file | python-docx, PyMuPDF; **ưu tiên bản HTML/DOCX** từ TVPL/cổng CP, né OCR ở MVP | |
| Deploy | docker-compose: `postgres` + `api` + `ui` | chạy được trên 1 laptop |

## 2. Schema — 10 bảng lõi (DDL rút gọn, đủ để code ngay)

```sql
CREATE TABLE artifact (        -- L0: log bất biến
  id TEXT PRIMARY KEY,         -- sha256 của file
  doc_no TEXT, doc_type TEXT,  -- '39/2016/TT-NHNN', 'thong_tu' | 'noi_bo' ...
  issuer TEXT, rank INT,       -- rank từ bảng precedence
  issued_date DATE, effective_date DATE,
  audience TEXT DEFAULT 'internal',      -- 'public' | 'internal'
  ingested_at TIMESTAMPTZ,               -- TRỤC K
  channel TEXT, raw BYTEA, text TEXT);

CREATE TABLE node (            -- L1: cây pháp lý, danh tính bền
  id UUID PRIMARY KEY,         -- birth-id, không bao giờ tái dùng
  artifact_id TEXT REFERENCES artifact,
  path TEXT,                   -- 'dieu:8/khoan:2' (địa chỉ bề mặt LÚC SINH)
  label TEXT, seq INT);

CREATE TABLE alias (           -- địa chỉ bề mặt -> node, có thời gian tính
  doc_no TEXT, path TEXT, node_id UUID,
  valid_from DATE, valid_to DATE);

CREATE TABLE op (              -- L2: toán tử, append-only
  id UUID PRIMARY KEY,
  kind TEXT CHECK (kind IN ('amend','repeal','suspend','replace','insert')),
  source_artifact TEXT, source_quote TEXT,   -- span gốc để UI đối chiếu
  target_node UUID, new_text TEXT,
  valid_from DATE, valid_to DATE,            -- cửa sổ hiệu lực của op
  scope_predicate JSONB,                     -- grandfathering
  risk_class TEXT,             -- 'definitional' | 'prescriptive'
  extractor TEXT, confidence REAL,
  status TEXT DEFAULT 'proposed',            -- proposed|ratified|rejected|superseded
  ratified_by TEXT, ingested_at TIMESTAMPTZ,
  prev_hash TEXT, hash TEXT);                -- hash-chain (rẻ, cắt được)

CREATE TABLE edge (            -- citation có kiểu
  src UUID, dst UUID,          -- dst NULL nếu frontier
  kind TEXT CHECK (kind IN ('dinh_nghia','tham_quyen','ngoai_le','frontier')),
  frontier_ref TEXT);

CREATE TABLE node_version (    -- L3: SNAPSHOT đã materialize (cái được index!)
  node_id UUID, version INT,
  text TEXT, status TEXT,      -- active|suspended|repealed
  valid_from DATE, valid_to DATE,
  scope_predicate JSONB,
  provenance UUID[],           -- chuỗi op tạo ra version này
  computed_under TIMESTAMPTZ,  -- K-cutoff của lần fold
  embedding vector(768));

CREATE TABLE conflict (
  id UUID, member_versions JSONB, reason TEXT,
  tier INT,                    -- 2=residual fold, 3=SEM
  status TEXT DEFAULT 'open', resolved_by_op UUID);

CREATE TABLE notification (    -- blast-radius / trigger notice
  op_id UUID, affected_doc TEXT, owner TEXT,
  acked BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ);

CREATE TABLE coverage (        -- freshness certificate lấy từ đây
  channel TEXT, last_seq TEXT, last_checked TIMESTAMPTZ);

CREATE TABLE precedence (doc_type TEXT, rank INT, valid_from DATE, valid_to DATE);
```

Truy vấn tritemporal rẻ đến mức này: *"luật tại t như ta biết ở K"* = fold chỉ những op có `status='ratified' AND ingested_at <= K`, rồi chọn version có `valid_from <= t < valid_to`. Một mệnh đề WHERE — đó là toàn bộ phép màu.

## 3. Pipeline ingest — cụ thể từng bước

**3.1 Parser cây (thuần regex, KHÔNG dùng LLM — cấu trúc là deterministic).** Chuẩn hóa NFC trước (văn bản VN trộn NFC/NFD — gotcha thật). State machine trên các mẫu: `^Chương [IVXLC]+`, `^Mục \d`, `^Điều \d+[a-z]?\.`, `^\d+[a-z]?\.` (khoản), `^[a-zđ]\)` (điểm). Trích ngày: `ngày (\d+) tháng (\d+) năm (\d+)`; ngày hiệu lực từ điều "Hiệu lực thi hành". Exit test: đếm điều/khoản/điểm của từng văn bản demo khớp tay 100% — parser sai thì mọi thứ sau vô nghĩa.

**3.2 Citation.** Hai tầng: regex bắt định danh tuyệt đối (`(Điều|khoản|điểm)\s+[\w,\s]+\s+(của\s+)?(Thông tư|Nghị định|Luật|Quyết định)\s+(số\s+)?[\d\w/–-]+`) — cover phần lớn; LLM resolve tham chiếu tương đối ("Điều này", "Thông tư này", "khoản 2 Điều này") và **gán kiểu** edge (định nghĩa/thẩm quyền/ngoại lệ) — prompt đưa câu chứa citation + 3 nhãn + ví dụ.

**3.3 Op extraction (tim của hệ).** Tầng rule bắt động từ hiệu lực: `sửa đổi, bổ sung|bãi bỏ|thay thế|ngưng hiệu lực|hết hiệu lực thi hành`. Tầng LLM nhận đoạn văn bản sửa đổi, trả JSON theo schema `op` (kind, target dạng địa chỉ bề mặt, new_text, valid_from), kèm `source_quote` bắt buộc. Resolver đổi địa chỉ bề mặt → `node_id` qua bảng alias. **Auto-ratify chỉ khi cả ba đồng thời**: rule và LLM khớp nhau, target resolve duy nhất, `risk_class='prescriptive'` (target không có inbound edge kiểu `dinh_nghia`). Còn lại vào queue cho admin console — UI hiển thị `source_quote` cạnh op đề xuất, một nút approve/reject/edit.

**3.4 Fold (engine, ~150 dòng Python thuần).**

```python
def fold(node_id, K=None):
    ops = ratified_ops(node_id, ingested_before=K)      # trục K
    ops.sort(key=lambda o: (rank(o), o.valid_from, o.ingested_at))  # sequencer
    versions = [base_version(node_id)]
    for op in ops:
        versions = apply(versions, op)   # amend: đóng version cũ tại valid_from, mở version mới
                                         # suspend: chèn version status='suspended' TRONG cửa sổ,
                                         #          version cũ HỒI SINH sau valid_to  <- TT10 case
                                         # repeal: đóng vĩnh viễn, không hồi sinh
    return versions                      # kèm provenance = op ids đã áp
```

Test bất biến quan trọng nhất (đây cũng là demo determinism): `fold_all_from_scratch() == incremental_state()` — chạy trong CI.

## 4. Retrieval + trả lời + verifier

```
câu hỏi → LLM parse {topic, t (mặc định now; bắt "hợp đồng ký <ngày>"), audience}
→ BM25 top-30 ∪ dense top-30 TRÊN node_version đang hiệu lực tại t   (lọc audience Ở TẦNG SQL)
→ RRF (k=60) → mở rộng 1-hop theo edge định_nghĩa/ngoại_lệ
→ context pack: mỗi node kèm header [id | doc | path | cửa sổ hiệu lực | trạng thái | tóm tắt chuỗi sửa đổi]
→ LLM soạn, bắt buộc đánh dấu [n] theo id
→ VERIFIER (code, không phải model): mọi [n] ∈ context; mọi đoạn trích khớp fuzzy ≥0.9
  với text snapshot; fail → regenerate 1 lần → fail nữa → Escalate
→ đóng gói Answer{content, provenance, freshness (đọc bảng coverage), ttl, audience}
```

Piecewise: nếu trong cửa sổ liên quan có ranh giới version hoặc `scope_predicate` — đưa **cả hai version vào context** với cửa sổ của chúng và ép LLM trả lời có điều kiện ("ký trước 01/09/2023: …; từ 01/09/2023: …"). Conflict tier 2/3 nếu retrieved set chạm bảng `conflict` → gắn certificate vào answer (employee) hoặc escalate (customer).

## 5. Cấu trúc repo & phân công

```
/corpus     văn bản gốc + fixtures đã parse tay (ground truth cho test)
/ingest     fetch, normalize, tree_parser.py, citation.py, op_extract.py
/engine     fold.py, snapshot.py, conflict.py, invariants/
/api        FastAPI: /ask /timeline/{node} /conflicts /ratify /graph
/ui         chat_app.py, admin_app.py (Streamlit)
/eval       naive_rag.py (baseline), benchmark.yaml, judge.py
```

Team 4 người: **P1** ingest (parser là nghề riêng — người kỹ tính nhất); **P2** engine + API; **P3** retrieval/answer/verifier; **P4** UI + eval + demo script. P1 và P2 là đường găng.

## 6. Kế hoạch phase (exit criteria quyết định khi nào sang phase sau)

| Phase | Việc | Exit criteria |
|---|---|---|
| 0 | compose up, fetch corpus demo | `docker compose up` chạy |
| 1 | tree parser + alias + dates | 100% corpus demo parse đúng (đối chiếu đếm tay) |
| 2 | citation + op extraction + **ratify UI** | TT06→TT39 sinh đủ op; TT10 sinh op `suspend` đúng 3 khoản |
| 3 | fold + snapshot + as-of + timeline API | query "Điều 8 TT39 tại 10/2023" trả đúng trạng thái treo; determinism test xanh |
| 4 | hybrid retrieval + answer + verifier + freshness | câu hỏi lãi suất trả lời từ snapshot kèm phả hệ 39→06→10 |
| 5 | precedence + certificate + blast-radius + 2 invariant | cặp Đ468 BLDS vs TT39 ra certificate cite NQ01/2019; văn bản nội bộ stale bị bắt |
| 6 | baseline naive RAG + benchmark + polish demo | bảng số naive-vs-ours theo 5 loại câu hỏi |

**Corpus demo (~10 văn bản, tất cả ca thật):** TT 39/2016/TT-NHNN · TT 06/2023 · TT 10/2023 · BLDS 2015 (Điều 468) · NQ 01/2019/NQ-HĐTP · Luật Các TCTD 2024 (vài điều) · TT 41/2016 (để demo frontier→Basel) · 2–3 văn bản nội bộ tự soạn: một quy trình cho vay cite TT39 (một bản **cố tình stale** để demo SEM catch), một mẫu hợp đồng có điều khoản chuyển tiếp. Bản hợp nhất TT39 của NHNN (tra trên cổng NHNN/TVPL) dùng làm differential oracle: diff snapshot của engine với nó — lệch là bug hoặc là điểm khoe.

**Benchmark harness:** `benchmark.yaml` ~40 câu, mỗi câu gắn loại (`amended | suspended | point_in_time | grandfather | conflict`) và **assertion kiểm bằng code** ("không được viện dẫn khoản 8 Điều 8 như đang hiệu lực", "phải nhắc TT10/2023") + LLM-judge phụ. Baseline = cùng embedding, chunk 500 token trên văn bản thô, không engine — ~100 dòng. Bảng kết quả theo loại chính là slide ăn điểm nhất.

## 7. Gotchas cụ thể (trả học phí trước)

Unicode NFC/NFD trộn lẫn — normalize ngay cửa vào. Số hiệu văn bản phải thành token nguyên vẹn trước khi word-segment, nếu không BM25 mù. `ngưng hiệu lực` ≠ `bãi bỏ` — hai op kind khác nhau, đừng để LLM gộp (đưa cả hai vào few-shot với TT10 làm ví dụ). Ngày hiệu lực ≠ ngày ban hành — TT06 ban hành 6/2023, hiệu lực 01/09/2023, và TT10 treo khoản *trước khi nó kịp có hiệu lực* — nếu schema không tách hai trục ngay từ đầu, ca này không biểu diễn nổi. Đừng chunk theo token — node cây *là* chunk; một điều quá dài thì context pack lấy khoản liên quan + header của điều.

## 8. Thang de-scope (cắt từ trên xuống khi cháy giờ)

hash-chain → reranker → TTL-đo-động-học (để TTL config tĩnh) → LLM pair-proposer tier-3c (giữ blast-radius 3a + invariant 3b) → graph viz đẹp (giữ bảng). **Không bao giờ cắt:** parser đúng, ratification gate, fold + as-of, verifier, benchmark. Bốn thứ đó *là* sản phẩm; mọi thứ khác là trang sức. Và ghi một dòng vào slide production-path để trả lời ban giám khảo: self-host LLM cho dữ liệu nội bộ, SSO/RBAC thay role-switch, và diễn tập rebuild materialized view từ log — vì bài học FAA tháng 1/2023: view sập trong khi log còn nguyên vẫn đủ để ground toàn bộ không phận một ngày.