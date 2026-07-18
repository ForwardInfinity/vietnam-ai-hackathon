# 02-DOMAIN-SPEC — Luật của bài toán (độc lập công nghệ)

> File này sở hữu: cấu trúc văn bản pháp quy VN, đại số toán tử sửa đổi với ngữ nghĩa chính xác, ba trục thời gian, doctrine ưu tiên & xung đột, ngữ pháp trích dẫn, danh sách bẫy đã trả học phí, glossary.
> Không chứa: schema/DDL, pipeline (xem 03). Mọi ví dụ "TT/20xx" năm ≥2026 là fixture synthetic (danh mục ở 04).

## §1. Cấu trúc văn bản (grammar được luật hóa bởi ND 34/2016/NĐ-CP, sđ ND 154/2020)

Cây phân cấp: `Phần → Chương → Mục → (Tiểu mục) → Điều → Khoản → Điểm → Tiết`. Đơn vị địa chỉ được (node): **Điều, Khoản, Điểm, Tiết, Phụ lục**. Chương/Mục là container tổ chức, không phải đích của op (nhưng là namespace context trong omnibus — §5.4).

Mẫu nhận dạng (line-anchored, sau chuẩn hóa §7.1):

```
Chương:  ^Chương\s+[IVXLCDM]+          Mục:    ^Mục\s+\d+
Điều:    ^Điều\s+\d+[a-zđ]?\s*[\.:]?    (có suffix chèn: Điều 24a, Điều 32đ)
Khoản:   ^\d+[a-zđ]?\.\s               (khoản chèn: "1a.")
Điểm:    ^[a-zđ][0-9]?\)\s             (bảng chữ cái TIẾNG VIỆT: …c, d, đ, e…)
Tiết:    ^\(?[ivx]+\)  và dạng hỗn hợp  a(iii), đ(i)   (một số thông tư dùng dày đặc)
Phụ lục: ^Phụ\s*lục\s+([0-9IVX]+)?      (node hạng nhất, addressable — op có thể
                                        "bổ sung một đoạn vào cuối Phụ lục 04"; nội dung
                                        công thức/bảng lưu blob, không hứa tính toán — D-49)
```

Quy tắc bắt buộc:

- **Tách heading/body cho mỗi node.** Điều có tiêu đề ("Điều 8. Những nhu cầu vốn không được cho vay") lẫn không ("Điều 1."). Có op CHỈ sửa tiêu đề (`target_part='heading'`). Có điều MỘT DÒNG mà toàn bộ op nằm trong heading ("Điều 21. Bãi bỏ khoản 6 Điều 22.").
- **Text được quote trong văn bản sửa đổi** bọc `"…".` — strip ngoặc kép và dấu chấm sau ngoặc đóng trước khi làm new_text.
- **Ngày**: `ngày (\d+) tháng (\d+) năm (\d{4})`; ngày hiệu lực lấy từ điều "Hiệu lực thi hành" (thường điều áp chót/chót); ngày ban hành từ header văn bản.
- **Số hiệu văn bản**: dạng `{số}/{năm}/{loại}-{cơ quan}` (`39/2016/TT-NHNN`, `34/2016/NĐ-CP`, `32/2024/QH15`). Có thể chứa khoảng trắng lỗi ngay trong bản gốc (`32 /2026/TT- NHNN`) — vá trước khi tokenize. Luật còn được cite bằng ngày ("Luật ... ngày 16/6/2010") — alias phải phủ cả hai dạng.

## §2. Ba trục thời gian

| Trục | Nghĩa | Ví dụ chuẩn |
|---|---|---|
| Ban hành (`issued_date`) | Ngày ký | TT06: 28/06/2023 |
| Hiệu lực (`[valid_from, valid_to)`) | Cửa sổ nội dung govern; nửa-mở; `valid_to` NULL = mở; có thể TƯƠNG LAI hoặc HỒI TỐ | TT06 hiệu lực 01/09/2023 |
| Biết-đến (`K`, `ingested_at`) | Thời điểm HỆ biết artifact/op | Câu audit: "lúc giải ngân, ngân hàng có thể biết gì?" = query với K cutoff |

Hệ quả bắt buộc: TT10 (ban hành 23/08/2023) treo các khoản mà TT06 bổ sung **trước khi chúng kịp có hiệu lực** (01/09/2023) — nếu không tách trục ban hành/hiệu lực, ca này không biểu diễn nổi; khoảng operative của khoản 8–10 Điều 8 TT39 là `[2023-09-01, 2023-09-01)` = **rỗng** — "đã từng có hiệu lực chưa?" → **chưa từng**.

## §3. Đại số toán tử (op) — ngữ nghĩa chính xác + cụm từ kích hoạt

| Kind | Cụm từ kích hoạt (rule layer) | Ngữ nghĩa engine | Ca đối chứng |
|---|---|---|---|
| `amend` | "sửa đổi, bổ sung … như sau", "được sửa đổi như sau", "thay thế cụm từ … bằng …" (materialize qua D-21) | Đóng version hiện tại của node tại `valid_from`, mở version mới với new_text/new_heading (`target_part`) | TT06 sửa nhiều điều TT39 |
| `insert` | "bổ sung Điều/khoản/điểm … như sau", "bổ sung … vào sau …" | Sinh NODE MỚI (birth-id mới) + alias; số thứ tự sau đó có thể trôi → alias windows | TT06 bổ sung k8–10 vào Đ8; bổ sung Điều 32a–32đ (Mục cho vay điện tử) |
| `repeal` (target node) | "bãi bỏ", "hết hiệu lực thi hành" | Đóng vĩnh viễn tại `valid_from`, status `repealed`, không hồi sinh | các khoản bị TT06 bãi bỏ |
| `suspend` | "ngưng hiệu lực thi hành" | Chèn version status `suspended` trên cửa sổ; KHÔNG xóa; hết cửa sổ → hồi sinh `active`. **`ngưng hiệu lực` ≠ `bãi bỏ` — hai kind khác nhau, few-shot phải có cả hai với TT10 làm ví dụ** | TT10 treo k8–10 Đ8 TT39 |
| `repeal` (target **op**) | "bãi bỏ khoản X Điều Y của Thông tư Z" khi khoản đó LÀ điều khoản sửa đổi | Đóng hiệu lực của op đích TỪ `valid_from` TRỞ ĐI; cửa sổ đã qua BẤT KHẢ XÂM PHẠM (D-10). Query tại thời điểm trong cửa sổ cũ vẫn trả text theo op cũ | fixture TT08/2026; pattern thật: bãi bỏ hàng loạt điều khoản sửa đổi |
| `close_window` (target op) | (do pending-event sweep đề xuất, người chốt) | Đặt `valid_to` cho op có `valid_to_event`; node treo hồi sinh từ ngày đó | văn bản QPPL mới đóng cửa sổ TT10 |
| `dinh_chinh` | "đính chính" (công văn/quyết định đính chính) | Sửa text HỒI TỐ về ĐẦU cửa sổ của version bị đính chính (khác amend) | fixture ĐC-01/2026 |
| `norm_decl` | tuyên bố thay thế toàn văn bản: "thay thế Thông tư số …", "Luật này thay thế Luật số …" | Khai sinh/kế vị/đổi-scope Norm; kèm repeal văn bản cũ; tương chiếu điều cũ↔mới NON-BINDING (D-08, D-09) | Luật Các TCTD 32/2024/QH15 thay Luật 47/2010/QH12; TT06 vừa sửa norm cho-vay vừa KHAI SINH norm cho-vay-điện-tử |
| `blanket_derogation` | "mọi quy định trước đây trái với Thông tư này hết hiệu lực" | KHÔNG mutate state; seed conflict screening theo chủ đề văn bản mới (D-14) | điều khoản thi hành phổ biến |

Ba tính chất bắt buộc của op: (1) suspend ≠ delete; (2) op nhắm được op, bãi bỏ op ≠ xóa op; (3) op đã phê chuẩn bất biến — sửa sai bằng op mới (D-20). `valid_to` có thể là **sự kiện chưa định danh** ("cho đến ngày có hiệu lực thi hành của văn bản QPPL mới" — nguyên văn TT10) → vào pending-event registry, re-evaluate mỗi lần nạp; phán đoán "văn bản X chính là sự kiện đang chờ" là ngữ nghĩa — máy đề xuất, người chốt (D-11).

**Hiệu lực phân kỳ theo chủ đề trong CÙNG một văn bản**: "các quy định về Phiếu lý lịch tư pháp có hiệu lực từ 01/07/2026" (khác ngày hiệu lực chung) — phân loại ngữ nghĩa, không regex nổi → bắt buộc per-op review (D-19).

## §4. Grandfathering & scope

Điều khoản chuyển tiếp mẫu (TT06): hợp đồng ký TRƯỚC ngày hiệu lực **tiếp tục thực hiện theo thỏa thuận đã ký**; nội dung sửa đổi/bổ sung SAU ngày hiệu lực phải theo quy định mới. → Trích thành scope predicate DSL đóng (D-25):

```
{ "contract_signed_before": "2023-09-01", "not_amended_on_or_after": "2023-09-01" }
```

Engine materialize **các version song song cùng cửa sổ, khác scope** (scope nằm trong khóa — D-04). Chủ thể thường không xác định lúc hỏi → câu trả lời mặc định **piecewise**: "HĐ ký trước 01/09/2023 chưa sửa đổi → quy định cũ; còn lại → quy định mới". Mô hình tư duy: Rust editions (nhiều phiên bản sống song song vô hạn qua lõi chung), không phải hot-patch.

## §5. Ngữ pháp trích dẫn & quy tắc binding

### 5.1 Pinpoint tuyệt đối (regex-first)

```
(Điều|khoản|điểm|tiết)\s+[\w,\sđ]+\s+(của\s+)?(Thông tư|Nghị định|Luật|Quyết định|Nghị quyết)\s+(số\s+)?[\d\w/–-]+
```
Expand enumeration: "các điểm a, b, c và đ khoản 1 Điều 39" → 4 edge riêng. "khoản 8, khoản 9 và khoản 10" → 3 op riêng (few-shot bắt buộc có ví dụ tách).

### 5.2 Kiểu edge (input của closure D-29 và risk classifier D-19)

| Kiểu | Nhận dạng | Vai trò |
|---|---|---|
| `tham_quyen` | đoạn `^Căn cứ` đầu văn bản (MIỄN PHÍ bằng regex, khỏi tốn LLM) | thẩm quyền ban hành; "Luật X được sửa đổi bởi Luật Y" trong căn cứ → trỏ **Norm**, không trỏ artifact |
| `dinh_nghia` | "theo quy định tại Điều X", term được giải thích tại điều "Giải thích từ ngữ" | mandatory closure khi term có mặt; inbound `dinh_nghia` → op sửa node đó là `definitional` |
| `ngoai_le` | "trừ trường hợp quy định tại …" | mandatory closure LUÔN, hai chiều |
| `chuyen_tiep` | điều khoản chuyển tiếp trỏ cohort | mandatory khi khớp cohort |
| `chu_de` | "thực hiện theo quy định của NHNN về hoạt động cho vay…" — KHÔNG số hiệu | trỏ **Norm**; nuôi blast-radius (TT39 đổi → tài liệu cite mảng phải nhận notice); KHÔNG gate closure |
| `frontier` | Basel, điều ước, chuẩn ngoài kho | advisory |

### 5.3 Binding "Thông tư này" (bẫy chết người của extraction)

- Cụm "Thông tư này/Điều này/Khoản này" nằm **TRONG text được quote** → bind vào văn bản **ĐÍCH** (Điều 7a mới được chèn vào TT09/2019 nói "Thông tư này" = TT09, KHÔNG phải thông tư sửa đổi).
- Nằm **NGOÀI quote** → bind vào văn bản **SỬA ĐỔI**.

### 5.4 Omnibus (một văn bản sửa nhiều văn bản)

Resolver mang **context-stack theo Chương/Điều**: "Điều 9" trần trong Chương "Sửa đổi Thông tư X" = Điều 9 của X. Heuristic carry-từ-tiêu-đề-văn-bản là KHÔNG đủ. Fixture TT11/2026 (sửa 13 thông tư, chia chương) là bài kiểm.

### 5.5 Cross-validation bằng ngoặc provenance

Văn bản/VBHN hay tự ghi "(đã được bổ sung theo khoản 2 Điều 1 Thông tư 06/2023/TT-NHNN)" — chuỗi provenance của node resolve được PHẢI chứa op tương ứng; lệch = trích sai → chặn ở ratify queue.

## §6. Doctrine ưu tiên & xung đột

### 6.1 Điều 156 Luật BHVBQPPL 2015 (đã luật hóa → tier-1 tự động)

1. Văn bản hiệu lực pháp lý **cao hơn** thắng (hierarchy: Hiến pháp > Luật/Nghị quyết QH > Pháp lệnh/NQ UBTVQH > Lệnh/QĐ CTN > NĐ-CP > QĐ-TTg > văn bản Bộ/TT liên tịch > … > văn bản nội bộ SHB > diễn giải nội bộ).
2. Cùng cơ quan ban hành, cùng vấn đề → văn bản **ban hành sau** thắng. **"Sau thắng" CHỈ khi cùng cơ quan.**
3. **"Chuyên ngành thắng" KHÔNG phải quy tắc phổ quát** — nó là điều khoản tự khẳng định của TỪNG luật ("trường hợp luật khác có quy định khác thì áp dụng luật này/luật đó"), encode như statement có nguồn.

### 6.2 Ca chuẩn tier-2 (certificate)

Đ468 BLDS 2015: trần lãi thỏa thuận 20%/năm "trừ trường hợp luật khác có liên quan quy định khác" vs cơ chế lãi suất thỏa thuận TCTD theo Luật Các TCTD + TT39 → không tự phân định được bằng Đ156 → **certificate treo** cho đến NQ 01/2019/NQ-HĐTP (HĐTP TANDTC): HĐ tín dụng của TCTD áp dụng luật chuyên ngành, không áp trần Đ468. Tại as-of < 2019: certificate mở; as-of ≥ 2019: resolved, cite NQ01. NQ01 là **statement giải**, đi qua pending_event → `resolved_by_op`.

### 6.3 Hạng thấp nhất

Công văn giải đáp NHNN, văn bản diễn giải nội bộ SHB: vào kho đúng tư cách **diễn giải có nguồn, không phải quy phạm** — được cite, hạng thấp nhất, là cách hợp thức duy nhất để ngân hàng "chốt một cách đọc an toàn" trong vùng certificate.

### 6.4 Nhãn so sánh nội quy vs pháp quy (miễn trừ Liskov có hướng — D-34)

| Nhãn | Nghĩa | Xử lý |
|---|---|---|
| `mau_thuan` | trái nghĩa vụ/quyền | vào queue, fork ownership |
| `chat_hon_ve_minh` | nội quy siết nghĩa vụ CỦA ngân hàng | = tuân thủ → TỰ LOẠI |
| `chat_hon_ve_doi_tac` | siết yêu cầu VỚI khách hàng | nghi vấn (siết precondition của đối tác có thể phạm nghĩa vụ luật định) → queue |
| `khac_pham_vi` | scope không giao | loại |

## §7. Danh sách bẫy đã trả học phí (extraction/parse/engine PHẢI xử lý)

1. **Unicode NFC/NFD trộn lẫn** trong văn bản VN → normalize NFC ngay cửa vào.
2. **Số hiệu chứa khoảng trắng lỗi** (`32 /2026/TT- NHNN`) → vá regex trước khi word-segment; số hiệu phải thành **một token** trước BM25, không thì BM25 mù.
3. `ngưng hiệu lực` ≠ `bãi bỏ` — hai op kind; LLM hay gộp → few-shot có TT10.
4. Ngày hiệu lực ≠ ngày ban hành; op có thể chạm node **chưa kịp có hiệu lực** (TT10×TT06).
5. `valid_to` theo SỰ KIỆN, không phải ngày (TT10) → pending_event, thiếu là không biểu diễn nổi ca demo trung tâm.
6. Bãi bỏ một op ≠ xóa op — cửa sổ đã hiệu lực phải nguyên vẹn (bẫy viết-lại-lịch-sử; golden class `op_on_op`).
7. Hai op cùng `valid_from` cùng hạng là chuyện thường (TT06+TT10 cùng 01/09/2023) → tie-break canonical (issued_date, seq), KHÔNG phải thứ tự nạp; đảo thứ tự nạp không được đổi kết quả.
8. Binding "Thông tư này" trong/ngoài quote (§5.3).
9. Omnibus đổi namespace theo Chương (§5.4).
10. Hiệu lực **phân kỳ theo chủ đề** trong một văn bản → per-op review.
11. Op chỉ sửa **TIÊU ĐỀ**, hoặc nhắm **Phụ lục**.
12. Đừng chunk theo token — node cây LÀ chunk (D-17).
13. Nội quy CHẶT HƠN thông tư không phải mâu thuẫn — nhưng hỏi chặt hơn VỚI AI (§6.4).
14. **Contamination qua điều khoản sửa đổi**: text bị treo/thay sống nguyên văn trong node `amending` đang-hiệu-lực của văn bản sửa đổi → node role `amending` LOẠI khỏi retrieval (D-05); nội dung chỉ sống qua op. Điều khoản chuyển tiếp/hiệu lực của văn bản sửa đổi KHÔNG phải `amending` (chúng mang quy phạm thật, retrievable, role `transition`/`effectivity`).
15. **Replace cấp cha tái cấu trúc con** → con sinh birth-id MỚI + tương chiếu non-binding (D-08); timeline không được trình bày "điểm c cũ → điểm c mới" như cùng một danh tính.
16. VBHN (văn bản hợp nhất) **không có giá trị pháp lý chính thức** — chỉ dùng làm differential oracle (D-22); artifact VBHN gắn `is_oracle`, không vào retrieval.
17. Seq trong artifact quyết định thứ tự áp trong cùng văn bản (Điều 5 chèn khoản vào Điều 11 rồi Điều 6 thay cụm từ "tại Điều 11" — áp theo thứ tự xuất hiện).
18. Bản text trên web có artifact OCR — đối chiếu bản gốc Công báo trước khi tin (D-43).

## §8. Corpus có chủ quyền vs không chủ quyền

- **Corpus ngoài** (SBV/CP/QH/Công báo): chỉ *tiêu thụ, parse, phê chuẩn, chứng thực coverage*. Vai của hệ: "you are the judge program, not Wizards" — sản phẩm là chuỗi dẫn xuất + chứng chỉ, không phải quyền sửa văn bản. Kênh có số tuần tự (Công báo) → dò gap bằng máy.
- **Corpus trong** (quy định/quy trình/biểu mẫu SHB): có chủ quyền — đường dài ép cấu trúc lúc soạn (doctrine D-50); hackathon: parse như corpus ngoài, gắn `owner` (phòng ban) để blast-radius có địa chỉ. Biểu mẫu là node/doc hạng nhất, nhận staleness propagation (D-36).

## §9. Glossary (VN → gloss cho AI)

| Thuật ngữ | Nghĩa |
|---|---|
| Thông tư (TT) | circular — văn bản cấp Bộ/NHNN |
| Nghị định (NĐ-CP) | government decree |
| Luật / Nghị quyết QH | statute / National Assembly resolution |
| Nghị quyết HĐTP (NQ-HĐTP) | Judicial Council resolution — diễn giải áp dụng pháp luật của TANDTC |
| VBQPPL | văn bản quy phạm pháp luật — legal normative document |
| VBHN | văn bản hợp nhất — non-authoritative consolidated text |
| Công báo | official gazette, đánh số tuần tự |
| Công văn | official letter — hướng dẫn/diễn giải, KHÔNG phải quy phạm |
| Sửa đổi, bổ sung | amend & supplement |
| Bãi bỏ / hết hiệu lực | repeal |
| Ngưng hiệu lực | suspend (khả hồi) |
| Đính chính | erratum — hồi tố |
| Điều khoản chuyển tiếp | transitional provision (grandfathering) |
| Điều khoản thi hành | implementation/effectivity clause — nơi op hay nấp |
| NHNN / SBV | Ngân hàng Nhà nước — State Bank of Vietnam |
| TCTD | tổ chức tín dụng — credit institution |
| LDR / KBNN | loan-to-deposit ratio / Kho bạc Nhà nước (State Treasury) |
