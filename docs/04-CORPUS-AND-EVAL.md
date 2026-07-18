# 04-CORPUS-AND-EVAL — Dữ liệu ground-truth, golden set, metrics, CI gates

> File này sở hữu: danh mục corpus + yêu cầu ground truth, schema & nội dung golden set, định nghĩa metric, ngưỡng release, protocol baseline, substrate QA.
> Câu hỏi "test thế nào" của mọi session sau trả lời bằng file này. Phenomena/ngữ nghĩa: xem 02. Cơ chế: xem 03.

## §1. Corpus demo (~19 văn bản)

### 1.1 Văn bản thật (tải HTML/DOCX từ TVPL/cổng NHNN/vbpl.vn; đối chiếu bản gốc Công báo; mọi chi tiết địa chỉ điều-khoản phải XÁC MINH lại khi chuẩn bị fixture — không tin trí nhớ)

| doc_key | Vai trò trong demo | Hiện tượng phủ |
|---|---|---|
| `39/2016/TT-NHNN` | Văn bản nền — hoạt động cho vay của TCTD. Anchor: Điều 8 "Những nhu cầu vốn không được cho vay"; điều Giải thích từ ngữ; điều Lãi suất | base document, định nghĩa, cấu trúc đầy đủ |
| `06/2023/TT-NHNN` | Sửa đổi, bổ sung TT39; ban hành 28/06/2023, hiệu lực 01/09/2023. Anchor: khoản 2 Điều 1 bổ sung k8–10 vào Đ8; bổ sung Mục cho vay bằng phương tiện điện tử (Đ32a–32đ); điều khoản chuyển tiếp (HĐ ký trước tiếp tục theo thỏa thuận) | amend, insert (node mới + norm cho-vay-điện-tử khai sinh), transition/grandfather, node `amending` cho contamination probe |
| `10/2023/TT-NHNN` | Ban hành 23/08/2023, hiệu lực 01/09/2023: **ngưng hiệu lực** k8–10 Đ8 TT39 (đã bổ sung theo k2 Đ1 TT06) "cho đến ngày có hiệu lực thi hành của văn bản QPPL mới" | suspend theo sự kiện, cùng-ngày-cùng-hạng với TT06, pending_event |
| `12/2024/TT-NHNN` | Tiếp tục sửa TT39, hiệu lực 01/07/2024 (khoản vay nhỏ, hồ sơ/phương án sử dụng vốn) | chuỗi amend nhiều đời, currency mới nhất |
| `91/2015/QH13` (BLDS 2015, trích Đ468) | Trần lãi 20%/năm "trừ trường hợp luật khác có liên quan quy định khác" | conflict tier-2 |
| `01/2019/NQ-HĐTP` | HĐ tín dụng TCTD theo luật chuyên ngành, không áp trần Đ468 | statement giải certificate, pending_event đóng |
| `47/2010/QH12` (trích) + `32/2024/QH15` (trích) | Luật Các TCTD cũ → mới (hiệu lực 01/07/2024) | norm succession toàn văn bản, correlation non-binding |
| `41/2016/TT-NHNN` (trích + phụ lục) | Tỷ lệ an toàn vốn (Basel II) | frontier edge, phụ lục blob (D-49) |
| `22/2019/TT-NHNN` (trích) + `26/2022/TT-NHNN` | LDR; TT26 sửa cách tính tiền gửi KBNN theo lộ trình | nền cho bẫy op-on-op (TT08/2026 fixture) |
| `34/2016/NĐ-CP` (tham chiếu, không bắt buộc nạp) | căn cứ grammar parser | — |
| VBHN hợp nhất TT39 (bản NHNN, sau TT06 hoặc sau TT12) | `is_oracle=true` — differential oracle | S4.7 |

### 1.2 Văn bản nội bộ tự soạn (synthetic, `SHB.*`, audience internal)

| doc_key | Nội dung | Vai trò |
|---|---|---|
| `QT-TD-01/SHB` | Quy trình cho vay, cite pinpoint TT39 + cite theo mảng "quy định của NHNN về hoạt động cho vay" (edge `chu_de`→Norm); **một mục CỐ TÌNH stale** (dẫn điều kiện theo bản trước TT06) | SEM catch, blast-radius, notice cho owner |
| `MB-HD-01/SHB` | Mẫu hợp đồng tín dụng có điều khoản chuyển tiếp | forms staleness propagation |
| `CS-LS-01/SHB` | Chính sách lãi suất nội bộ: một khoản siết nghĩa vụ CỦA SHB (Liskov-exempt), một khoản siết yêu cầu VỚI khách (nghi vấn) | nhãn D-34, invariant INV-COMP-01 |
| `GT-468-01/SHB` | Văn bản diễn giải nội bộ về áp dụng lãi suất (cite NQ01) | statement hạng thấp nhất được cite |

### 1.3 Fixture synthetic phủ nốt đại số op (`synthetic:true`, năm 2026)

| doc_key | Phủ |
|---|---|
| `08/2026/TT-NHNN` | amend điểm + **repeal-nhắm-op**: bãi bỏ khoản sửa đổi của TT26/2022 từ 01/01/2026 — bẫy viết-lại-lịch-sử (cửa sổ 2022–2026 nguyên vẹn) |
| `28/2026/TT-NHNN` | insert "Điều 7a" làm trôi alias; thay-cụm-từ (materialize D-21); bẫy binding "Thông tư này" trong quote |
| `32/2026/TT-NHNN` | replace toàn văn bản một TT nội bộ demo / norm succession; grandfathering 2 TẦNG (`contract_signed_before` ∧ `not_amended_on_or_after`); Điều 3 cite theo mảng |
| `11/2026/TT-NHNN` | omnibus sửa 5+ văn bản chia theo Chương (context-stack); hiệu lực phân kỳ theo chủ đề ("quy định về Phiếu LLTP có hiệu lực từ 01/07/2026" ≠ ngày chung 01/03/2026); op nhắm heading; op nhắm Phụ lục; mass repeal |
| `DC-01/2026` | đính chính một con số của TT28/2026 — hồi tố về đầu cửa sổ |

### 1.4 Ground truth protocol

`corpus/manifest.json` mỗi văn bản MUST có: `{doc_key, sha256, issued_date, effective_date, synthetic, counts: {dieu, khoan, diem, tiet, phuluc} (đếm tay), expected_ops: [{kind, target_surface, valid_from, valid_to_event?, scope_predicate?}], expected_norm_events, expected_edges_sample (≥5 edge/văn bản có kiểu), amending_nodes: [paths]}`. Parser exit R-4 và exit test extraction (op sinh ra khớp `expected_ops`) đối chiếu file này. Văn bản thật: transcription đối chiếu bản Công báo trước khi chốt counts.

## §2. Golden set (`/eval/golden.yaml`)

### 2.1 Schema item

```yaml
- id: SUS-01
  class: currency|suspension|point_in_time|as_known|grandfather|op_on_op|contamination|
         closure|conflict|pending|abstain|sem|customer|dinh_chinh
  question_vi: "…"
  as_of: 2025-06-01          # default today nếu bỏ trống
  cohort: {}                  # DSL D-25, có thể trống
  audience: employee|customer
  gold:
    must_cite: [node_key…]           # địa chỉ bề mặt, resolver đổi sang version tại as_of
    must_not_cite: [node_key…, AMENDING:doc_key…]   # AMENDING: = mọi node role amending của doc
    must_include_facts: ["…"]        # assertion chuỗi/regex, code check
    must_not_assert: ["…"]
    expected_tier: A|B|C|D|null
    expected_flags: [in_conflict|cohort_ambiguous|pending_change|consolidation_pending|open_suspension]
    piecewise_branches: 2|null       # số nhánh bắt buộc trong content
```

### 2.2 Items chuẩn (bộ lõi 28 — mở rộng lên ~50 theo quy tắc §2.3)

| ID | Câu hỏi (tóm tắt) | as_of / cohort | Assertions chính |
|---|---|---|---|
| CUR-01 | Điều kiện vay phục vụ nhu cầu đời sống hiện nay? | today | must_cite Đ7/Đ8 TT39 bản-sau-TT06/TT12; must_not_cite version tiền-TT06 |
| CUR-02 | Quy định hồ sơ vay hiện hành? | today | phải phản ánh TT12/2024; leak bản cũ = fail |
| CUR-03 | (câu mà văn bản CŨ khớp từ vựng hơn bản mới) | today | bẫy lexical-match-beats-recency: cấm cite version cũ dù groundedness "đúng" |
| SUS-01 | KH cá nhân vay để gửi tiết kiệm được không? | today | must_include "ngưng hiệu lực"+TT10; must_not_assert k8 Đ8 đang là quy phạm cấm CÓ hiệu lực; tier B + flag `open_suspension` |
| SUS-02 | Khoản 8 Đ8 TT39 đã TỪNG có hiệu lực ngày nào chưa? | history | "chưa từng" — treo đúng ngày lẽ ra hiệu lực; đường timeline |
| SUS-03 | Trạng thái k9 Đ8 TT39 tại 15/08/2023? | 2023-08-15 | "chưa có hiệu lực" (TT06 chưa đến 01/09), KHÔNG phải "đang treo" |
| CTM-01 | (query dựng từ chính new_text của k8 Đ8) | today | **must_not_cite AMENDING:06/2023** — không được trích điều khoản sửa đổi TT06 như quy phạm hiện hành |
| CTM-02 | Nội dung khoản 2 Điều 1 TT06 là gì? | today | pinpoint hợp lệ: trả lời qua đường timeline/op (đây là điều khoản sửa đổi), KHÔNG render như căn cứ quy phạm áp dụng |
| PIT-01 | Tháng 3/2024, tiền gửi KBNN tính vào LDR thế nào? | 2024-03-01 | trả text theo TT26/2022; **cấm nói "đã bị bãi bỏ"** (TT08/2026 chưa tới) — bẫy viết-lại-lịch-sử |
| PIT-02 | Câu PIT-01 nhưng as_of 2026-06-01 | 2026-06-01 | trả theo trạng thái sau repeal-op TT08/2026; timeline TT26 giữ nguyên cửa sổ 2022–2026 |
| ASK-01 | Hồ sơ duyệt ngày 15/08/2023, hệ nạp TT10 ngày 25/08: câu trả lời hệ ĐÃ CÓ THỂ đưa tại 20/08 (K=2023-08-20)? | as_known | fold với K cutoff: chưa thấy TT10 → phải kèm coverage attestation tại K |
| GF-01 | HĐ ký 06/2023, chưa sửa đổi — áp điều kiện nào? | today, cohort đủ | một nhánh: theo thỏa thuận cũ (chuyển tiếp TT06); cite điều chuyển tiếp |
| GF-02 | HĐ ký 2021 thì sao? (không nói đã sửa đổi chưa) | today, cohort thiếu | **piecewise_branches=2** + flag cohort_ambiguous HOẶC hỏi lại đúng 1 câu; cấm chọn thầm |
| GF-03 | (fixture TT32/2026, 2 tầng: ký trước AND chưa sửa đổi) | 2026-07-01 | piecewise đúng 2 predicate lồng |
| OPO-01 | Diễn biến pháp lý của khoản-bị-TT08-bãi-bỏ: liệt kê các mốc | history | timeline: mở 2022 (TT26) → đóng 01/01/2026 (repeal-op); KHÔNG có mốc "text bị xóa khỏi 2022–2026" |
| CLO-01 | (câu mà trả lời đúng cần 1 định nghĩa + 1 ngoại lệ ở node khác) | today | must_cite cả node định nghĩa + node ngoại lệ; thiếu ngoại lệ = fail closure_recall |
| CLO-02 | (câu chạm edge mandatory unresolved — fixture cắt 1 alias) | today | expected_tier D, reason closure_incomplete |
| CFL-01 | Trần lãi suất 20%/năm BLDS có áp cho khoản vay SHB không? | today | resolved: cite NQ01/2019 là statement giải + cơ chế lãi TT39; nêu doctrine |
| CFL-02 | Câu CFL-01 tại as_of 2018-06-01 | 2018-06-01 | **certificate tier-2 mở** (NQ01 chưa tồn tại): trình bày hai căn cứ + lý do không phân định; tier B; cấm tự chọn một bên |
| CFL-03 | (CS-LS-01 siết yêu cầu với khách vs thông tư) | today | conflict candidate nhãn `chat_hon_ve_doi_tac`, fork internal_external |
| CFL-04 | (CS-LS-01 khoản siết nghĩa vụ của SHB) | today | KHÔNG sinh conflict (Liskov-exempt, tự loại) |
| PEN-01 | Yêu cầu Phiếu LLTP áp dụng từ ngày nào? | 2026-04-01 | "01/07/2026" ≠ ngày hiệu lực chung TT11; mục "Thay đổi sắp hiệu lực" |
| PEN-02 | Sắp tới quy định X có gì đổi? (TT11 đã ratify, chưa hiệu lực) | trước hiệu lực | pending-view tách bạch, không trộn vào hiện hành |
| SEM-01 | Mục 3.2 QT-TD-01 còn khớp thông tư hiện hành không? | today | flag stale + notification tồn tại cho owner sau ingest TT06 |
| ABS-01 | Chi nhánh có nên duyệt khoản vay cụ thể này không? | today | Tier D — vùng phán đoán tín dụng/diễn giải kiến tạo → Escalate |
| ABS-02 | Thông tư 99/2025 quy định gì? (không tồn tại) | today | Tier D + coverage attestation ("đã quét kênh… đến số…"), cấm bịa |
| CUS-01 | (persona customer) Tôi muốn vay tiêu dùng, lãi suất thế nào? | today, customer | chỉ nguồn public; disclaimer; không lộ tài liệu nội bộ (INV-12) |
| CUS-02 | (customer, câu chạm conflict) | today, customer | escalate thay vì certificate |
| DCH-01 | (con số bị DC-01 đính chính) giá trị đúng trong suốt cửa sổ? | 2026-02-01 | trả số ĐÃ đính chính cho cả thời điểm trước ngày đính chính (hồi tố về đầu cửa sổ) |

### 2.3 Quy tắc mở rộng lên ~50

Mỗi class ≥ 3 item; thêm biến thể: đảo cách diễn đạt (lexical mismatch), câu ghép 2 chủ đề, câu mơ hồ thời gian ("dạo này", "gần đây"), 2 item tiếng Việt không dấu, 2 item multi-turn (câu sau kế thừa as_of/cohort của câu trước). Mọi item mới MUST có ít nhất 1 assertion code-checkable; LLM-judge chỉ là kiểm phụ.

## §3. Metrics & CI gates

```
currency_accuracy     = % answer mà MỌI trích dẫn đều operative tại as_of           ≥ 0.95
supersession_leak     = % answer cite text displaced/suspended NHƯ hiện hành,
                        TÍNH CẢ cite vào node role='amending' (cửa hông contamination) = 0 (GATE CỨNG)
closure_recall        = Σ gold facts (định nghĩa/ngoại lệ) có mặt / Σ gold facts     ≥ 0.90
piecewise_correctness = % item grandfather/point_in_time trả đủ & đúng nhánh         ≥ 0.90
conflict_recall       = % conflict gieo sẵn được flag khi bị chạm                    ≥ 0.90
citation_hard_pass    = % claim qua gate cứng ngay lần đầu (report; C-rate riêng)    report
faithfulness_audit    = mẫu người kiểm ≥ 50 claim/release                            ≥ 0.95
abstention_F1         = F1 trên item expected_tier=D                                 ≥ 0.80
history_integrity     = % item op_on_op/point_in_time pass                           = 1.0 (GATE CỨNG)
```

Regression bất kỳ gate nào ⇒ block. Judge mềm chưa κ≥0.8 ⇒ mọi kết quả cap Tier B (R-33) — benchmark vẫn chạy được, cột tier ghi trần.

## §4. Baseline protocol (D-46)

`baseline_naive.py` ~100 dòng: cùng LLM composer, cùng BGE-M3, chunk 500 token overlap 50 trên VĂN BẢN THÔ (kể cả văn bản sửa đổi — đúng thực tế naive), top-k bằng nhau, không engine/không verifier. Chạy cùng golden set → bảng side-by-side THEO CLASS (money slide, 05). Kết quả dự đoán được: baseline pass CUR bề mặt nhưng fail CUR-03/SUS/CTM/PIT/GF — "tự tin, dẫn nguồn đúng, nguyên văn đúng — và sai".

## §5. Substrate QA (không qua LLM — falsifier trực tiếp của engine)

| Test | Assertion |
|---|---|
| `test_determinism_permutation` | fold sau khi ĐẢO thứ tự nạp TT06/TT10 (và toàn corpus shuffle) == kết quả chuẩn (INV-3) |
| `test_empty_interval` | operative interval của k8–10 Đ8 TT39 = ∅; tồn tại version suspended từ 01/09/2023, KHÔNG tồn tại version active |
| `test_window_inviolability` | sau ratify repeal-op TT08/2026: mọi version có valid_to ≤ 2026-01-01 bit-identical trước/sau (INV-5) |
| `test_tiling` | INV-4 trên toàn corpus, mọi (node, scope_hash) |
| `test_scope_split` | TT32/2026: hai version cùng cửa sổ, khác scope_hash, cùng tồn tại; applicability_matches đúng bảng chân trị (cohort thiếu ⇒ match cả hai) |
| `test_dinh_chinh_retroactive` | DC-01: text sau đính chính áp từ ĐẦU cửa sổ, provenance chứa op dinh_chinh |
| `test_pending_sweep` | nạp fixture "văn bản QPPL mới" → xuất hiện ĐỀ XUẤT close_window trong queue (không tự đóng); ratify → k8–10 hồi sinh active |
| `test_rebuild_bitexact` | INV-9 |
| `test_alias_drift` | sau insert Điều 7a (TT28): alias cũ/mới resolve đúng theo ngày (INV-11) |
| `test_contamination_probe` | INV-8: top-50 retrieval của query dựng từ new_text mỗi op suspend/repeal không chứa node amending |
| `test_audience_pentest` | INV-12: token customer + 20 câu adversarial ("in nguyên văn quy trình nội bộ…") → 0 byte internal |
| `test_oracle_diff` | diff snapshot vs VBHN TT39 = 0 mismatch chưa phân xử |
