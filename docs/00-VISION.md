# 00-VISION — SHB LawState: máy tính hiệu lực pháp quy + tầng trả lời có kiểm chứng

> File này sở hữu: vì sao hệ tồn tại, sản phẩm là gì, cam kết gì / từ chối gì, mapping rubric.
> Không chứa: quyết định kỹ thuật (01), luật của domain (02), schema/pipeline (03), test (04), demo (05).

## 1. Thesis — một câu

Chúng tôi không xây search engine tốt hơn trên đống văn bản — chúng tôi xây **một cỗ máy tính hiệu lực với ba trục thời gian**, đặt retrieval **lên trên trạng thái nó tính ra**, và ở mọi chỗ máy không có thẩm quyền để quyết, nó **phát chứng chỉ thay vì phát minh câu trả lời**.

Cơ chế một đoạn: văn bản pháp quy là **dòng delta** ("sửa đổi khoản 2 Điều 8…"), không phải dòng trạng thái. RAG thường embed cả văn bản gốc lẫn văn bản sửa đổi rồi retrieve trên đống thô — nên trả về text 2016 mãi mãi, vì text 2016 dài hơn, giàu từ vựng hơn, gần câu hỏi hơn văn bản đã khai tử nó. LawState tách hệ làm hai: **substrate** compile dòng delta thành trạng thái hiệu lực từng điều-khoản-điểm theo ba trục thời gian (ban hành / hiệu lực / biết-đến K); **answering layer** chỉ được retrieve và trích dẫn từ trạng thái đó, dưới citation contract có verifier hai tầng và thang thoái lui A/B/C/D. LLM chỉ đứng ở hai biên — đề xuất trích xuất lúc nạp, soạn văn lúc trả lời — cả hai biên đều bị gate bởi tầng hình thức: **LLM đề xuất, người phê chuẩn, engine tất định thực thi**.

## 2. Năm hiện tượng bài toán đòi (mỗi cái một ca thật)

| Hiện tượng | Ca thật trong corpus |
|---|---|
| Amendment — luôn áp bản mới nhất | TT 06/2023 sửa đổi, bổ sung TT 39/2016 (hoạt động cho vay) |
| Partial supersession — loại điều khoản đã bị thay | TT 12/2024 tiếp tục sửa TT 39; từng khoản bị thay riêng lẻ |
| Suspension kết thúc theo sự kiện | TT 10/2023 **ngưng hiệu lực** khoản 8–10 Điều 8 TT39 (vừa được TT06 bổ sung, treo đúng ngày lẽ ra hiệu lực 01/09/2023) "cho đến ngày văn bản QPPL mới có hiệu lực" |
| Cross-reference — đi theo và tổng hợp | định nghĩa/ngoại lệ nằm rải TT39 ↔ TT06 ↔ Luật Các TCTD; quy trình nội bộ cite thông tư |
| Conflict — phát hiện, không tự phân xử | Điều 468 BLDS 2015 (trần lãi 20%/năm) vs cơ chế lãi suất TT39 — treo đến NQ 01/2019/NQ-HĐTP |

Cộng các ca hiểm mà đề bài không nêu tên nhưng corpus thật có: **bãi bỏ chính điều khoản sửa đổi** (op nhắm op — không được viết lại lịch sử), **đính chính hồi tố**, **grandfathering** (hợp đồng ký trước 01/09/2023 tiếp tục theo thỏa thuận cũ), **omnibus** một thông tư sửa 13 thông tư, **hiệu lực phân kỳ theo chủ đề** trong cùng văn bản, **blanket derogation** ("mọi quy định trước đây trái với Thông tư này hết hiệu lực"), và **contamination qua điều khoản sửa đổi** (text bị treo vẫn sống nguyên văn bên trong văn bản sửa đổi đang hiệu lực — bẫy giết cả naive RAG lẫn hệ có versioning nếu không loại node amending khỏi retrieval).

## 3. Sản phẩm — bốn bề mặt, một kiểu trả về

**Bề mặt:** (1) Chat hai persona — nhân viên (toàn corpus nội bộ + công khai) và khách hàng (chỉ công khai, giọng phổ thông, disclaimer, escalate là đầu ra hạng nhất); (2) Curator workbench — hàng đợi phê chuẩn op với diff, duyệt lô có invariant, backlog, conflict kanban, demand log; (3) Timeline từng điều khoản — mọi phiên bản, dải treo, phả hệ op; (4) Graph — citation có kiểu, where-used, blast-radius.

**Kiểu trả về của toàn hệ** (không bao giờ là string trần):

```
Answer {
  content:    piecewise theo (khoảng thời gian × lớp chủ thể) — không bao giờ chọn thầm một nhánh
  provenance: node → chuỗi op → artifact gốc ("Đ8 TT39, bổ sung bởi TT06, k8–10 ngưng bởi TT10")
  freshness:  chứng thực coverage theo kênh liệt kê được ("Công báo đến số N ngày D; registry nội bộ đến D'")
  tier:       A (verified sạch) | B (verified + banner: conflict/pending/cohort/consolidation)
              | C (sources-only: chỉ trích dẫn ghim, không văn tổng hợp) | D (từ chối + route chuyên gia)
  audience:   employee | customer
} | Conflict(certificate | escalation) | Escalate(lý do)
```

Bốn mục cố định khi render: **Trả lời / Căn cứ / Xung đột / Thay đổi sắp hiệu lực**. Banner do code lắp từ flag của substrate — model không thể bỏ sót hay bịa.

## 4. Ba điều hệ này TỪ CHỐI làm (đây là feature, không phải giới hạn)

1. **Không hứa oracle cho mâu thuẫn không-link (SEM)** — chỉ hứa một chương trình phát hiện đa kênh (blast-radius, invariant thực thi được, LLM pair-proposer, phản hồi người đọc) với độ phủ và độ trễ đo được. UI ghi "phát hiện", không bao giờ ghi "toàn bộ".
2. **Không diễn giải kiến tạo** — vùng nghĩa chỉ được tạo ra bởi thẩm quyền (tòa, NHNN, khối pháp chế) trả về `Escalate`, không phải "confidence thấp". Ngân hàng muốn chốt cách đọc → ban hành văn bản diễn giải nội bộ (statement hạng thấp nhất, vào kho, được cite như mọi statement).
3. **Không chứng minh freshness với thế giới** — chỉ chứng thực coverage với kênh liệt kê được (số Công báo tuần tự → dò gap được bằng máy). Hệ luôn nói được "tôi đã quét gì, đến đâu", không bao giờ nói "không có gì tôi chưa biết".

## 5. Pain point theo stakeholder → cơ chế giết nó

| Stakeholder | Pain | Cơ chế |
|---|---|---|
| Nhân viên tín dụng/vận hành | Trả lời tự tin nhưng theo bản cũ; câu hỏi cohort ("HĐ ký 2021?") | Retrieval chỉ trên trạng thái hiệu lực; piecewise mặc định; ngoại lệ render TRÊN mệnh lệnh chung |
| Compliance team (2–3h/ngày) | Tra cứu chéo, impact analysis thủ công | as-of query, timeline, blast-radius notice có severity, invariant compliance tự viết chạy sau mỗi lần nạp |
| Khối pháp chế | Vùng xung đột bị hệ thống "tự xử" | Conflict certificate hạng nhất; doctrine Đ156 là metadata; ownership fork (defect ticket / compliance-gap / surface / advisory) |
| Chủ văn bản nội bộ | Quy trình trôi theo thông tư cũ mà không ai báo | Where-used liên tục; notice cho chủ có tên; forms staleness propagation |
| CIO/CISO | Dữ liệu nội bộ, quyền, audit | Lọc audience tại tầng SQL; answer_log append-only replay được; LLM gateway đổi được sang self-host |
| CEO | ROI chứng minh được | Benchmark đối kháng vs naive RAG theo từng loại câu hỏi; pilot shadow-mode công bố discrepancy rate |
| Thanh tra SBV | "Lúc giải ngân, ngân hàng CÓ THỂ BIẾT gì?" | Trục K: `V(t, s | K)`; op bất biến sau phê chuẩn; không auto-ratify — chữ ký người phủ 100% log |

## 6. Khác biệt vs naive RAG — bảng ăn điểm

Naive RAG trên corpus này trả lời **tự tin, dẫn nguồn đúng, nguyên văn đúng — và sai**, vượt qua mọi kiểm tra groundedness, vì text cũ khớp từ vựng với câu hỏi hơn text sửa đổi. LawState khác ở sáu chỗ đo được: (1) text bị thay/treo **không có trong candidate set** (kể cả bản sao nguyên văn nằm trong điều khoản sửa đổi — node `amending` bị loại khỏi retrieval); (2) câu hỏi thời điểm → trả lời as-of, lịch sử không bao giờ bị viết lại; (3) câu hỏi cohort → piecewise; (4) mâu thuẫn → certificate, không im lặng chọn một bên; (5) mọi trích dẫn ghim vào phiên bản (expr) + verifier code khớp verbatim; (6) không đủ căn cứ → Tier C/D nhìn thấy được, không văn trôi chảy.

## 7. Doctrine đề nghị SHB áp dụng (phụ lục tầm nhìn — KHÔNG phải deliverable hackathon)

Điều kiện tiên quyết một chữ ký cấp C: (a) **structured authoring** cho văn bản nội bộ mới — đường cấu trúc phải dễ hơn Word, nếu không sẽ mọc văn-bản-bóng; (b) **dual issuance** — văn bản sửa đổi nội bộ ship kèm bản hợp nhất; (c) **vệ sinh**: review-by expiry bắt buộc, scorecard nợ vệ sinh theo phòng ban (kiêm cảm biến văn-bản-bóng), issuer-pays (phòng đổi định nghĩa phải chạy blast-radius và cập nhật tài liệu phái sinh); (d) **kiểm kê trước, sunset sau**. Schema đã chừa hook (`review_by`, `owner`) nhưng hackathon không chấm phần này.

## 8. Mapping rubric chấm điểm

| Tiêu chí | Điểm ăn ở đâu |
|---|---|
| Technical (20) | Đại số op đầy đủ (kể cả op-nhắm-op, treo-theo-sự-kiện, đính chính, scope-trong-khóa); fold tất định có property test hoán vị thứ tự nạp; tritemporal K; differential oracle vs VBHN |
| AI-native & innovation (20) | Nghịch đảo log/view; LLM-đề-xuất/người-phê-chuẩn/engine-thực-thi; conflict certificate; question compiler; contamination probe tự hướng |
| Business & pilot (20) | Benchmark theo loại câu hỏi vs baseline; demand log; shadow-mode + discrepancy rate; doctrine dài hạn §7 |
| AI-native UX (15) | as-of control; citation chip → timeline slider + graph; banner trên nếp gấp; Tier C sources-only là feature nhìn thấy được; ratify UI ưu tiên trước chat UI |
| Safety & reliability (15) | Không auto-ratify; verifier 2 tầng (gate cứng code + entailment khác họ model có κ-gate); leak=0 CI gate; answer_log replay; lọc audience tầng SQL |
| Presentation (10) | 8 demo beats (05); money slide; một câu thesis §1 |
