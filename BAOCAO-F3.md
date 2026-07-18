# BÁO CÁO F3 — Ingest: text pháp lý thô → cây node + edge có kiểu + op PROPOSED

Phạm vi sở hữu: `ingest/**`, `tests/ingest/**`. Mọi thứ F3 sinh ra dừng ở `status=proposed`
— máy đề xuất, người phê chuẩn, engine tất định thực thi (D-03). Không có LLM nào
được phép quyết định nội dung pháp lý cuối cùng.

Chạy demo: `uv run python -m ingest.demo "06/2023/TT-NHNN"` (hoặc doc_key bất kỳ trong manifest).

## 1. Kiến trúc pipeline

```
text thô ──normalize──▶ tree_parser (regex thuần, KHÔNG LLM)
                            │ ParsedDoc (node tree + quote-depth suppression)
                            ├─ roles      : node_role (amending → retrievable=false)
                            ├─ citation   : 3 tầng — (a) regex pinpoint + enumeration,
                            │               (b) ^Căn cứ → tham_quyen, (c) LLM leftovers
                            ├─ op_extract : rule verb-scan + LLM few-shot bắt buộc,
                            │               merge 2 nguồn → PROPOSED ops + birth-id (R-12)
                            └─ ratify     : router per_op / batch (D-19) + machine-verify
                                            R-15/R-16 (áp cả 2 chiều — không thiên vị)
orchestrator.build_bundle  = thuần (không DB) → IngestBundle
orchestrator.persist_bundle = ghi DB theo thứ tự R-3; pipeline.run(artifact_id) là seam F6
```

Alias resolver có cửa sổ thời gian (doc bị thay thế → alias trỏ doc mới theo ngày),
fallback provisional cho doc chưa vào kho; MemoryStore (test/demo) và DbStore (prod)
cùng interface.

## 2. Exit criteria — kết quả

### 2.1 R-4: parser đếm đúng 100% trên TOÀN BỘ corpus (24/24 văn bản)

| doc_key | dieu | khoan | diem | tiet | phuluc | khớp manifest | ops (F3/manifest·mẫu) |
|---|---|---|---|---|---|---|---|
| 39/2016/TT-NHNN | 35 | 106 | 86 | 0 | 0 | ✓ | 9/9 |
| 06/2023/TT-NHNN | 4 | 13 | 13 | 0 | 0 | ✓ | 28/21 |
| 10/2023/TT-NHNN | 3 | 0 | 0 | 0 | 0 | ✓ | 3/3 |
| 12/2024/TT-NHNN | 4 | 11 | 11 | 0 | 0 | ✓ | 21/20 |
| 91/2015/QH13 | 11 | 20 | 6 | 0 | 0 | ✓ | 2/2 |
| 01/2019/NQ-HĐTP | 14 | 27 | 22 | 0 | 0 | ✓ | 0/0 |
| 47/2010/QH12 | 17 | 88 | 36 | 0 | 0 | ✓ | 2/3 |
| 32/2024/QH15 | 13 | 109 | 50 | 0 | 0 | ✓ | 2/2 |
| 41/2016/TT-NHNN | 7 | 47 | 70 | 14 | 1 | ✓ | 0/0 |
| 22/2019/TT-NHNN | 12 | 55 | 57 | 35 | 0 | ✓ | 6/6 |
| 26/2022/TT-NHNN | 3 | 2 | 0 | 0 | 0 | ✓ | 2/2 |
| 52/2025/TT-NHNN | 4 | 0 | 0 | 0 | 0 | ✓ | 2/2 |
| 4033/QĐ-NHNN | 3 | 0 | 0 | 0 | 0 | ✓ | 1/1 |
| 21/VBHN-NHNN | 43 | 122 | 88 | 7 | 0 | ✓ | 0/0 |
| 06/VBHN-NHNN | 43 | 122 | 88 | 7 | 0 | ✓ | 0/0 |
| 08/2026/TT-NHNN | 4 | 0 | 0 | 0 | 0 | ✓ | 2/2 |
| 28/2026/TT-NHNN | 3 | 2 | 0 | 0 | 0 | ✓ | 3/3 |
| 32/2026/TT-NHNN | 8 | 18 | 5 | 0 | 0 | ✓ | 3/3 |
| 11/2026/TT-NHNN | 8 | 9 | 0 | 0 | 0 | ✓ | 9/9 |
| DC-01/2026 | 0 | 0 | 0 | 0 | 0 | ✓ | 1/1 |
| QT-TD-01/SHB | 7 | 13 | 5 | 0 | 0 | ✓ | 0/0 |
| MB-HD-01/SHB | 5 | 12 | 0 | 0 | 0 | ✓ | 0/0 |
| CS-LS-01/SHB | 5 | 6 | 0 | 0 | 0 | ✓ | 0/0 |
| GT-468-01/SHB | 3 | 6 | 0 | 0 | 0 | ✓ | 0/0 |

**24/24 khớp 100%** — kể cả VBHN 260 node, TT22 với 35 tiết, TT41 có phụ lục,
DC-01 là công văn không điều khoản. Điểm mấu chốt: quote-depth tracker — marker
cấu trúc bên trong text được trích dẫn “…” của điều khoản sửa đổi KHÔNG sinh node
(bẫy 02§7#1), nên TT06 chỉ có 4 Điều dù chứa nguyên văn 8 Điều mới của TT39.

### 2.2 Extraction: expected_ops khớp 89/89 (100%)

Manifest liệt kê op MẪU (89 mục); F3 sinh 96 op — mọi mục manifest đều khớp
(kind + target_doc + target_path + valid_from + phần nội dung), phần dư là
phân rã hợp lệ (xem adjudication). Phân bố op F3:

```
amend=40  insert=18  repeal=27  suspend=3  dinh_chinh=2  norm_decl=5  blanket_derogation=1
tổng=96 · tất cả status=proposed · 23 node birth-id (R-12) do insert/op-pending sinh
```

Các ca gai góc đã xử đúng (đối chiếu tay với manifest — KHÔNG sửa manifest):

- **TT06 k6/k10, TT12 k1** — directive cha "Sửa đổi, bổ sung khoản 1, điểm a…"
  không mang quote, các điểm con mang mệnh lệnh + quote riêng → cha bị coi là
  container, chỉ con emit op. Trước fix, khóa merge va chạm ("khoản 1" của k6a
  và k10a nuốt nhau) → thiếu op Đ22k1; đã hoàn thiện địa chỉ tương đối TRƯỚC merge.
- **TT10** — ngưng hiệu lực ≠ bãi bỏ (bẫy #2): 3 suspend + event khôi phục,
  0 repeal; khoản 8-10 Điều 8 chưa tồn tại dưới dạng node (TT06 thay cả Điều 8,
  chưa ratify) → birth dưới node cha + provenance mention làm điều kiện (D-08).
- **TT12** — chain-cite "(đã được sửa đổi, bổ sung bởi điểm c, d khoản 6 Điều 1
  TT06)" nằm ở khoản CHA → op con thừa kế provenance mention của tổ tiên; đích
  b(iii)/c(iii) là tiết chỉ tồn tại trong text TT06 đề xuất → birth-id + R-13.
- **TT06 k11** — "Bổ sung Mục 3 Chương II (Điều 32a–32h)": phân rã thành 8 insert
  per-Điều (ADJ-1) vì DDL không có node mục.
- **4033/QĐ** — đính chính dạng phrase-swap: `phrase_from="ngày làm việc" →
  phrase_to="ngày"`, hồi tố về đầu cửa sổ TT52 (D-12); cùng ngày ban hành với
  TT52 → orchestrator xếp quyết định SAU thông tư khi trùng issued_date.
- **TT28/TT32** — "các văn bản sau đây" → phân phối repeal per-doc; kế vị norm
  (norm_decl succession D-09) cho TT thay thế toàn bộ.
- **TT11** — omnibus sửa 5 thông tư: binding theo Chương (02§5.4); "Bổ sung
  khoản 3 vào Phụ lục 3 TT41" → amend nối blob phụ lục (ADJ-2); Phiếu LLTP
  hiệu lực 01/07/2026 ≠ 01/03/2026 ngày chung → `divergent_effective_date`
  + queue per_op (bẫy #10).

### 2.3 Edges ⊇ expected_edges_sample: 113/119 khớp + 6 adjudicated

```
tham_quyen=188  dinh_nghia=856  chu_de=131  ngoai_le=21  chuyen_tiep=75  frontier=62
tổng=1333 · 353 unresolved (confidence=0) → backlog cho curator — KHÔNG đoán mò
```

6 mẫu còn lại được adjudicate (ADJ-5): F2 tự đánh dấu chúng là "(ngữ nghĩa)",
"CFL-03", "PRECEDENCE-STATEMENT (D-15)", NORM không có cú pháp trích dẫn —
không tồn tại surface form theo 02§5.1/5.2 để regex bám; chúng thuộc tầng LLM
(c)/pair-proposer SEM/bảng precedence D-15, có danh sách tường minh trong
`tests/ingest/test_exit_corpus.py::SEMANTIC_EDGE_ADJ`.

Điểm đáng nói: edge trong quote của node amending VẪN được sinh (edge đi theo
phiên bản node, D-13) nhưng binding "Thông tư này" trong quote trỏ về doc ĐÍCH
(02§5.3) qua `chapter_target_doc` tính riêng từng node; node amending không
retrievable nên không lọt closure (D-05 giữ nguyên).

### 2.4 Bẫy 02§7 — trap tests (tất cả xanh)

| # | Bẫy | Test |
|---|---|---|
| 1 | marker trong quote không sinh node | test_tree_parser (TT06 mini + thật) |
| 2 | ngưng hiệu lực ≠ bãi bỏ | test_op_extract + exit TT10 |
| 3 | hai lớp sửa cùng đích (TT06+TT12) | exit + provenance R-13 |
| 8 | "Thông tư này" trong quote → doc đích | test_citation binding |
| 9 | omnibus TT11 tách đích theo Chương | test_llm_mock + live |
| 10 | phân kỳ hiệu lực Phiếu LLTP | exit TT11 + live |
| 11 | đính chính hồi tố (4033, DC-01) | test_op_extract + exit |
| 14 | VBHN là oracle, không ratify op từ nó | test_roles (is_oracle) |
| 15 | danh sách bãi bỏ phân phối per-doc | exit TT28/TT32 |
| 17 | điểm đ vs d, 32a…32h thứ tự chữ VN | test_surface + exit TT06 |

### 2.5 LLM: mock + live

- `tests/ingest/test_llm_mock.py` — gateway giả kiểm tra: merge rule↔LLM (đồng
  thuận → batch-eligible D-19; lệch → per_op + cờ), LLM không được bịa target
  (few-shot VD5 "no target guessing" — target không resolve → red flag, không drop).
- `tests/ingest/test_ingest_llm_live.py -m llm_live` — DeepSeek thật trên TT06 +
  TT10 + TT11 corpus thật: **3/3 pass** (~2m37s). LLM đồng thuận với rule trên op
  cơ học; TT10 giữ đúng suspend; TT11 tách đích và giữ phân kỳ hiệu lực.
- Few-shot bắt buộc trong prompt: tách enumeration, ngưng≠bãi bỏ, quote binding,
  phased effectivity, không đoán target.

### 2.6 Ratify router + machine-verify

- Router D-19: op cơ học (amend/insert/repeal có quote đầy đủ, rule↔LLM khớp,
  không cờ đỏ) → hàng `batch`; còn lại (definitional/prescriptive, divergent
  date, birth-id, provenance mismatch) → `per_op`. Chạy không-LLM: 96/96 per_op
  (đúng thiết kế — batch đòi hỏi hai nguồn độc lập đồng thuận).
- Machine-verify R-15/R-16 áp CẢ HAI chiều trước khi cho vào batch: quote khớp
  nguyên văn text nguồn, đích tồn tại/birth hợp lệ, ngày trong cửa sổ, không
  chồng lấn op khác — lệch bất kỳ → giáng xuống per_op kèm lý do.

## 3. Adjudications (mismatch có phán quyết — manifest KHÔNG bị sửa)

| ADJ | Nội dung | Phán quyết |
|---|---|---|
| ADJ-1 | TT06 k11 "Bổ sung Mục 3" — manifest 8 insert per-Điều | F3 phân rã giống hệt; DDL không có level mục — khớp từng Điều 32a…32h |
| ADJ-2 | TT11 seq4 target_part=appendix (ngoài DDL body/heading) | phụ lục là blob (D-49) → emit amend nối text vào node phuluc:3 |
| ADJ-3 | edge sample target "SELF (thi hành)" (TT06 Đ3, TT26 Đ2) | câu trách nhiệm thi hành không có địa chỉ đơn vị — không phải citation 02§5.1; pass-with-note |
| ADJ-4 | amending_nodes của VBHN | VBHN là oracle (is_oracle) — node không bao giờ retrievable; role không mang hệ quả |
| ADJ-5 | 6 edge "(ngữ nghĩa)"/CFL/PRECEDENCE/NORM không cú pháp | thuộc tầng LLM (c)/SEM/D-15 — ngoài phạm vi regex 02§5.1-5.2; danh sách tường minh trong test |

## 4. Ca không chắc chắn / giới hạn ghi nhận

- Ref TƯƠNG ĐỐI bên trong quote ("điểm a khoản 2" trong text mới của Đ22) được
  hoàn thiện theo ngữ cảnh node NGUỒN chứ không theo đơn vị đích → dst path có
  thể sai; các edge này đều confidence=0 → backlog, curator sửa tay. Fix đúng
  đắn cần mô phỏng cây SAU op — thuộc F4 re-derive sau ratify.
- "Luật Các tổ chức tín dụng" không năm trong quote TT12: alias nhị phân
  47/2010 vs 32/2024 — rule layer để unresolved (đúng hơn đoán); tầng LLM live
  pin được theo ngày văn bản.
- `provenance_mismatch` ×5 trên TT12: văn bản nói đích "đã được sửa bởi TT06"
  nhưng kho CHƯA có bản ratify của op TT06 → cờ này là hành vi ĐÚNG trước khi
  curator phê chuẩn chuỗi TT06 → TT12 theo thứ tự.
- 353 edge unresolved (chu_de trỏ mảng ngoài corpus, tên luật không số hiệu…)
  — cố ý không đoán: R-10 cấm cưỡng ép resolve.

## 5. Trạng thái test

```
uv run pytest -q -m "not llm_live"      → 248 passed (DB throwaway port 55433)
make smoke                              → 191 passed, 2 skipped
uv run pytest -m llm_live tests/ingest/test_ingest_llm_live.py → 3 passed (DeepSeek live)
```

Exit: R-4 24/24 · expected_ops 89/89 · edges 113/119 + 6 ADJ-5 · amending_nodes
khớp (trừ oracle ADJ-4) · demo `python -m ingest.demo <doc_key>` chạy trên mọi
doc trong manifest.
