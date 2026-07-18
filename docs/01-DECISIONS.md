# 01-DECISIONS — Sổ quyết định đã khóa

> File này sở hữu: mọi quyết định thiết kế đã chốt + lý do + phương án đã loại. AI session mới KHÔNG mở lại các quyết định này trừ khi user yêu cầu tường minh.
> Chi tiết normative của từng quyết định nằm ở 02 (domain) và 03 (system); file này là hiến pháp.

Quy ước ID toàn bộ tài liệu: `D-n` quyết định · `R-n` requirement (03) · `INV-n` invariant (03) · `FR-n` UI (03) · golden item theo class (04) · `PB-n` probe phản biện (05).

## A. Kiến trúc lõi

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-01 | Nghịch đảo log/view: văn bản thô là log; index và trích dẫn CHỈ trên snapshot hiệu lực do engine tính ra | Mọi failure của RAG thường (stale, supersession, miss ref) là một triệu chứng của một nguyên nhân: retrieve trên dòng delta | Retrieval trên văn bản thô + rerank/filter hậu kỳ |
| D-02 | Ba trục thời gian tách từ schema: ban hành / hiệu lực (cửa sổ, có thể tương lai hoặc hồi tố) / biết-đến K (`ingested_at`). Query chuẩn: `V(t, s | K)` | Trục K là câu thanh tra hỏi ("lúc giải ngân ngân hàng có thể biết gì"); TT06 ban hành 6/2023 hiệu lực 9/2023 mà TT10 treo trước khi kịp hiệu lực — thiếu trục là không biểu diễn nổi | Bitemporal 2 trục (gộp ban hành vào hiệu lực) |
| D-03 | LLM chỉ ở hai biên (extract lúc nạp, soạn văn lúc trả lời), cả hai bị gate bởi tầng hình thức. Máy KHÔNG BAO GIỜ tự mở cổng vào effective state | Auto-ratify là câu một auditor SBV khoanh đỏ; determinism của engine chỉ có giá trị khi input đã được người phê chuẩn | Auto-ratify theo ngưỡng confidence; agent tự do |
| D-04 | Chiều scope (lớp chủ thể) nằm TRONG khóa của snapshot; trả lời piecewise là mặc định khi thiếu dữ kiện cohort — không bao giờ chọn thầm một nhánh | Grandfathering = hai phiên bản cùng hiệu lực song song cho hai cohort; filter "chỉ bản mới nhất" sẽ loại mất text đang govern cohort cũ | Cohort xử lý ở tầng session/prompt; single-track version |
| D-05 | Node có role `amending` (điều khoản sửa đổi chứa text quote) bị LOẠI khỏi retrieval — nội dung của nó chỉ sống qua op đã phê chuẩn | Bẫy contamination: text bị treo sống nguyên văn trong điều khoản sửa đổi đang-hiệu-lực → mọi metric leak đọc 0 trong khi leak thật chảy. Đây là lỗ giết cả hệ có versioning | Chỉ probe INV trên node đích; xử lý bằng rerank |
| D-06 | Ba từ chối (không oracle SEM, không diễn giải kiến tạo → Escalate, không hứa freshness với thế giới → chỉ coverage attestation) là contract sản phẩm | Hứa quá thẩm quyền = chết trong phòng thanh tra; escalation là ranh giới thông-tin/tư-vấn | Confidence score cho vùng diễn giải; "always answer" |

## B. Mô hình dữ liệu

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-07 | Node nhận birth-id UUID cấp lúc sinh, không bao giờ tái sử dụng; địa chỉ bề mặt ("khoản 2 Điều 8 TT39") sống trong bảng alias CÓ THỜI GIAN TÍNH | Insert Điều 7a làm trôi số thứ tự; identifier chết không tái sinh (quy ước CRDT) | unit_key vị trí làm identity (conflate vị trí với danh tính) |
| D-08 | Replace cấp cha (thay toàn bộ một Điều có tái cấu trúc con): đóng mọi version con, sinh node con MỚI với birth-id mới; bảng tương chiếu cũ↔mới lưu nhãn **non-binding** | Điểm c cũ ≠ điểm c mới về danh tính; tương chiếu 1-nhiều buộc dẫn xuất lại từ văn bản mới để lỗi bảng không lan vào "luật" | Reuse key vị trí cho con; correlation binding |
| D-09 | Norm = danh tính xuyên thay-thế-toàn-văn-bản (TT39 kế vị QĐ 1627 với tư cách "quy chế cho vay"), là cạnh được BẢO TRÌ qua op `norm_decl` đi đường ratify | Citation theo mảng không số hiệu ("theo quy định của NHNN về cho vay") phải có đích để blast-radius thấy; thiếu nó → song đề abstain-mãi hoặc mù-im-lặng | Suy luận succession tự động; ref bắt buộc trỏ unit |
| D-10 | Op nhắm được op (`target_op`): bãi bỏ một op chỉ ĐÓNG hiệu lực từ đó trở đi, cửa sổ đã qua bất khả xâm phạm; `close_window` đóng cửa sổ treo-theo-sự-kiện. `source_node` giữ cho provenance | Xóa op = viết lại lịch sử → query point-in-time sai; compensating-effect thủ công thì người làm việc của engine + provenance sai kiểu thao tác pháp lý | Compensating effect do curator tự dựng text |
| D-11 | `valid_to` của op có thể là SỰ KIỆN chưa định danh (`valid_to_event`) + bảng `pending_event` + sweep sau MỖI lần ingest đề xuất đóng (người chốt) | TT10: "đến ngày văn bản QPPL mới có hiệu lực" — thiếu registry thì nạp đúng nhưng không bao giờ ĐÓNG được → stale ngược, im lặng | Trông chờ curator nhớ; date placeholder |
| D-12 | `dinh_chinh` là op kind riêng, hồi tố về ĐẦU cửa sổ của text bị đính chính | Khác amend (hiệu lực từ ngày op); extractor cần từ vựng để emit nó | Gộp vào amend; retract-append backdate không tên |
| D-13 | Edge citation có kiểu (`dinh_nghia|tham_quyen|ngoai_le|chu_de|chuyen_tiep|frontier`), dẫn xuất theo PHIÊN BẢN node; `chu_de` trỏ Norm, `frontier` trỏ ngoài kho (Basel) | Kiểu edge là input của risk classifier và closure; edge treo trên node trần sẽ stale và blast-radius bắn sai | Edge không kiểu; edge trên node bất biến |
| D-14 | Blanket derogation = op kind targetless, KHÔNG mutate state; seed conflict screening scoped theo chủ đề văn bản mới | Về pháp lý nó declaratory của lex posterior (Đ156 đã encode ở precedence); giá trị thật là tín hiệu ưu tiên dò mâu thuẫn | Bỏ qua; hoặc cố compile thành delta có địa chỉ |
| D-15 | Precedence là statement CÓ NGUỒN trong kho với cửa sổ hiệu lực riêng (Luật BHVBQPPL tự nó từng được thay thế) | "Sau thắng" CHỈ khi cùng cơ quan (Đ156); "chuyên ngành thắng" KHÔNG phổ quát — Đ468 vs TT39 phải chờ NQ01/2019 là bằng chứng nó thuộc tier-2 | Hardcode bảng ưu tiên; luật chuyên ngành auto-win |

## C. Ingest — extraction — phê chuẩn

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-16 | Parser cây là regex state machine thuần (grammar theo ND 34/2016, đủ tầng Tiết `a(iii)` và Phụ lục là node hạng nhất), KHÔNG dùng LLM cho cấu trúc; exit test: đếm điều/khoản/điểm khớp tay 100% trên corpus demo | Cấu trúc là deterministic và được luật hóa; parser sai thì mọi thứ sau vô nghĩa | LLM parse cấu trúc; chunk theo token |
| D-17 | Chunk = node cây (điều/khoản/điểm), không chunk theo token; điều quá dài → context pack lấy khoản liên quan + header | Op nhắm node; citation ghim node; token-chunk phá địa chỉ pháp lý | Sliding window 500 token |
| D-18 | Op extraction 2 tầng: rule bắt động từ hiệu lực trên MỌI node (kể cả "Điều khoản thi hành") + LLM JSON-schema với `source_quote` bắt buộc, few-shot có tách enumeration, phân biệt `ngưng hiệu lực` ≠ `bãi bỏ`, quy tắc binding "Thông tư này" trong/ngoài quote, context-stack theo Chương cho omnibus | Ngôn ngữ sửa đổi tiếng Việt gần công thức → precision cao; op hay nấp ở điều thi hành; các bẫy đã trả học phí (02 §7) | Extraction một tầng LLM tự do |
| D-19 | Hai hàng đợi phê chuẩn, risk classifier làm router: op `definitional`/`norm_decl`/ngày-hiệu-lực-theo-phân-loại-ngữ-nghĩa → per-op review; op cơ học (rule↔LLM khớp, target resolve duy nhất, prescriptive, ngày đọc thẳng) → **batch-ratify**: người duyệt CẢ LỚP kèm invariant mẫu máy verify từng op + spot-check ≥10%. Chữ ký người phủ 100% log | Omnibus sinh ~100 op: ép per-op thoái hóa thành rubber-stamp — TỆ HƠN sampling trung thực vì nó rửa output máy thành "đã người duyệt" | Auto-ratify; per-op cứng cho mọi op |
| D-20 | Op đã phê chuẩn là BẤT BIẾN; sửa lỗi trích xuất = op mới đè lên (append-only, superseded) | Chính lịch sử trích xuất cũng phải audit được | Edit op in-place |
| D-21 | Thay-cụm-từ KHÔNG vào enum op: curator materialize thành các op amend node-level tại ratify UI | Một op cụm từ chạm hàng chục node — phải thấy từng diff | phrase_replace op tự động apply |
| D-22 | Differential oracle: engine tự materialize rồi diff với VBHN (không chính thức) của nhà nước/TVPL; lệch → hàng đợi phân xử. Oracle là chuông báo, KHÔNG phải chân lý | Các bản hợp nhất độc lập sai TƯƠNG QUAN ở ca khó (Knight–Leveson) | Coi VBHN là ground truth; bỏ oracle |

## D. Engine

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-23 | Fold là pure function Python (~200 dòng), sort key canonical: `(precedence_rank, valid_from, issued_date, seq_in_artifact, artifact_id, ingested_at)`; determinism test CI gồm HOÁN VỊ thứ tự nạp | TT06+TT10 cùng hiệu lực 01/09/2023 cùng hạng — thứ tự nạp file không được quyết định luật | Sort theo ingested_at; engine trong DB trigger |
| D-24 | Suspend ≠ delete: node treo sống với status `suspended`; treo theo sự kiện chưa xảy ra → treo vô thời hạn, version `active` có thể KHÔNG BAO GIỜ tồn tại (khoản 8–10 Đ8 TT39) | Ngưng hiệu lực cho phép hồi sinh; "đã từng hiệu lực chưa?" phải trả lời được từ timeline | Suspend = đóng cửa sổ như repeal |
| D-25 | Applicability DSL ĐÓNG, v1: `{contract_signed_before: date} ∧ {not_amended_on_or_after: date} ∧ {entity_class: enum}`; không predicate form nào khác hợp lệ | DSL đóng = hard-to-vary, match được điều khoản chuyển tiếp thật của TT06 (ký-trước AND chưa-sửa-đổi); JSONB mở là nơi silent wrongness sinh sôi | JSONB tự do; predicate ngôn ngữ tự nhiên |

## E. Answering

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-26 | Question compiler là phần không-commodity: câu hỏi → `{topic, t, s, K, audience, mode}`; phát hiện câu-trả-lời-phụ-thuộc-s; thiếu s mà nhánh phân kỳ → hỏi lại đúng MỘT câu (employee) hoặc trả piecewise; customer → piecewise bảo thủ hoặc escalate | Lỗi demo nhìn thấy được mọc ở đây, không phải ở engine; generation là hàng chợ | Đoán thầm nhánh; hỏi nhiều câu |
| D-27 | Retrieval = một predicate SQL duy nhất: `retrievable ∧ status='active' ∧ hiệu lực tại t ∧ scope khớp ∧ audience` — lọc audience Ở TẦNG SQL qua query-builder một cửa; câu hỏi pinpoint-address/lịch sử đi đường alias→timeline (thấy được cả version treo/đã đóng) | Text bị thay không được ở TRONG candidate set; nhưng câu hỏi về lịch sử/trạng thái treo phải trả lời được — hai đường khác nhau | Filter ở application sau retrieve; một đường duy nhất |
| D-28 | Hybrid: BM25 in-process (tokenize pyvi, số hiệu văn bản bảo vệ thành 1 token bằng regex TRƯỚC khi tách từ) ⊕ dense BGE-M3 `vector(1024)` ⊕ RRF k=60 → mở rộng closure theo edge | Số hiệu chứa khoảng trắng ngay trong bản gốc; BM25 mù nếu không segment; chốt model trước DDL vì dimension | PhoBERT (không phải sentence embedder, 256 token); OpenSearch (ops thừa ở quy mô này) |
| D-29 | Closure có completeness gate: mandatory = `ngoai_le` (luôn, 2 chiều) + `chuyen_tiep` khớp cohort + `dinh_nghia` cho term có mặt; depth ≤2 có budget; mandatory edge unresolved (confidence 0) bị chạm → Tier D `closure_incomplete`. Edge `chu_de`(Norm) nuôi blast-radius, KHÔNG gate closure | Trả lời nêu quy tắc mà thiếu ngoại lệ là failure đắt thứ nhì sau staleness; ref theo mảng đã có đích Norm nên không còn song đề abstain-mãi/mù-im-lặng | Closure 1-hop không gate; mọi ref đều gate |
| D-30 | Verifier HAI tầng: (cứng, code, luôn bật) mọi trích dẫn ∈ context + quote khớp fuzzy ≥0.9 với snapshot + con số khớp exact → fail → regenerate 1 lần → fail → Tier C; (mềm, LLM judge KHÁC HỌ MODEL với composer, context cô lập chỉ {claim, cited texts}) entailment từng claim → fail/chưa-κ → flag, cap Tier B | Cổng phải sound (code); phần thiếu của cổng cứng (câu nối sai giữa hai quote đúng) bù bằng tầng mềm; cùng họ model = tương quan lỗi tối đa | Chỉ entailment LLM (model gác model); chỉ verbatim |
| D-31 | Thang tier total: `¬retrieval_floor ∨ ngoài coverage → D` · `¬hard_pass → C (sources-only, chỉ trích dẫn ghim)` · `hard_pass ∧ (flags≠∅ ∨ judge chưa κ≥0.8 ∨ judge off) → B + banner` · còn lại → A. KHÔNG code path nào render văn tổng hợp khi ¬hard_pass | Floor phải là C chứ không phải B khi không kiểm chứng được; nhưng gate cứng không bao giờ tắt nên B-có-banner khi judge off là hợp lệ (văn vẫn verbatim-grounded) | "Disable verifier ⇒ cap B" khi verifier duy nhất là LLM (mâu thuẫn INV) |
| D-32 | Freshness = coverage attestation theo kênh (bảng coverage, dò gap số Công báo) + pin `run_id`; TTL v1 là config tĩnh theo mảng (hook đo động học để sau) | "Trả lời theo trạng thái ngày D" là lời khẳng định; attestation theo kênh là chứng thực kiểm được | Hứa freshness tuyệt đối; TTL đo động học ngay v1 |

## F. Conflict & SEM

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-33 | Ba tầng ba lời hứa: T1 tự động CHỈ quy tắc đã luật hóa (cấp trên thắng; sau thắng cùng cơ quan); T2 certificate kiểu unsat-core, tồn tại đến khi có statement giải (`resolved_by_op`, đi qua pending_event); T3 SEM = chương trình 4 kênh, không oracle | Ranh giới T1/T2 có bằng chứng doctrinal: Đ468 vs TT39 chờ NQ01/2019; hệ không tự phân xử vùng của thẩm quyền | Auto-resolve bằng doctrine; chỉ surface không tier |
| D-34 | Nhãn conflict 4 loại + hướng: `chat_hon_ve_minh` (siết nghĩa vụ CỦA ngân hàng) = tuân thủ, TỰ LOẠI khỏi queue; `chat_hon_ve_doi_tac` (siết yêu cầu VỚI khách) = nghi vấn | Miễn trừ Liskov có hướng — thiếu nó kênh pair-proposer ngập false positive "nội quy nghiêm hơn thông tư" và chôn curator | Mọi khác biệt đều là candidate |
| D-35 | Ownership fork trên certificate/notice: nội↔nội → defect ticket cho phòng sở hữu; nội↔ngoại → compliance-gap escalation; ngoại↔ngoại → surface kèm doctrine; frontier/Basel → advisory | Biến xung đột từ nhìn-thấy-được thành làm-được | Một hàng đợi chung không route |
| D-36 | Blast-radius qua where-used (index bảo trì liên tục) → notice cho CHỦ CÓ TÊN, severity phân tầng: `interruptive` bắt-ack là NGOẠI LỆ HIẾM (op definitional), còn lại `advisory` digest. Forms/biểu mẫu nhận staleness propagation như mọi tài liệu | Blast-radius phẳng của omnibus = bão ack → mù học được (đúng cái chết NOTAM; 50.59 là graded screening) | Ack phẳng mọi notice; tính where-used on-demand |
| D-37 | Kênh SEM: (a) blast-radius; (b) invariant THỰC THI ĐƯỢC do compliance viết, chạy trên effective state sau mỗi lần nạp; (c) LLM pair-proposer offline gán nhãn D-34 trước khi vào queue người; (d) nút "nghi đã cũ" trên mỗi câu trả lời | (b) là máy dò công nghiệp duy nhất từng hoạt động; (d) thiếu kênh downvote thì văn bản chết trôi nổi | Hứa dò SEM tự động đầy đủ |

## G. Stack (ops-tối-thiểu — team hackathon chết vì ops, không chết vì thiếu framework)

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-38 | MỘT Postgres 16 + pgvector (HNSW) cho tất cả: nodes, ops, edges, snapshots, conflicts, coverage, answer_log | Bốn filter (similarity, validity, scope, audience) compose trong một query; zero sync giữa store | Neo4j (đồ thị vài nghìn node = bảng edge + recursive CTE; ops đổi lấy zero điểm khác biệt); OpenSearch; Redis/queue |
| D-39 | BM25 in-process (`rank_bm25`), rebuild từ snapshot <1s mỗi lần ingest; tokenize `pyvi`/`underthesea` | Corpus vài nghìn node; một dependency Python thay một cluster | Elastic/OpenSearch |
| D-40 | Embedding BGE-M3 (1024d, chạy local sentence-transformers, không cần GPU với corpus này) | 8k context, mạnh tiếng Việt; PhoBERT bị loại có lý do (D-28) | multilingual-e5-base (768d — đổi thì phải đổi DDL) |
| D-41 | LLM qua MỘT gateway module (OpenAI-compatible / Anthropic / vLLM on-prem là config): composer+extractor một họ, judge KHÁC HỌ; temperature 0 + JSON schema mode cho extraction. Production: self-host Qwen-72B, kiến trúc không đổi | Data-residency của bank; đổi provider không đổi kiến trúc | Gọi SDK rải rác; judge cùng model |
| D-42 | FastAPI + Pydantic (model map 1:1 với đối tượng dữ liệu); UI Streamlit ×2 (chat + admin console); graph render pyvis, fallback bảng; docker-compose `postgres+api+ui` chạy 1 laptop | Pydantic schema kiêm LLM output contract; Streamlit đủ cho 8 demo beats | Next.js đa surface; K8s cho hackathon |
| D-43 | Parse file: ưu tiên HTML/DOCX từ TVPL/cổng CP; NÉ OCR ở MVP; văn bản thật đối chiếu bản gốc Công báo trước khi tin | Bản transcription trên mạng có artifact OCR | VietOCR pipeline ngay v1 |
| D-44 | RLS-lite: audience filter ép trong query-builder MỘT CỬA + adversarial test (customer token không thể moi text internal); Postgres RLS policy là flag production | Đủ chứng minh trong demo, không nợ kiến trúc | Filter rải rác ở từng endpoint |

## H. Eval & vận hành chất lượng

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-45 | Golden set có class ĐỐI KHÁNG TỰ HƯỚNG: `op_on_op` (bẫy viết-lại-lịch-sử), `contamination` (điều-khoản-sửa-đổi), `grandfather` piecewise, `abstain` — cộng CI gates release-blocking, `supersession_leak = 0` là gate CỨNG (đo cả cite vào node amending) | Bộ test phải được viết bởi vốn từ toán tử đầy đủ + probe tự hướng; metric mù thì suite phải bắt bằng behavioral assertion | Chỉ test happy-path 4 loại đề bài nêu |
| D-46 | Baseline naive RAG bắt buộc: cùng LLM, cùng embedding, chunk 500 token trên văn bản thô, ~100 dòng; báo cáo side-by-side THEO CLASS | "So với RAG thường" là deliverable; bảng theo class là money slide | Baseline yếu hơn về model (so sánh không trung thực) |
| D-47 | Substrate QA: determinism (fold-from-scratch == incremental, kể cả hoán vị nạp), tiling per (node, scope), oracle diff, rebuild-from-log bit-exact, contamination probe | Mỗi test là một falsifier của một lời hứa cụ thể | Tin bằng review |

## I. Phạm vi

| ID | Quyết định (LOCK) | Lý do | Đã loại |
|---|---|---|---|
| D-48 | KHÔNG BAO GIỜ CẮT: parser đúng, ratification gate (kể cả batch), fold + as-of, verifier cứng, benchmark. Thang de-scope chi tiết ở 05 | Bốn thứ đó LÀ sản phẩm; mọi thứ khác là trang sức | — |
| D-49 | Phụ lục Basel/TT41 công thức: node blob, KHÔNG hứa trả lời tính toán | Trung thực về năng lực; tính CAR là bài toán khác | Parse công thức, tính hộ |
| D-50 | Doctrine tổ chức (structured authoring, dual issuance, expiry/scorecard/issuer-pays) = đề nghị SHB, cần chữ ký cấp C — KHÔNG phải deliverable hackathon; schema chừa hook `owner`, `review_by` | Không chặn ingest bằng một cuộc cải cách quy trình; nhưng đường dài phải nói được | Bắt buộc structured authoring ngay demo |
