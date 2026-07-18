# 05-DEMO-DEFENSE — Kịch bản demo, money slide, phản biện, de-scope, production path

> File này sở hữu: trình diễn và phòng thủ. Mọi beat trỏ về golden item (04) và cơ chế (03) — demo LÀ acceptance suite chạy sống.

## §1. Tám demo beats (theo thứ tự kể chuyện, ~7 phút)

| # | Beat | Thao tác trên sân khấu | Chứng minh |
|---|---|---|---|
| 1 | Hỏi thường — trả lời từ trạng thái | Hỏi CUR-01 → answer 4 mục, citation chip, phả hệ "Đ8 TT39 ← TT06 ← TT10" | D-01, provenance |
| 2 | **Naive RAG chết trên cùng câu hỏi** | Cùng câu → baseline: trích bản 2016/điều khoản TT06 tự tin, dẫn nguồn "đúng" — sai | Money shot #1: groundedness không cứu được staleness |
| 3 | Câu bẫy lịch sử | SUS-02 "khoản 8 Đ8 đã từng hiệu lực chưa?" → "chưa từng" + timeline dải treo; PIT-01 "3/2024 KBNN/LDR?" → text TT26 nguyên vẹn | khoảng-rỗng, bẫy viết-lại-lịch-sử |
| 4 | Time travel + K | as-of slider 2022 → text cũ; ASK-01 với K cutoff → "tại ngày đó hệ đã có thể biết gì" + coverage attestation | tritemporal |
| 5 | Piecewise | GF-02 "HĐ ký 2021?" → hai nhánh dán nhãn / hỏi lại đúng một câu | D-04, D-26 |
| 6 | Conflict certificate | CFL-02 (as-of 2018) → certificate Đ468 vs TT39; kéo as-of qua 2019 → resolved by NQ01 | tier-2, statement giải |
| 7 | Tier C nhìn thấy được | Câu ép fail gate cứng → render sources-only khác biệt thị giác | "degradation là feature, không phải lời xin lỗi" |
| 8 | **Vòng đời 15 giây** | Bấm "văn bản mới về" (fixture): op đề xuất → curator duyệt (1 per-op + 1 batch với invariant template) → replay → hỏi lại: answer ĐỔI → notification bắn cho owner QT-TD-01 (SEM-01) | Money shot #2: substrate sống + blast-radius |

Beat dự phòng (nếu được hỏi): CTM-01 chạy live — query dựng từ text khoản bị treo → hệ không trích điều khoản sửa đổi; baseline thì có.

## §2. Money slide (bảng kết quả theo class — điền số từ /eval)

| Class | Naive RAG | LawState |
|---|---|---|
| currency / suspension / contamination | leak X% | **leak 0%** (gate cứng) |
| point-in-time / op-on-op (history) | không có khái niệm | 100% (gate cứng) |
| grandfather piecewise | chọn thầm 1 nhánh | ≥90% đủ nhánh |
| closure (định nghĩa+ngoại lệ) | ~X% | ≥90% |
| conflict | im lặng chọn một bên | certificate/resolved + doctrine |
| abstain | bịa có dẫn nguồn | F1 ≥0.80, route chuyên gia |

Một câu đóng slide: *"Naive RAG trả lời tự tin, dẫn nguồn đúng, nguyên văn đúng — và sai. Chúng tôi làm cho loại sai đó trở thành KHÔNG THỂ BIỂU DIỄN ở tầng dữ liệu, thay vì hy vọng model né được nó."*

## §3. Ngân hàng câu phản biện (probe) + trả lời chuẩn

| ID | Probe (giám khảo sẽ hỏi) | Trả lời (cơ chế + nơi xem) |
|---|---|---|
| PB-01 | TT10 treo "đến ngày văn bản mới có hiệu lực" — ai đóng cửa sổ, lúc nào? | `pending_event` + sweep sau mỗi ingest đề xuất `close_window`; NGƯỜI chốt vì "văn bản X có phải sự kiện đang chờ" là phán đoán ngữ nghĩa (D-11, S4.6, test_pending_sweep) |
| PB-02 | Bãi bỏ một điều khoản sửa đổi — query giữa cửa sổ cũ trả gì? Ai tính text? | Op nhắm op, đóng forward-only, cửa sổ cũ bất khả xâm phạm (INV-5); engine tự tính, không ai dựng tay text bù (D-10, PIT-01/02) |
| PB-03 | Text bị treo vẫn nằm nguyên văn trong TT06 đang hiệu lực — sao không leak? | Node role `amending` bị loại khỏi retrieval từ tầng khóa dữ liệu; nội dung chỉ sống qua op; contamination probe trong CI (D-05, INV-8, CTM-01) |
| PB-04 | Omnibus ~100 op — cho xem log duyệt không phải rubber-stamp | Hai hàng đợi: definitional per-op; cơ học batch với invariant template MÁY VERIFY từng op + spot-check ≥10%; chữ ký người phủ 100% log; không auto-ratify (D-19, INV-6, FR-10) |
| PB-05 | HĐ ký 2021 chưa sửa đổi — hôm nay áp bản nào? Cho xem candidate set | Scope nằm TRONG khóa snapshot: version cũ vẫn `active` dưới predicate cohort; thiếu dữ kiện → piecewise, cấm chọn thầm (D-04, GF-02, test_scope_split) |
| PB-06 | Làm sao biết hệ không BỎ SÓT văn bản? | Không hứa điều đó (từ chối #3): chỉ attestation coverage theo kênh liệt kê được, Công báo dò gap bằng số tuần tự; luôn nói "đã quét gì, đến đâu" (D-32, R-6) |
| PB-07 | Thanh tra hỏi: lúc giải ngân ngân hàng CÓ THỂ BIẾT gì? | Trục K: `V(t, s | K)` — fold chỉ op `ingested_at ≤ K`; answer_log replay bit-exact (D-02, ASK-01, INV-10) |
| PB-08 | Hai văn bản cùng ngày hiệu lực cùng hạng — thứ tự nạp có đổi kết quả không? | Không: tie-break canonical (rank, valid_from, issued_date, seq); CI có test hoán vị thứ tự nạp (D-23, INV-3) |
| PB-09 | Sao dám auto-resolve xung đột bằng Đ156? | Chỉ tự động phần ĐÃ LUẬT HÓA (cấp trên thắng; sau thắng cùng cơ quan); "chuyên ngành thắng" không phổ quát — bằng chứng: Đ468 vs TT39 phải chờ NQ01 ⇒ tier-2 certificate, hệ không tự phân xử (D-33, CFL-02) |
| PB-10 | Verifier là LLM chấm LLM? | Không: gate quyết định là CODE (verbatim+số exact, luôn bật, floor Tier C); LLM judge KHÁC HỌ model chỉ thêm flag, và chưa κ≥0.8 thì không được nâng ai lên Tier A (D-30, D-31, R-32/33) |
| PB-11 | "Mọi quy định trước đây trái với Thông tư này hết hiệu lực" — hệ làm gì? | Op targetless, không mutate state (về pháp lý là declaratory của Đ156); seed conflict screening scoped chủ đề văn bản mới (D-14) |
| PB-12 | Quy trình nội bộ cite "quy định của NHNN về cho vay" không số hiệu — TT39 bị thay toàn văn thì ai báo? | Edge `chu_de` trỏ NORM (danh tính xuyên kế vị); blast-radius qua Norm → notice cho owner có tên, severity phân tầng (D-09, D-36, SEM-01) |
| PB-13 | Thay toàn bộ một Điều, cơ cấu điểm đổi — "điểm c" cũ và mới là một? | Không: con sinh birth-id MỚI, tương chiếu non-binding; timeline không trình bày hai danh tính như một (D-08) |
| PB-14 | Sao không dùng Neo4j/PhoBERT/OpenSearch như gợi ý đề bài? | Danh sách gợi ý là candidates, không phải constraints: đồ thị vài nghìn node = bảng edge + CTE (zero điểm khác biệt, thêm ops); PhoBERT không phải sentence embedder, 256 token; BM25 in-process đủ ở quy mô này (D-38..40) |
| PB-15 | Khách hàng moi được tài liệu nội bộ không? | Audience filter ở tầng SQL qua query-builder một cửa, mọi stage; pen-test 20 câu adversarial trong CI (INV-12, test_audience_pentest) |
| PB-16 | Scale lên hàng nghìn văn bản thật thì curator chịu nổi không? | Trung thực: throughput curator là bottleneck đã định giá — batch-ratify giảm bậc độ lớn công per-op; demand log (câu Tier-D xếp tần suất) quyết định thứ tự consolidate; con số FTE là câu hỏi mở của pilot, không phải của demo (D-19, S6 /admin/demand) |

## §4. Thang de-scope (cắt từ trên xuống khi cháy giờ)

Cắt được, theo thứ tự: (1) reranker; (2) TTL đo động học (giữ config tĩnh); (3) LLM pair-proposer tier-3c (GIỮ blast-radius 3a + invariant 3b); (4) graph viz đẹp (giữ bảng edge); (5) judge mềm (gate cứng vẫn nguyên — tier cap B, nói thẳng trên UI); (6) multi-turn session (mỗi câu độc lập); (7) VBHN oracle diff chạy tay một lần thay vì tự động.

**KHÔNG BAO GIỜ CẮT** (D-48): parser đúng (exit R-4), ratification gate kể cả batch, fold + as-of + timeline, verifier cứng, benchmark + baseline. Bốn thứ đó LÀ sản phẩm.

## §5. Risk register (nói trước, không để bị hỏi)

| Risk                              | Thực tế                                               | Mitigation                                                                                       |
| --------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Curator throughput                | omnibus ~100 op là ca thường                          | batch-ratify + demand log; ratify UI làm TRƯỚC chat UI                                           |
| Extraction sai mà không thấy      | determinism chỉ bảo hành tái lập, không bảo hành đúng | cross-validation ngoặc provenance; differential oracle VBHN; risk-router per-op cho definitional |
| Conflict recall không thể biết đủ | về nguyên lý                                          | không quảng cáo exhaustive; UI ghi "phát hiện"; SLA triage                                       |
| Tiếng Việt entailment yếu         | judge mềm                                             | κ-gate + cap Tier B; gate quyết định là code                                                     |
| OCR/legacy nội bộ                 | ngoài phạm vi MVP                                     | ưu tiên HTML/DOCX; khối scan đi sau kiểm kê (doctrine D-50)                                      |
| Demo beat chết trên sân khấu      | stack lạ                                              | stack ops-tối-thiểu một laptop; mọi beat là golden item đã chạy trong CI trước                   |

## §6. Production path (một slide, trả lời "rồi sao nữa")

Self-host LLM (Qwen-72B/vLLM) sau gateway — kiến trúc không đổi (D-41). SSO/OIDC + RBAC thay role header; Postgres RLS bật policy thật (D-44). Shadow-mode cạnh compliance team: mọi answer Tier A được người kiểm lại, **công bố discrepancy rate nội bộ** so baseline 2–3h/ngày; mở rộng corpus theo demand log; customer-facing CHỈ sau khi nội bộ chứng minh số. Diễn tập rebuild materialized view từ log định kỳ (INV-9) — bài học FAA 1/2023: view sập khi log còn nguyên vẫn đủ ground toàn bộ. Doctrine dài hạn cho corpus nội bộ: structured authoring + dual issuance + expiry/scorecard/issuer-pays — điều kiện một chữ ký cấp C (D-50).

## §7. Một câu nếu chỉ được nói một câu

*"Chúng tôi không xây search engine tốt hơn trên đống văn bản — chúng tôi xây một cỗ máy tính hiệu lực với ba trục thời gian, đặt retrieval lên trên trạng thái nó tính ra, và ở mọi chỗ máy không có thẩm quyền để quyết, nó phát chứng chỉ thay vì phát minh câu trả lời."*
