# 03-SYSTEM-SPEC — Luật của hệ thống (normative, RFC 2119)

> File này sở hữu: DDL, invariant, thuật toán engine, pipeline nạp & trả lời, API, UI FR, repo skeleton.
> Tiền đề: mọi quyết định nền ở 01 (D-n), ngữ nghĩa domain ở 02. Requirement `R-n`, invariant `INV-n`.

## S0. Ba nguyên tắc sinh mọi lựa chọn

1. **Hạ tầng tối thiểu**: một Postgres, một process API, UI Streamlit, docker-compose — không Kafka, không microservice, không cluster search (D-38..D-44).
2. **Mọi thứ thông minh nằm trong code thuần**: fold engine là pure function Python, test bằng pytest, không phụ thuộc DB lúc test.
3. **Máy đề xuất — người phê chuẩn — engine tất định thực thi** (D-03): không code path nào ghi vào effective state mà không đi qua op đã ratify.

## S1. Stack (khóa)

| Lớp | Chọn | Ghi chú |
|---|---|---|
| DB | Postgres 16 + pgvector (HNSW) | tất cả bảng một chỗ |
| BM25 | `rank_bm25` in-process | rebuild từ snapshot <1s/lần ingest; tokenize `pyvi`; regex bảo vệ số hiệu thành 1 token TRƯỚC khi tách từ |
| Embedding | BGE-M3, `vector(1024)`, sentence-transformers local | chốt trước DDL (D-40) |
| LLM | gateway module duy nhất (`/answer/llm_gateway.py`): OpenAI-compatible / Anthropic / vLLM; extraction & composer một họ; judge KHÁC họ; temperature 0, JSON schema mode | D-41 |
| API | FastAPI + Pydantic | Pydantic model = LLM output contract |
| UI | Streamlit ×2 (`chat_app.py`, `admin_app.py`); graph pyvis, fallback bảng | D-42 |
| Parse file | python-docx, PyMuPDF; ưu tiên HTML/DOCX; né OCR MVP | D-43 |
| Deploy | docker-compose: `postgres` + `api` + `ui` | 1 laptop |

## S2. DDL (authoritative — chạy được ngay)

```sql
CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE audience_t   AS ENUM ('public','internal','restricted');
CREATE TYPE op_kind_t    AS ENUM ('amend','insert','repeal','suspend','close_window',
                                  'dinh_chinh','norm_decl','blanket_derogation');
CREATE TYPE op_status_t  AS ENUM ('proposed','ratified','rejected','superseded');
CREATE TYPE node_role_t  AS ENUM ('rule','definition','scope','exception','transition',
                                  'effectivity','amending','form','appendix');
CREATE TYPE nv_status_t  AS ENUM ('active','suspended','repealed');
CREATE TYPE edge_kind_t  AS ENUM ('dinh_nghia','tham_quyen','ngoai_le','chu_de','chuyen_tiep','frontier');
CREATE TYPE risk_t       AS ENUM ('definitional','prescriptive');
CREATE TYPE cfl_label_t  AS ENUM ('mau_thuan','chat_hon_ve_minh','chat_hon_ve_doi_tac','khac_pham_vi');
CREATE TYPE cfl_fork_t   AS ENUM ('internal_internal','internal_external','external_external','advisory');
CREATE TYPE cfl_status_t AS ENUM ('open','resolved','dismissed','accepted_risk');
CREATE TYPE sev_t        AS ENUM ('interruptive','advisory');
CREATE TYPE pev_kind_t   AS ENUM ('open_suspension','open_conflict');

-- L0: log bất biến
CREATE TABLE artifact (
  id            text PRIMARY KEY,          -- sha256 file
  doc_key       text UNIQUE NOT NULL,      -- '39/2016/TT-NHNN'
  doc_type      text NOT NULL,             -- luat|nghi_quyet|nghi_dinh|thong_tu|quyet_dinh|cong_van|noi_bo|bieu_mau|vbhn
  issuer        text NOT NULL,             -- 'QH','CP','NHNN','HDTP','SHB.<phòng>'
  title         text,
  issued_date   date, effective_date date,
  audience      audience_t NOT NULL DEFAULT 'internal',
  owner         text,                      -- phòng ban (corpus trong) — đích blast-radius
  review_by     date,                      -- hook doctrine D-50
  channel       text,                      -- 'congbao','sbv','internal_registry',...
  is_oracle     boolean NOT NULL DEFAULT false,  -- VBHN: chỉ để diff, không vào retrieval
  synthetic     boolean NOT NULL DEFAULT false,
  ingested_at   timestamptz NOT NULL DEFAULT now(),   -- TRỤC K
  raw bytea, text text);

-- L1: danh tính bền
CREATE TABLE node (
  id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),   -- birth-id, không tái dùng (INV-2)
  artifact_id text NOT NULL REFERENCES artifact,
  parent_id   uuid REFERENCES node,
  path        text NOT NULL,               -- 'dieu:8/khoan:2/diem:a/tiet:iii' | 'phuluc:04' (địa chỉ LÚC SINH)
  label       text, seq int,
  role        node_role_t NOT NULL DEFAULT 'rule',
  page_anchor jsonb);

CREATE TABLE alias (                        -- địa chỉ bề mặt -> node, có thời gian tính
  doc_key text, path text, node_id uuid REFERENCES node,
  valid_from date, valid_to date,
  PRIMARY KEY (doc_key, path, valid_from));

CREATE TABLE norm (                         -- danh tính xuyên thay-thế-toàn-văn-bản (D-09)
  id uuid, topic text NOT NULL,             -- cùng id xuyên chuỗi kế vị; 1 hàng mỗi hiện thân
  artifact_id text REFERENCES artifact,
  valid_from date, valid_to date,
  correlation jsonb,                        -- tương chiếu cũ↔mới — NON-BINDING (D-08)
  PRIMARY KEY (id, artifact_id));

-- L2: toán tử, append-only
CREATE TABLE op (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind op_kind_t NOT NULL,
  source_artifact text NOT NULL REFERENCES artifact,
  source_node uuid REFERENCES node,         -- điều khoản sửa đổi sinh op này (provenance)
  source_quote text NOT NULL,               -- span nguyên văn — UI đối chiếu, bắt buộc
  seq int NOT NULL,                         -- thứ tự xuất hiện TRONG artifact (tie-break §S4.5)
  target_node uuid REFERENCES node,
  target_op   uuid REFERENCES op,           -- op nhắm op (D-10)
  target_norm uuid,
  target_part text NOT NULL DEFAULT 'body' CHECK (target_part IN ('body','heading')),
  new_text text, new_heading text,
  valid_from date, valid_to date,
  valid_to_event text,                      -- sự kiện chưa định danh (D-11)
  scope_predicate jsonb,                    -- DSL đóng D-25
  risk_class risk_t,
  extractor text NOT NULL,                  -- 'rule','llm:<model>','curator:<id>'
  confidence real,
  status op_status_t NOT NULL DEFAULT 'proposed',
  ratified_by text, ratified_at timestamptz,
  ratify_batch uuid,
  superseded_by uuid REFERENCES op,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(target_node, target_op, target_norm) = 1
         OR kind = 'blanket_derogation'),
  CHECK (kind <> 'blanket_derogation' OR num_nonnulls(target_node,target_op,target_norm) = 0),
  CHECK (kind NOT IN ('amend','insert','dinh_chinh') OR new_text IS NOT NULL OR new_heading IS NOT NULL),
  CHECK (kind <> 'close_window' OR target_op IS NOT NULL));

CREATE TABLE ratify_batch (                 -- duyệt lô D-19
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  invariant_template jsonb NOT NULL,        -- S4.4
  description text, approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
  spot_check_rate real NOT NULL DEFAULT 0.1, spot_checked uuid[]);

-- Edge dẫn xuất theo PHIÊN BẢN node nguồn (D-13)
CREATE TABLE edge (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  src_node uuid NOT NULL REFERENCES node, src_version int NOT NULL,
  dst_node uuid REFERENCES node, dst_norm uuid, frontier_ref text,
  kind edge_kind_t NOT NULL, raw_citation text,
  resolved_against date,                    -- alias tra tại ngày văn bản nguồn
  confidence real NOT NULL DEFAULT 1.0,
  CHECK (num_nonnulls(dst_node, dst_norm, frontier_ref) <= 1));  -- cả ba NULL = unresolved (backlog)

-- L3: SNAPSHOT — thứ DUY NHẤT được index & trích dẫn (D-01)
CREATE TABLE node_version (
  node_id uuid NOT NULL REFERENCES node, version int NOT NULL,
  heading text, body text,
  status nv_status_t NOT NULL,
  valid_from date NOT NULL, valid_to date,  -- nửa-mở [from, to)
  scope_predicate jsonb, scope_hash text NOT NULL DEFAULT '',   -- chiều s TRONG khóa (D-04)
  provenance uuid[] NOT NULL,               -- chuỗi op tạo version này
  run_id uuid NOT NULL,
  retrievable boolean NOT NULL,             -- false ⟺ role='amending' ∨ artifact.is_oracle (INV-8)
  embedding vector(1024),
  PRIMARY KEY (node_id, version),
  UNIQUE (node_id, valid_from, scope_hash, status, run_id));
CREATE INDEX ON node_version (valid_from, valid_to) WHERE retrievable;
CREATE INDEX ON node_version USING hnsw (embedding vector_cosine_ops) WHERE retrievable;

CREATE TABLE replay_run (
  run_id uuid PRIMARY KEY, k_cutoff timestamptz NOT NULL,
  corpus_hash text NOT NULL, started timestamptz, finished timestamptz, ops_count int);

CREATE TABLE conflict (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  member_versions jsonb NOT NULL,           -- [{node_id, version}] — unsat-core tối thiểu
  tier int NOT NULL CHECK (tier IN (1,2,3)),
  label cfl_label_t, fork cfl_fork_t,
  doctrine jsonb,                           -- {rank_a, rank_b, same_issuer, art156: 'ap_dung'|'khong_phan_dinh'}
  reason text NOT NULL,
  status cfl_status_t NOT NULL DEFAULT 'open',
  resolved_by_op uuid REFERENCES op, ticket_ref text,
  detected_by text, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE notification (                 -- blast-radius (D-36)
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  op_id uuid REFERENCES op, affected_node uuid, affected_doc text, owner text,
  severity sev_t NOT NULL DEFAULT 'advisory',
  acked boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE coverage (channel text PRIMARY KEY, last_seq text, last_checked timestamptz);

CREATE TABLE pending_event (                -- D-11
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind pev_kind_t NOT NULL,
  ref uuid NOT NULL,                        -- op có valid_to_event | conflict chờ statement giải
  predicate text NOT NULL,                  -- "văn bản QPPL mới quy định về các vấn đề này"
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  closed_by_op uuid REFERENCES op);

CREATE TABLE precedence (                   -- quy tắc ưu tiên là statement CÓ NGUỒN (D-15)
  doc_type text, issuer text, rank int NOT NULL,
  source_node uuid, valid_from date, valid_to date);

CREATE TABLE answer_log (                   -- append-only, replay được (INV-10)
  qa_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id uuid, question text NOT NULL,
  audience audience_t NOT NULL, as_of date NOT NULL, as_known timestamptz,
  tier char(1) NOT NULL CHECK (tier IN ('A','B','C','D')),
  claims jsonb NOT NULL,                    -- [{text, node_version_refs[], hard_pass, judge_verdict}]
  retrieved jsonb NOT NULL, conflicts uuid[], banners jsonb NOT NULL,
  run_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE feedback (                     -- kênh SEM (d) — D-37
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  qa_id uuid REFERENCES answer_log, node_id uuid, kind text NOT NULL DEFAULT 'nghi_da_cu',
  note text, created_at timestamptz NOT NULL DEFAULT now());

-- Views
CREATE VIEW v_consolidation_pending AS      -- node có op proposed đã đến hạn hiệu lực
  SELECT DISTINCT target_node AS node_id FROM op
  WHERE status='proposed' AND valid_from <= current_date AND target_node IS NOT NULL;
```

R-1. Trigger cấm UPDATE/DELETE trên `artifact`, `op` (sau ratify), `answer_log`, `node_version` (chỉ replay ghi, trong một transaction đổi `run_id`).
R-2. Truy vấn tritemporal chuẩn: *"luật tại t như biết ở K"* = fold chỉ op `status='ratified' AND ingested_at <= K`, chọn version `valid_from <= t < COALESCE(valid_to,'infinity')`. Một mệnh đề WHERE.

## S3. Invariants (CI + trigger; mỗi INV là một test chạy được)

| ID | Phát biểu |
|---|---|
| INV-1 | Append-only: artifact/op-đã-ratify/answer_log không bao giờ UPDATE/DELETE; sửa op = op mới + `superseded_by` |
| INV-2 | Birth-id không tái sử dụng; node do replace-cấp-cha sinh ra có id MỚI (D-08) |
| INV-3 | Determinism: `fold_all_from_scratch() == incremental_state()`, VÀ bất biến dưới hoán vị thứ tự nạp artifact (TT06/TT10 đảo chiều) |
| INV-4 | Tiling: với mỗi (node, scope_hash), các cửa sổ version không chồng lấn, phủ liên tục từ lần hiệu lực đầu |
| INV-5 | Window inviolability: revoke một op không đổi bất kỳ version nào có `valid_to <= revoke.valid_from` (bẫy viết-lại-lịch-sử) |
| INV-6 | No-auto-ratify: mọi op `ratified` có `ratified_by` là người, hoặc `ratify_batch` có `approved_by` người + machine-check invariant_template pass từng op |
| INV-7 | Không code path nào render văn tổng hợp khi hard-verifier fail (floor = Tier C sources-only) |
| INV-8 | Không text nào ngoài `node_version.retrievable ∧ status='active' ∧ hiệu-lực-tại-t` vào composer context. Adversarial probes GỒM contamination: query dựng từ `new_text` của op suspend/repeal KHÔNG được trả node `amending` chứa quote |
| INV-9 | Rebuild: dựng lại toàn bộ node_version từ artifact+op cho ra kết quả bit-exact (modulo run_id) |
| INV-10 | Answer replay: từ answer_log + run_id, mọi trích dẫn tái dựng được nguyên văn |
| INV-11 | Alias nhất quán: mọi (doc_key, path) tại một ngày resolve về đúng MỘT node |
| INV-12 | Audience: token customer không nhận được bất kỳ byte nào từ artifact `internal/restricted` ở MỌI stage (retrieval, closure, composer, citation) |

## S4. Pipeline substrate

### S4.1 Ingest & parse (R-3..R-7)

R-3. Thứ tự: lưu artifact L0 (sha256, tem K) → chuẩn hóa (NFC; vá khoảng trắng số hiệu; gộp header 2 cột vỡ dòng) → parse cây (state machine §02-§1) → sinh node + alias + dates → gán `role` (rule-based: điều "Giải thích từ ngữ"→`definition`, "trừ trường hợp"→giữ `rule` nhưng edge `ngoai_le`, điều khoản chuyển tiếp→`transition`, hiệu lực→`effectivity`, node chứa động-từ-hiệu-lực + quote→`amending`, phụ lục→`appendix`).
R-4. Exit test parser: đếm điều/khoản/điểm/tiết từng văn bản demo khớp `corpus/manifest.json` (đếm tay) 100%.
R-5. Role `amending` phải được curator XÁC NHẬN tại ratify (curator đang nhìn node đó khi duyệt op nó sinh ra); node `amending` ⇒ `retrievable=false` mọi version (INV-8).
R-6. Coverage: sau mỗi lần quét kênh, cập nhật `coverage(channel, last_seq)`; kênh Công báo dò gap theo số tuần tự → gap ⇒ cảnh báo backlog.
R-7. VBHN nạp với `is_oracle=true`: parse để diff (S4.7), không sinh op, không retrieval.

### S4.2 Citation → edge (R-8..R-10)

R-8. Ba tầng: (a) regex pinpoint + expand enumeration; (b) `^Căn cứ` → `tham_quyen` (regex, miễn phí; "Luật X đã được sửa đổi bởi Luật Y" → dst_norm); (c) LLM resolve tham chiếu tương đối + GÁN KIỂU edge còn lại — prompt bắt buộc chứa quy tắc binding §02-5.3 và context-stack omnibus §02-5.4.
R-9. Resolve địa chỉ qua `alias` tại `resolved_against` = ngày ban hành văn bản nguồn; lúc trả lời re-project theo as_of.
R-10. Không resolve được → edge với cả 3 đích NULL + confidence 0 → backlog; nếu kiểu thuộc mandatory closure → chạm là Tier D (D-29). Tham chiếu theo mảng → `dst_norm` (KHÔNG cưỡng ép về unit).

### S4.3 Op extraction (R-11..R-14)

R-11. Tầng rule: quét động từ hiệu lực (bảng §02-§3) trên MỌI node kể cả "Điều khoản thi hành". Tầng LLM: input đoạn văn bản sửa đổi + chương-context; output JSON schema:

```json
{ "ops": [ { "kind": "amend|insert|repeal|suspend|dinh_chinh|norm_decl|blanket_derogation",
  "target_surface": "khoản 2 Điều 8 TT 39/2016/TT-NHNN | null",
  "target_is_amending_provision": false,
  "target_part": "body|heading",
  "new_text": "…|null", "new_heading": "…|null",
  "valid_from": "date|null", "valid_to": "date|null",
  "valid_to_event": "string|null",
  "scope_predicate": {}, "source_quote": "NGUYÊN VĂN BẮT BUỘC",
  "confidence": 0.0 } ] }
```

Prompt MUST: một op một thao tác; tách enumeration; `ngưng hiệu lực`≠`bãi bỏ` (few-shot TT10); binding "Thông tư này"; ngày hiệu lực riêng từng op nếu văn bản phân kỳ; không đoán target — unknown ⇒ null + confidence thấp.
R-12. Resolver surface→node_id qua alias; `target_is_amending_provision=true` (hoặc resolver phát hiện target là node role `amending`) ⇒ chuyển thành `target_op` trỏ op mà node đó đã sinh. Op `insert`: node đích được TẠO (cấp birth-id) ngay lúc đề xuất để thỏa CHECK target; alias và version chỉ sinh khi ratify + replay.
R-13. Cross-validation ngoặc provenance (§02-5.5): lệch ⇒ op bị giữ ở queue với cờ đỏ.
R-14. Thay-cụm-từ: extractor emit đề xuất dạng danh sách node bị chạm; curator materialize thành các op `amend` node-level tại UI (D-21).

### S4.4 Ratify — hai hàng đợi (R-15..R-17)

R-15. Router (D-19): per-op nếu `risk_class='definitional'` (target có inbound edge `dinh_nghia`) ∨ kind `norm_decl` ∨ `valid_from` cần phân loại ngữ nghĩa ∨ cờ đỏ R-13; ngược lại đủ 4 điều kiện cơ học (rule↔LLM khớp; target resolve duy nhất; prescriptive; ngày đọc thẳng) → batch-eligible.
R-16. Batch-ratify: curator khai `invariant_template`, máy verify TỪNG op khớp template, sign cả lớp, spot-check ≥ 10%:

```json
{ "pattern": "phrase_replace", "from": "X", "to": "Y" }
{ "pattern": "uniform_field_change", "field_regex": "\\d+ ngày làm việc", "from": "10", "to": "07" }
{ "pattern": "mass_repeal", "target_doc_keys": ["…"] }
```

R-17. UI ratify (FR-8..13): hiển thị `source_quote` cạnh diff (target hiện tại vs sau-áp), approve/edit/reject, sort theo risk rồi confidence tăng dần. Throughput queue này là đường găng — build TRƯỚC chat UI.

### S4.5 Fold engine (R-18..R-20 — pure function, ~200 dòng)

```python
def resolve_windows(ops):        # PASS 1 — op nhắm op
    # close_window(target): đặt valid_to = op.valid_from cho op đích (đóng treo-theo-sự-kiện)
    # repeal(target_op):    window_end = min(end, valid_from) — CHỈ từ đó trở đi (INV-5)
    # valid_to_event chưa đóng → cửa sổ mở vô hạn (pending_event giữ nghĩa vụ)

def fold(node_id, K=None) -> list[Version] | ConflictCertificate:
    ops = ratified_node_ops(node_id, ingested_before=K)
    ops.sort(key=lambda o: (precedence_rank(o, at=o.valid_from),   # bảng precedence CÓ cửa sổ
                            o.valid_from, o.issued_date, o.seq,
                            o.source_artifact, o.ingested_at))     # canonical trước, nạp sau cùng
    versions = [base_version(node_id)]        # node do 'insert' sinh: base = new_text của op insert
    for op in ops_with_resolved_windows:
        if incomparable(op, applied):          # chồng cửa sổ, precedence không phân định
            return ConflictCertificate(members=…, reason=…)   # tier-2: KHÔNG chọn bừa
        versions = apply(versions, op)
        # amend:       đóng version tại valid_from, mở version mới (body/heading theo target_part)
        # insert:      đã xử lý ở sinh node; op này chỉ mang cửa sổ
        # repeal:      đóng vĩnh viễn, status='repealed'
        # suspend:     chèn version 'suspended' trên cửa sổ; cửa sổ mở vô hạn nếu event chưa đóng;
        #              version 'active' có thể KHÔNG BAO GIỜ tồn tại (k8-10 Đ8 TT39)
        # dinh_chinh:  thay text HỒI TỐ từ ĐẦU cửa sổ của version bị đính chính
        # scope_predicate: split versions — (V ∧ ¬P giữ nguyên) + (V ∧ P áp op); scope_hash = hash chuẩn hóa predicate
    return versions   # provenance = op ids đã áp, theo thứ tự
```

R-18. Sau fold toàn corpus: ghi `node_version` MỘT transaction với `run_id` mới; đánh dấu run cũ stale; API answering pin run_id (từ chối serve khi run stale, client auto-retry).
R-19. Embedding + BM25 index rebuild từ snapshot sau mỗi run.
R-20. Certificate từ fold ghi vào `conflict` tier-2 + `pending_event(open_conflict)`.

### S4.6 Pending-event sweep (R-21)

Sau MỖI ingest: với từng `pending_event` open, so văn bản vừa nạp với `predicate` (rule + LLM đề xuất ứng viên) → phát **đề xuất đóng** vào ratify queue (op `close_window` cho suspension; op giải/`resolved_by_op` cho conflict — NQ01/2019 đi đường này). Máy không tự đóng.

### S4.7 Differential oracle (R-22)

Có VBHN (`is_oracle`) → diff text materialized vs VBHN (normalize whitespace/diacritics) → lệch vào backlog phân xử: lỗi parser / lỗi precedence / lỗi nhà hợp nhất. Oracle là chuông báo, không phải chân lý (D-22).

### S4.8 Blast-radius & SEM (R-23..R-26)

R-23. Khi op ratified: where-used = inbound edges tới target (kể cả `chu_de` qua Norm của artifact chứa target) → `notification` cho `owner`; severity: `interruptive` ⟺ risk_class definitional; còn lại advisory digest (D-36). Biểu mẫu (doc_type `bieu_mau`) nhận propagation như mọi doc.
R-24. Invariant compliance (`/engine/invariants/*.py`, registry enable/disable): chạy trên effective state sau mỗi run; ship 2 mẫu: INV-COMP-01 trần-lãi-suất nhất quán (nội bộ vs TT39/NQ01), INV-COMP-02 ngày-áp-dụng-LLTP nhất quán (fixture TT11). Fail → conflict tier-3 + notification.
R-25. Pair-proposer LLM offline theo cụm chủ đề, gán nhãn D-34 trước khi vào queue người; `chat_hon_ve_minh` tự loại.
R-26. Ownership fork khi mở conflict: theo cặp issuer (nội↔nội → ticket owner; nội↔ngoại → escalation compliance; ngoại↔ngoại → surface; frontier → advisory).

## S5. Pipeline answering

### S5.1 Question compiler (R-27 — phần không-commodity, có test riêng)

```json
{ "topic_terms": ["…"], "as_of": "date (default today)", "as_known": "ts|null",
  "cohort": {"contract_signed_before": "date|null", "not_amended_on_or_after": "date|null",
             "entity_class": "…|null"},
  "audience": "employee|customer",
  "mode": "current|point_in_time|history|pending",
  "pinpoint": "địa chỉ bề mặt|null" }
```

R-27. Rules: cụm thời gian ("năm 2022", "tại thời điểm giải ngân") → as_of/mode; "sắp tới/từ tháng sau" → pending; hỏi về địa chỉ cụ thể/"đã từng" → pinpoint/history (đi đường alias→timeline, thấy cả version treo/đóng — D-27); retrieved set có ranh giới version hoặc scope mà thiếu cohort → employee: hỏi lại đúng MỘT câu HOẶC piecewise; customer: piecewise bảo thủ/escalate. KHÔNG BAO GIỜ chọn thầm nhánh.

### S5.2 Retrieval (R-28)

```sql
SELECT nv.* FROM node_version nv JOIN node n ON … JOIN artifact a ON …
WHERE nv.run_id = :pinned AND nv.retrievable AND nv.status='active'
  AND nv.valid_from <= :as_of AND (:as_of < nv.valid_to OR nv.valid_to IS NULL)
  AND applicability_matches(nv.scope_predicate, :cohort)   -- cohort thiếu ⇒ match mọi nhánh
  AND a.audience = ANY(:entitlements)                      -- query-builder MỘT CỬA (D-44, INV-12)
```
BM25 top-30 ∪ dense top-30 (cùng predicate) → RRF k=60 → top-12. Mode `pending`: thêm nhánh version `valid_from > today` tách riêng, dán nhãn.

### S5.3 Closure (R-29)

Từ top-12: theo edge re-projected tại as_of, depth ≤2, budget 24 node/12k token, thứ tự bắt buộc: (1) `ngoai_le` luôn, 2 chiều; (2) `chuyen_tiep` khớp cohort (mơ hồ → pull + flag `cohort_ambiguous`); (3) `dinh_nghia` cho term có mặt; (4) `tham_quyen` khi cần. `closure_complete` := không rơi mandatory vì budget ∧ không chạm mandatory unresolved. ¬closure_complete ⇒ Tier D (`closure_incomplete`).

### S5.4 Context pack & composer (R-30..R-31)

R-30. Mỗi node kèm header `[id | doc_key | path | cửa sổ hiệu lực | status | scope | tóm tắt chuỗi sửa đổi]`. Có ranh giới version/scope trong cửa sổ liên quan → đưa CẢ các nhánh với cửa sổ của chúng, ép trả lời có điều kiện.
R-31. Composer contract (JSON): `{answer_vi (markdown, claim tag [n]), claims[{id, text, refs[]}], bases[{ref, citation_vi, interval}], refusal|null}`. Prompt MUST: chỉ dùng expression được cấp; mọi câu quy phạm mang ≥1 tag; con số/ngưỡng quote VERBATIM; thiếu căn cứ → refusal (không độn). Render 4 mục cố định: **Trả lời / Căn cứ / Xung đột / Thay đổi sắp hiệu lực**; banner do CODE lắp từ flags — model không thể bỏ/bịa (thứ tự: conflict > cohort_ambiguous > consolidation_pending > pending_change).

### S5.5 Verifier hai tầng + thang tier (R-32..R-34)

R-32. **Gate cứng (code, luôn bật)**: mọi `[n]` ∈ context; mọi đoạn trong ngoặc kép khớp fuzzy ≥0.9 với snapshot; mọi con số xuất hiện trong claim tồn tại exact trong ref. Fail → regenerate 1 lần → fail → **Tier C**: render sources-only (trích dẫn ghim + citation, KHÔNG văn tổng hợp — INV-7).
R-33. **Judge mềm (LLM KHÁC HỌ composer, context cô lập {claim, cited texts}, temp 0)**: verdict `entails|partial|fails` từng claim. Chưa đạt κ≥0.8 trên ≥300 cặp Việt gán nhãn, hoặc judge off → mọi answer cap **Tier B** + banner "kiểm chứng ngữ nghĩa chưa hiệu chuẩn". Có verdict fail → flag, cap B.
R-34. **Tier function (total)**:

```
D  nếu ¬retrieval_floor ∨ ngoài coverage ∨ closure_incomplete ∨ composer refusal
   → route chuyên gia + ghi demand log
C  nếu ¬hard_pass (sau 1 regen)
B  nếu hard_pass ∧ (flags≠∅ ∨ judge chưa-κ/off/fail)
A  nếu hard_pass ∧ judge pass ∧ flags=∅
flags := {in_conflict (chạm conflict open), cohort_ambiguous, consolidation_pending
          (chạm v_consolidation_pending), pending_change (có version tương lai cùng node),
          open_suspension (chạm node đang treo với pending_event mở)}
```

### S5.6 Freshness, audience, log (R-35..R-37)

R-35. Mọi answer mang: `run_id` + coverage attestation ("Công báo đến số N ngày D; registry nội bộ đến D'") + TTL config tĩnh theo mảng (D-32).
R-36. Customer: entitlements `{public}` (INV-12), giọng phổ thông, disclaimer thông-tin-không-phải-tư-vấn, conflict → escalate thay vì certificate; employee thấy certificate đầy đủ.
R-37. Ghi answer_log MỌI câu (INV-10); nút "nghi đã cũ" → `feedback`.

## S6. API (FastAPI `/v1`, SSE cho chat)

| Endpoint | Chức năng |
|---|---|
| `POST /ask` | {session, question, as_of?, cohort?} → SSE: meta{run_id, coverage} · token · citation · banner · tier · done{qa_id} |
| `GET /nodes/{key}/timeline` | mọi version (kể cả suspended/repealed/không-bao-giờ-active) + dải treo + provenance + diff |
| `GET /nodes/{key}/graph?depth&as_of` | edges có kiểu (where-used + outbound) |
| `GET /norms/{id}` | chuỗi kế vị + correlation (non-binding) |
| `POST /admin/ingest` | multipart → S4.1–S4.3 → đề xuất op |
| `GET /admin/ops?status=proposed` | queue theo R-17 order |
| `POST /admin/ops/{id}/decision` | approve/edit/reject |
| `POST /admin/batches` | tạo batch + invariant_template → machine-verify → sign |
| `POST /admin/replay` | chạy fold toàn corpus → {run_id, changed_nodes, certificates, guard_violations} |
| `GET /admin/backlog` | consolidation_pending, oracle_mismatch, unresolved refs, pending_events open, coverage gaps |
| `GET/POST /admin/conflicts` | kanban + triage + fork |
| `GET /admin/demand` | câu Tier-D xếp theo tần suất |
| `GET /admin/notifications` | digest theo owner, ack |
| `POST /eval/run` | chạy golden set → report (04) |

Auth: header role (hackathon) / OIDC (pilot); mọi call mutating ghi actor. `/admin/*` = curator.

## S7. UI FR (Streamlit ×2)

**Chat**: FR-1 as-of control + tem "Theo trạng thái văn bản ngày … (run …)"; FR-2 citation chip → panel: text version, cửa sổ, badge "hiệu lực từ …", timeline slider, graph 1-hop, link văn bản gốc (page anchor); FR-3 banner TRÊN thân trả lời, đúng thứ tự R-31; FR-4 tier badge + giải thích thường dân; FR-5 Tier C render layout trích-dẫn-only khác biệt thị giác (degradation là feature); FR-6 Tier D card route chuyên gia; FR-7 toggle persona employee/customer (customer ẩn tier nội bộ, giữ citation + ngày); FR-8 nút "nghi đã cũ" mỗi answer.

**Admin**: FR-9 queue op: source_quote ↔ diff cạnh nhau, approve/edit/reject, sort risk→confidence; FR-10 batch panel: khai template → máy verify → sign → spot-check list; FR-11 nút replay + báo cáo run (changed nodes, certificates mới); FR-12 backlog dashboard (đếm + drill-down); FR-13 conflict kanban theo fork; FR-14 demand log + notification digest.

## S8. Repo skeleton & ownership

```
/corpus     văn bản gốc + fixtures + manifest.json (ground truth đếm tay; synthetic:true)
/ingest     fetch.py, normalize.py, tree_parser.py, citation.py, op_extract.py, roles.py
/engine     fold.py, windows.py, scope.py, snapshot.py, conflict.py, sweep.py, oracle_diff.py,
            blast_radius.py, invariants/
/retrieval  bm25.py, dense.py, fuse.py, closure.py, query_builder.py   # MỘT CỬA audience
/answer     compiler.py, compose.py, verify_hard.py, judge_soft.py, tiers.py, freshness.py,
            llm_gateway.py
/api        main.py (FastAPI), schemas.py (Pydantic = data objects 1:1)
/ui         chat_app.py, admin_app.py
/eval       golden.yaml, runner.py, baseline_naive.py, metrics.py
```

Mapping trách nhiệm khi decompose task: parser+extraction (ingest/) ↔ 02; engine/ ↔ S4.5–S4.8; retrieval+answer ↔ S5; eval ↔ 04. Ratify UI (admin_app) làm TRƯỚC chat UI (R-17).
