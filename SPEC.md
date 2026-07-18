# Spec triển khai — từ thiết kế xuống code

## 0. Nguyên tắc chọn stack

Ba quy tắc sinh ra mọi lựa chọn dưới đây: (1) **hạ tầng tối thiểu** — team hackathon chết vì ops, không chết vì thiếu framework: một Postgres, một process API, một UI, không Kafka, không microservice; (2) **mọi thứ thông minh nằm trong code thuần, không nằm trong dịch vụ** — fold engine là pure function Python, test được bằng pytest, không phụ thuộc gì; (3) **lệch khỏi danh sách gợi ý của đề bài ở hai chỗ, có lý do**: bỏ Neo4j (đồ thị citation ở quy mô vài nghìn node là một bảng `edge` + recursive CTE; Neo4j là chi phí ops đổi lấy zero điểm khác biệt — visualization vẽ từ bảng edge bằng cytoscape.js), bỏ PhoBERT (không phải model sentence-embedding, giới hạn 256 token — dùng multilingual-e5 hoặc BGE-M3).

## 1. Stack chốt

| Lớp | Chọn | Ghi chú |
|---|---|---|
| DB duy nhất | **Postgres 16 + pgvector** | nodes, ops, edges, snapshots, conflicts, coverage — tất cả một chỗ; HNSW index cho dense |
| BM25 | **rank_bm25 in-process** (hoặc tantivy nếu muốn) | corpus vài nghìn node — rebuild index từ snapshot trong <1s mỗi lần ingest; tokenize bằng **pyvi/underthesea**, bảo vệ số hiệu (`39/2016/TT-NHNN`) thành 1 token bằng regex trước khi tách từ |
| Embedding | **multilingual-e5-base** (nhớ prefix `query:`/`passage:`) hoặc **BGE-M3** (8k context, dense+sparse) | chạy local bằng sentence-transformers, không cần GPU với corpus này; **chốt model trước khi chốt DDL** — e5-base 768 chiều, BGE-M3 1024, cột `embedding` phải khớp |
| LLM | GPT-4o / Claude Sonnet qua API, **temperature 0 + JSON schema mode** cho extraction | ~vài trăm call extraction + 1–2 call/câu hỏi — chi phí không đáng kể; production của bank thì thay bằng model self-host (Qwen 72B), kiến trúc không đổi |
| API | **FastAPI + Pydantic** | Pydantic model map 1:1 với 6 đối tượng dữ liệu của thiết kế |
| UI | **Streamlit × 2 app** (chatbot + admin console) | |
| Parse file | python-docx, PyMuPDF; **ưu tiên bản HTML/DOCX** từ TVPL/cổng CP, né OCR ở MVP | |
| Deploy | docker-compose: `postgres` + `api` + `ui` | chạy được trên 1 laptop |

## 2. Schema — 12 bảng lõi (DDL rút gọn, đủ để code ngay)

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
  path TEXT,                   -- 'dieu:8/khoan:2/diem:a/tiet:iii' | 'phuluc:04' (địa chỉ bề mặt
                               -- LÚC SINH; có tầng TIẾT ký hiệu hỗn hợp 'a(iii)', 'đ(i)';
                               -- Phụ lục là node hạng nhất — op nhắm được, MVP lưu dạng blob)
  label TEXT, seq INT);

CREATE TABLE alias (           -- địa chỉ bề mặt -> node, có thời gian tính
  doc_no TEXT, path TEXT, node_id UUID,
  valid_from DATE, valid_to DATE);

CREATE TABLE op (              -- L2: toán tử, append-only
  id UUID PRIMARY KEY,
  kind TEXT CHECK (kind IN ('amend','repeal','suspend','replace','insert','dinh_chinh','norm_decl')),
                               -- dinh_chinh: hiệu lực HỒI TỐ về đầu cửa sổ, khác amend;
                               -- norm_decl: khai sinh/kế vị/đổi-scope của Norm — cũng qua ratify queue;
                               -- thay-cụm-từ KHÔNG vào enum: ratify UI materialize thành amend/node
  source_artifact TEXT, source_quote TEXT,   -- span gốc để UI đối chiếu
  seq INT,                     -- thứ tự xuất hiện TRONG artifact (tie-break fold — TT28 Đ5 vs Đ6)
  target_node UUID,            -- XOR với target_op
  target_op UUID,              -- op nhắm op: bãi bỏ điều-khoản-sửa-đổi (TT08 Đ2.2, TT11 Đ59.2)
  target_norm UUID,            -- op 'norm_decl' nhắm Norm; 3 tiêu chí: đối tượng điều chỉnh,
                               -- phạm vi chủ thể, kế vị tuyên bố tường minh (ca khó: TT06 vừa
                               -- sửa norm cho-vay vừa KHAI SINH norm cho-vay-điện-tử)
  target_part TEXT DEFAULT 'body',           -- 'body'|'heading' — có op chỉ sửa TIÊU ĐỀ (TT11 Đ37, Đ49)
  new_text TEXT,
  valid_from DATE, valid_to DATE,            -- cửa sổ hiệu lực của op
  valid_to_event TEXT,                       -- kết thúc theo SỰ KIỆN chưa định danh — TT10:
                                             -- "đến ngày văn bản QPPL mới có hiệu lực"
  scope_predicate JSONB,                     -- grandfathering
  risk_class TEXT,             -- 'definitional' | 'prescriptive'
  extractor TEXT, confidence REAL,
  status TEXT DEFAULT 'proposed',            -- proposed|ratified|rejected|superseded
  ratified_by TEXT, ingested_at TIMESTAMPTZ,
  prev_hash TEXT, hash TEXT);                -- hash-chain (rẻ, cắt được)

CREATE TABLE edge (            -- citation có kiểu, DẪN XUẤT THEO node_version
  src UUID, src_version INT,   -- text đổi → citation đổi; edge treo trên node trần sẽ stale
                               -- và blast-radius sẽ bắn notice sai
  dst UUID,                    -- node đích, HOẶC một trong hai đích dưới:
  norm_id UUID,                -- Norm-by-topic: "theo quy định của NHNN về cho vay…" (TT32 Đ3
                               -- — không số hiệu nhưng TT39 đổi thì TT32 phải nhận blast-radius)
  frontier_ref TEXT,           -- ngoài kho: Basel, điều ước
  kind TEXT CHECK (kind IN ('dinh_nghia','tham_quyen','ngoai_le','chu_de','frontier')));

CREATE TABLE norm (            -- danh tính xuyên thay-thế-toàn-văn-bản (VISION §2);
  id UUID,                     -- một hàng mỗi hiện thân, cùng id xuyên chuỗi kế vị
  topic TEXT,                  -- 'quy chế cho vay', 'cho vay đầu tư ra nước ngoài'…
  artifact_id TEXT REFERENCES artifact,
  valid_from DATE, valid_to DATE,
  correlation JSONB);          -- tương chiếu điều cũ↔mới khi kế vị — nhãn NON-BINDING

CREATE TABLE node_version (    -- L3: SNAPSHOT đã materialize (cái được index!)
  node_id UUID, version INT,
  heading TEXT, text TEXT,     -- tách tiêu đề/thân: op nhắm được riêng tiêu đề
  status TEXT,                 -- active|suspended|repealed
  valid_from DATE, valid_to DATE,
  scope_predicate JSONB, scope_hash TEXT,    -- khóa logic (node_id, interval, scope_hash, K):
                                             -- chiều s KHÔNG biến mất — hai version cùng interval
                                             -- khác scope song song tồn tại (grandfathering)
  provenance UUID[],           -- chuỗi op tạo ra version này
  computed_under TIMESTAMPTZ,  -- K-cutoff của lần fold
  embedding vector(768));      -- dim khớp model đã chốt (e5=768, BGE-M3=1024)

CREATE TABLE conflict (
  id UUID PRIMARY KEY, member_versions JSONB, reason TEXT,
  tier INT,                    -- 2=residual fold, 3=SEM
  label TEXT CHECK (label IN ('mau_thuan','chat_hon_ve_minh','chat_hon_ve_doi_tac','khac_pham_vi')),
                               -- miễn trừ Liskov: 'chat_hon_ve_minh' (siết nghĩa vụ CỦA ngân hàng)
                               -- = tuân thủ, tự loại khỏi queue — thiếu nhãn này kênh 3c ngập
                               -- false positive; 'chat_hon_ve_doi_tac' (siết yêu cầu VỚI khách)
                               -- = nghi vấn — siết precondition có thể phạm nghĩa vụ luật định
  status TEXT DEFAULT 'open', resolved_by_op UUID);

CREATE TABLE notification (    -- blast-radius / trigger notice
  op_id UUID, affected_doc TEXT, owner TEXT,
  severity TEXT DEFAULT 'advisory',          -- 'interruptive' (bắt ack — NGOẠI LỆ HIẾM) | 'advisory'
                                             -- (digest); blast-radius phẳng của omnibus = bão ack →
                                             -- mù học được (50.59 là graded screening, không ack phẳng)
  acked BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ);

CREATE TABLE coverage (        -- freshness certificate lấy từ đây
  channel TEXT, last_seq TEXT, last_checked TIMESTAMPTZ);

CREATE TABLE pending_event (   -- registry chờ-sự-kiện: mọi thứ "đợi văn bản tương lai"
  id UUID PRIMARY KEY,
  kind TEXT CHECK (kind IN ('open_suspension','open_conflict')),
  ref UUID,                    -- op có valid_to_event (TT10) hoặc conflict chờ statement giải
  predicate TEXT,              -- "văn bản QPPL mới quy định về các vấn đề này"
  status TEXT DEFAULT 'open', closed_by_op UUID);
-- Nửa còn lại của valid_to_event: mỗi lần ingest re-evaluate mọi hàng 'open' → ứng viên khớp
-- phát ĐỀ XUẤT ĐÓNG vào ratify queue ("văn bản X có phải sự kiện đang chờ?" là phán đoán
-- ngữ nghĩa — người chốt, máy không tự đóng). Thiếu bảng này TT10 nạp đúng nhưng không bao
-- giờ ĐÓNG được; NQ 01/2019 giải cặp Đ468–TT39 cũng đi đường này.

CREATE TABLE precedence (doc_type TEXT, issuer TEXT, rank INT,
  source_node UUID,            -- quy tắc ưu tiên cũng là statement CÓ NGUỒN trong kho
  valid_from DATE, valid_to DATE);
-- Đ156 Luật BHVBQPPL: "sau thắng" CHỈ khi cùng cơ quan ban hành. "Chuyên ngành thắng"
-- không phải quy tắc phổ quát — encode như điều khoản tự khẳng định của từng luật;
-- Đ468 BLDS vs TT39 phải chờ NQ 01/2019 = bằng chứng nó thuộc tier-2, không phải tier-1.
```

Truy vấn tritemporal rẻ đến mức này: *"luật tại t như ta biết ở K"* = fold chỉ những op có `status='ratified' AND ingested_at <= K`, rồi chọn version có `valid_from <= t < valid_to`. Một mệnh đề WHERE — đó là toàn bộ phép màu.

## 3. Pipeline ingest — cụ thể từng bước

**3.1 Parser cây (thuần regex, KHÔNG dùng LLM — cấu trúc là deterministic).** Chuẩn hóa trước: NFC (văn bản VN trộn NFC/NFD — gotcha thật), vá khoảng trắng trong số hiệu (`32 /2026/TT- NHNN` → `32/2026/TT-NHNN` — có thật trong bản gốc), gộp header hai cột vỡ dòng. State machine trên các mẫu: `^Chương [IVXLC]+`, `^Mục \d`, `^Điều \d+[a-z]?\.`, `^\d+[a-z]?\.` (khoản), `^[a-zđ]\)` (điểm), `^\(?[ivx]+\)` và dạng hỗn hợp `a(iii)`, `đ(i)` (tiết — TT11 dùng dày đặc), `^Phụ lục` (node hạng nhất, addressable — TT11 có op "bổ sung một đoạn vào cuối Phụ lục 04"). Mỗi node tách **heading/thân**: điều có tiêu đề ("Điều 2. Điều khoản thi hành") lẫn không ("Điều 1."), và có điều MỘT DÒNG mà toàn bộ op nằm trong heading ("Điều 21. Bãi bỏ khoản 6 Điều 22."). Text được quote trong văn bản sửa đổi bọc `“…”.` — strip ngoặc và dấu chấm sau ngoặc đóng. Trích ngày: `ngày (\d+) tháng (\d+) năm (\d+)`; ngày hiệu lực từ điều "Hiệu lực thi hành". Exit test: đếm điều/khoản/điểm/tiết của từng văn bản demo khớp tay 100% — parser sai thì mọi thứ sau vô nghĩa.

**3.2 Citation.** Ba tầng: (a) regex bắt định danh tuyệt đối (`(Điều|khoản|điểm)\s+[\w,\s]+\s+(của\s+)?(Thông tư|Nghị định|Luật|Quyết định)\s+(số\s+)?[\d\w/–-]+`), expand enumeration ("các điểm a, b, c và đ khoản 1 Điều 39" → 4 edge); (b) đoạn `^Căn cứ` → edge `tham_quyen` MIỄN PHÍ bằng regex, khỏi tốn LLM; căn cứ dạng "Luật X được sửa đổi bởi Luật Y" trỏ vào **Norm**, không phải artifact; (c) LLM resolve tham chiếu tương đối và **gán kiểu** edge còn lại — prompt đưa câu chứa citation + nhãn + ví dụ. **Quy tắc binding bắt buộc trong prompt**: "Thông tư này/Điều này" nằm TRONG text được quote → bind vào văn bản ĐÍCH (Điều 7a mới của TT09/2019 nói "Thông tư này" là TT09, không phải thông tư sửa đổi); nằm NGOÀI quote → bind vào văn bản sửa đổi. Với omnibus (TT11: một thông tư sửa 13 thông tư, chia theo Chương), resolver mang **context-stack theo Chương** — "Điều 9" là Điều 9 của thông tư nêu ở tiêu đề chương hiện hành; heuristic carry-từ-tiêu-đề-văn-bản là không đủ. Alias phủ cả cấp luật: cùng một luật được cite bằng số ("46/2010/QH12") lẫn bằng ngày ("ngày 16/6/2010").

**3.3 Op extraction (tim của hệ).** Tầng rule bắt động từ hiệu lực: `sửa đổi, bổ sung|bãi bỏ|thay thế|ngưng hiệu lực|hết hiệu lực thi hành|thay thế cụm từ|bổ sung cụm từ|đính chính` — quét trên MỌI node, kể cả điều "Điều khoản thi hành" (op rất hay nấp ở đó: TT08 Đ2.2, TT32 Đ13.2, TT11 Đ59). Tầng LLM nhận đoạn văn bản sửa đổi, trả JSON theo schema `op` (kind, target dạng địa chỉ bề mặt, new_text, valid_from), kèm `source_quote` bắt buộc; few-shot phải có ví dụ TÁCH ENUMERATION ("khoản 8, khoản 9 và khoản 10" → 3 op riêng). Op **thay-cụm-từ** không vào enum: curator materialize thành các op `amend` node-level với full text mới tại ratify UI (một op cụm từ chạm được hàng chục node). Resolver đổi địa chỉ bề mặt → `node_id` qua bảng alias; ngoặc đơn provenance trong chính văn bản ("đã được bổ sung theo khoản 2 Điều 1 TT06/2023") dùng làm **cross-validation**: chuỗi provenance của node resolve được phải chứa op tương ứng, lệch = trích sai. **Không có auto-ratify — máy không bao giờ tự mở cổng vào effective state** (đó là câu một auditor SBV sẽ khoanh đỏ). Thay bằng **hai hàng đợi, risk classifier làm router**: (a) op `definitional` (target có inbound edge `dinh_nghia`), op `norm_decl`, và mọi op có `valid_from` phụ thuộc phân loại chủ đề ("các quy định về Phiếu lý lịch tư pháp có hiệu lực từ 01/07/2026" — TT11 Đ59.3, phân loại ngữ nghĩa) → **per-op review** bắt buộc; (b) op cơ học thỏa cả bốn điều kiện — rule và LLM khớp nhau, target resolve duy nhất, `risk_class='prescriptive'`, `valid_from` đọc thẳng từ văn bản → **batch-ratify**: người phê chuẩn CẢ LỚP kèm invariant mẫu khai báo ("mọi diff chỉ là thay cụm từ X→Y", "chỉ đổi số ngày làm việc") mà máy verify từng op khớp pattern, cộng spot-check sampling — chữ ký người phủ 100% log, công sức tỷ lệ rủi ro. Ép per-op cho ~100 op cơ học của một omnibus thoái hóa thành rubber-stamp — TỆ HƠN sampling trung thực vì nó rửa output máy thành "đã người duyệt". UI hiển thị `source_quote` cạnh op đề xuất, approve/reject/edit, sort theo risk-class, diff view — throughput của queue này là đường găng, không phải trang sức.

**3.4 Fold (engine, ~150 dòng Python thuần).**

```python
def fold(node_id, K=None) -> list[Version] | ConflictCertificate:
    ops = ratified_ops(node_id, ingested_before=K)      # trục K
    # tie-break bằng dữ kiện CANONICAL trước ingested_at: TT06 và TT10 cùng valid_from
    # 01/09/2023, cùng rank — thứ tự nạp file không được quyết định kết quả; seq nội-artifact
    # vì TT28 Đ5 chèn khoản vào Điều 11 rồi Đ6 thay cụm từ "tại Điều 11" — áp theo thứ tự xuất hiện
    ops.sort(key=lambda o: (rank(o), o.valid_from, o.issued_date, o.seq, o.ingested_at))
    versions = [base_version(node_id)]
    for op in ops:
        if incomparable(op, applied_ops):     # chồng cửa sổ, precedence không phân định được
            return ConflictCertificate(...)   # tier-2: phát chứng chỉ, KHÔNG chọn bừa
        versions = apply(versions, op)
        # amend:      đóng version cũ tại valid_from, mở version mới
        # suspend:    chèn version status='suspended'; valid_to_event chưa xảy ra → treo VÔ THờI
        #             HẠN, chỉ hồi sinh khi có op mới đóng cửa sổ. TT10: 3 khoản của TT06 bị treo
        #             ĐÚNG ngày lẽ ra hiệu lực → version 'active' KHÔNG BAO GIỜ tồn tại
        # repeal:     đóng vĩnh viễn, không hồi sinh
        # repeal op (target_op): đóng hiệu lực op đó TỪ valid_from TRỞ ĐI — tuyệt đối không loại
        #             khỏi lịch sử. TT08 bãi bỏ kh.1 Đ1 TT26/2022: cửa sổ 2022–2026 nguyên vẹn,
        #             query tại 2024 vẫn trả text theo TT26 — xóa op = viết lại lịch sử
        # dinh_chinh: hồi tố về đầu cửa sổ của text bị đính chính, không phải từ ngày đính chính
    return versions                      # kèm provenance = op ids đã áp
```

Test bất biến quan trọng nhất (đây cũng là demo determinism): `fold_all_from_scratch() == incremental_state()` — chạy trong CI.

**3.5 Pending-event sweep (sau MỖI lần ingest).** Quét `pending_event` mở, so văn bản vừa nạp với `predicate` (rule + LLM đề xuất ứng viên), phát đề xuất đóng vào ratify queue; đóng = op mới được phê chuẩn → fold lại node liên quan, certificate được giải thì gắn `resolved_by_op`. Đây là nửa còn lại của `valid_to_event`: thiếu sweep, cửa sổ treo của TT10 đúng mãi mãi nhưng không bao giờ kết thúc được.

## 4. Retrieval + trả lời + verifier

```
câu hỏi → QUESTION COMPILER {topic, t (mặc định now), s (scope facts: ngày ký HĐ, loại chủ thể,
  đã sửa đổi HĐ chưa), audience} — JSON schema + few-shot từ câu hỏi nghiệp vụ thật
→ BM25 top-30 ∪ dense top-30 TRÊN node_version đang hiệu lực tại t   (lọc audience Ở TẦNG SQL)
→ RRF (k=60) → mở rộng 1-hop theo edge định_nghĩa/ngoại_lệ
→ context pack: mỗi node kèm header [id | doc | path | cửa sổ hiệu lực | trạng thái | tóm tắt chuỗi sửa đổi]
→ LLM soạn, bắt buộc đánh dấu [n] theo id
→ VERIFIER (code, không phải model): mọi [n] ∈ context; mọi đoạn trích khớp fuzzy ≥0.9
  với text snapshot; fail → regenerate 1 lần → fail nữa → Escalate
→ đóng gói Answer{content, provenance (trỏ tới trang/vị trí trong file gốc, không chỉ hash),
  freshness (đọc bảng coverage), ttl, audience} — customer kèm disclaimer thông-tin-không-phải-tư-vấn
```

Piecewise: nếu trong cửa sổ liên quan có ranh giới version hoặc `scope_predicate` — đưa **cả hai version vào context** với cửa sổ của chúng và ép LLM trả lời có điều kiện ("ký trước 01/09/2023: …; từ 01/09/2023: …"). Conflict tier 2/3 nếu retrieved set chạm bảng `conflict` → gắn certificate vào answer (employee) hoặc escalate (customer).

**Question compiler là phần không-commodity của L5** (generation mới là hàng chợ): lỗi demo nhìn thấy được mọc ở đây chứ không phải ở engine. Quy tắc cứng: retrieved set có ranh giới version hoặc `scope_predicate` mà câu hỏi không cho `s` → hoặc hỏi lại đúng MỘT câu ("hợp đồng ký trước hay sau 01/09/2023?"), hoặc trả piecewise — không bao giờ chọn thầm một nhánh. Harness có test riêng cho compiler: câu mờ, câu thiếu s, câu có s ẩn trong văn cảnh.

## 5. Cấu trúc repo & phân công

```
/corpus     văn bản gốc + fixtures đã parse tay (ground truth cho test); fixture synthetic
            dán nhãn synthetic:true; văn bản thật đối chiếu bản gốc Công báo trước khi tin
            (bản transcription trên mạng có artifact OCR)
/ingest     fetch, normalize, tree_parser.py, citation.py, op_extract.py
/engine     fold.py, snapshot.py, conflict.py, invariants/
/api        FastAPI: /ask /timeline/{node} /conflicts /ratify /graph
/ui         chat_app.py, admin_app.py (Streamlit)
/eval       naive_rag.py (baseline), benchmark.yaml, judge.py
```

Team 4 người: **P1** ingest (parser là nghề riêng — người kỹ tính nhất); **P2** engine + API; **P3** retrieval/answer/verifier; **P4** UI + eval + demo script — trong đó ratify/admin console làm TRƯỚC chat UI (một omnibus sinh ~100 op, throughput duyệt lô quyết định hệ sống hay chết với văn bản thật). P1, P2 và ratify UI là đường găng.

## 6. Kế hoạch phase (exit criteria quyết định khi nào sang phase sau)

| Phase | Việc | Exit criteria |
|---|---|---|
| 0 | compose up, fetch corpus demo | `docker compose up` chạy |
| 1 | tree parser + alias + dates | 100% corpus demo parse đúng (đối chiếu đếm tay) |
| 2 | citation + op extraction + **ratify UI** | TT06→TT39 sinh đủ op; TT10 sinh 3 op `suspend` với `valid_to_event`; TT08 sinh cặp amend + repeal-nhắm-op |
| 3 | fold + snapshot + as-of + timeline API | "Điều 8 TT39 tại 10/2023" trả đúng trạng thái treo; version `active` của khoản 8-10 KHÔNG tồn tại; timeline TT22 giữ nguyên cửa sổ 2022–2026 sau repeal-op; determinism test xanh KỂ CẢ khi đảo thứ tự nạp TT06/TT10 |
| 4 | hybrid retrieval + answer + verifier + freshness | câu hỏi lãi suất trả lời từ snapshot kèm phả hệ 39→06→10 |
| 5 | precedence + certificate + blast-radius + 2 invariant | cặp Đ468 BLDS vs TT39 ra certificate cite NQ01/2019; văn bản nội bộ stale bị bắt |
| 6 | baseline naive RAG + benchmark + polish demo | bảng số naive-vs-ours theo 5 loại câu hỏi |

**Corpus demo (~14 văn bản):** ca thật — TT 39/2016/TT-NHNN · TT 06/2023 · TT 10/2023 (suspend kết thúc theo sự kiện, target sinh bởi op khác) · BLDS 2015 (Điều 468) · NQ 01/2019/NQ-HĐTP · Luật Các TCTD 2024 (vài điều) · TT 41/2016 (frontier→Basel; phụ lục toàn công thức — node blob, KHÔNG hứa trả lời tính toán) · 2–3 văn bản nội bộ tự soạn: một quy trình cho vay cite TT39 (một bản **cố tình stale** để demo SEM catch), một mẫu hợp đồng có điều khoản chuyển tiếp. Fixture synthetic (dán nhãn, phủ nốt đại số op): **TT 08/2026** (amend điểm + repeal-nhắm-op — bẫy viết-lại-lịch-sử) · **TT 28/2026** (insert Điều 7a trôi alias, thay-cụm-từ, bẫy binding "Thông tư này") · **TT 32/2026** (replace toàn văn bản/Norm succession, grandfathering 2 tầng: ký-trước AND chưa-sửa-đổi, edge norm-by-topic ở Điều 3) · **TT 11/2026 omnibus** (context theo Chương, hiệu lực phân kỳ theo chủ đề, op nhắm heading/phụ lục, bãi bỏ op hàng loạt 5 thông tư). Còn thiếu duy nhất một ca **đính chính** — tự soạn nốt. Bản hợp nhất TT39 của NHNN (tra trên cổng NHNN/TVPL) dùng làm differential oracle: diff snapshot của engine với nó — lệch là bug hoặc là điểm khoe.

**Benchmark harness:** `benchmark.yaml` ~40 câu, mỗi câu gắn loại (`amended | suspended | point_in_time | grandfather | conflict | customer`) và **assertion kiểm bằng code** ("không được viện dẫn khoản 8 Điều 8 như đang hiệu lực", "phải nhắc TT10/2023") + LLM-judge phụ. Câu bắt buộc có: *"khoản 8 Điều 8 TT39 đã từng có hiệu lực ngày nào chưa?"* → chưa từng (treo đúng ngày lẽ ra hiệu lực); *"tháng 3/2024 tiền gửi KBNN tính vào LDR thế nào?"* → phải trả text theo TT26/2022, không được nói "đã bị bãi bỏ" (bẫy viết-lại-lịch-sử); *"hồ sơ tăng vốn nộp 15/4/2026 xử lý theo thời hạn nào?"* → piecewise theo ngày nộp (TT11 Đ59.4); *"yêu cầu Phiếu LLTP mới áp dụng từ ngày nào?"* → 01/07/2026, khác ngày hiệu lực chung của thông tư; 1–2 câu persona khách hàng. Baseline = cùng embedding, chunk 500 token trên văn bản thô, không engine — ~100 dòng. Bảng kết quả theo loại chính là slide ăn điểm nhất.

## 7. Gotchas cụ thể (trả học phí trước)

Unicode NFC/NFD trộn lẫn — normalize ngay cửa vào. Số hiệu văn bản phải thành token nguyên vẹn trước khi word-segment, nếu không BM25 mù — và số hiệu có thể chứa khoảng trắng ngay trong bản gốc (`32 /2026/TT- NHNN`). `ngưng hiệu lực` ≠ `bãi bỏ` — hai op kind khác nhau, đừng để LLM gộp (đưa cả hai vào few-shot với TT10 làm ví dụ). Ngày hiệu lực ≠ ngày ban hành — TT06 ban hành 6/2023, hiệu lực 01/09/2023, và TT10 treo khoản *trước khi nó kịp có hiệu lực* — nếu schema không tách hai trục ngay từ đầu, ca này không biểu diễn nổi. `valid_to` của suspension có thể là SỰ KIỆN chứ không phải ngày (TT10: "đến ngày văn bản QPPL mới có hiệu lực") — thiếu `valid_to_event` là không biểu diễn nổi ca demo trung tâm. Bãi bỏ một op ≠ xóa op khỏi lịch sử — cửa sổ đã hiệu lực phải nguyên vẹn. Hai op cùng `valid_from` cùng rank là chuyện thường (TT06+TT10 cùng 01/09/2023) — tie-break bằng dữ kiện canonical (issued_date, seq), không phải thứ tự nạp. "Thông tư này" trong text được quote bind vào văn bản đích, ngoài quote bind vào văn bản sửa đổi. Omnibus đổi namespace target theo Chương. Hiệu lực có thể phân kỳ THEO CHỦ ĐỀ trong cùng một văn bản (TT11 Đ59.3) — không regex nổi, phải qua curator. Op có thể chỉ sửa TIÊU ĐỀ của node, hoặc nhắm Phụ lục. Đừng chunk theo token — node cây *là* chunk; một điều quá dài thì context pack lấy khoản liên quan + header của điều. Nội quy CHẶT HƠN thông tư không phải mâu thuẫn (miễn trừ Liskov) — nhưng phải hỏi chặt hơn VỚI AI: siết nghĩa vụ của mình = tuân thủ, siết yêu cầu với khách = nghi vấn.

## 8. Thang de-scope (cắt từ trên xuống khi cháy giờ)

hash-chain → reranker → TTL-đo-động-học (để TTL config tĩnh) → LLM pair-proposer tier-3c (giữ blast-radius 3a + invariant 3b) → graph viz đẹp (giữ bảng). **Không bao giờ cắt:** parser đúng, ratification gate (kể cả duyệt THEO LÔ — omnibus ~100 op là ca thường, không phải ca biên), fold + as-of, verifier, benchmark. Bốn thứ đó *là* sản phẩm; mọi thứ khác là trang sức. Và ghi một dòng vào slide production-path để trả lời ban giám khảo: self-host LLM cho dữ liệu nội bộ, SSO/RBAC thay role-switch, và diễn tập rebuild materialized view từ log — vì bài học FAA tháng 1/2023: view sập trong khi log còn nguyên vẫn đủ để ground toàn bộ không phận một ngày.