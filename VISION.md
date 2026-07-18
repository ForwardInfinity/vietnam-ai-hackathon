# Bản thiết kế: Hệ tri thức pháp quy SHB

*(mỗi cơ chế kèm nguồn gốc — field đã trả giá để học nó)*

## 0. Nguyên lý sinh kiến trúc

Toàn bộ thiết kế suy ra từ hai đường cắt:

**Cắt theo chủ quyền.** Corpus ngoài (SBV, Chính phủ, Công báo) — không có quyền sửa upstream: chỉ *tiêu thụ, parse, phê chuẩn, chứng thực coverage*. Corpus trong (quy định, quy trình, mẫu biểu của chính SHB) — có chủ quyền tuyệt đối: *ép cấu trúc ngay lúc soạn*, xóa một nửa bài toán parse trước khi nó tồn tại (áp cho văn bản mới; khối legacy nội bộ chưa cấu trúc đi qua đường parse-như-corpus-ngoài sau khi kiểm kê — không chặn ingest bằng một cuộc cải cách quy trình). Digital NOTAM chết vì ép encode hạ nguồn; XBRL sống vì regulator ép tag tại nguồn — và bài học iXBRL nói *cách* ép: đường cấu trúc phải dễ hơn Word, tag nhúng trong chính tài liệu người đọc, không bắt nộp song song — nếu không sẽ mọc văn-bản-bóng (file Word chuyền email, "hướng dẫn tạm" qua Zalo) và kênh trong âm thầm thoái hóa về kênh ngoài mà không ai hạ cấp coverage attestation. Với corpus ngoài, bài học MTG nói thẳng vai của ta: *"you are not Wizards; you are the judge program"* — sản phẩm là chuỗi dẫn xuất, chứng chỉ xung đột và escalation có kỷ luật, không phải quyền sửa văn bản.

**Cắt log/view.** Câu trả lời không bao giờ được lấy từ retrieval trên văn bản thô. Văn bản thô là *log*; thứ được index và trích dẫn là *trạng thái hiệu lực đã materialize* do một versioning engine tính ra. LLM chỉ đứng ở hai biên — đề xuất trích xuất lúc nạp, soạn văn lúc trả lời — và cả hai biên đều bị gate bởi tầng hình thức. Nếu chỉ giữ một câu của thiết kế này, giữ câu đó.

## 1. Sơ đồ tổng thể

```
  KÊNH NGOÀI (SBV/CP/Công báo)                 KÊNH TRONG (gazette nội bộ duy nhất)
  quét theo kênh, dò gap theo số Công báo      structured authoring bắt buộc + dual issuance
        │                                             │
        ▼                                             ▼
┌────────────────────────────────────────────────────────────────────┐
│ L0 STORE BẤT BIẾN  artifact content-addressed · tem K (thời điểm   │
│    biết) · coverage ledger per kênh · op-log hash-chained          │
├────────────────────────────────────────────────────────────────────┤
│ L1 PARSE & DANH TÍNH  cây Điều/Khoản/Điểm · birth-id mỗi node ·    │
│    bảng alias (số hiệu↔id, có thời gian tính) · norm-identity      │
├────────────────────────────────────────────────────────────────────┤
│ L2 TRÍCH XUẤT + PHÊ CHUẨN  op đề xuất {amend|repeal|suspend|       │
│    replace|insert} + citation có kiểu → phân loại rủi ro →         │
│    curator ratify · sửa sai = op mới (append-only)                 │
├────────────────────────────────────────────────────────────────────┤
│ L3 VERSIONING ENGINE  fold(ops, precedence(t)) → V(t, s | K)       │
│    piecewise theo scope predicate · suspension giữ node sống ·     │
│    diff với bản hợp nhất ngoài (differential oracle)               │
├────────────────────────────────────────────────────────────────────┤
│ L4 INDEX  BM25 + dense + graph expansion TRÊN SNAPSHOT ·           │
│    where-used liên tục · blast-radius → trigger notices            │
├────────────────────────────────────────────────────────────────────┤
│ L5 TRẢ LỜI  parse câu hỏi → retrieve view → LLM soạn → VERIFIER    │
│    code khớp verbatim → Answer | Conflict | Escalate               │
├────────────────────────────────────────────────────────────────────┤
│ L6 XUNG ĐỘT  3 tầng: precedence tự động / certificate phần dư /    │
│    chương trình SEM đa kênh                                        │
├────────────────────────────────────────────────────────────────────┤
│ L7 VỆ SINH  review-by expiry · scorecard · issuer-pays             │
└────────────────────────────────────────────────────────────────────┘
```

## 2. Mô hình dữ liệu — sáu đối tượng

**Artifact**: file gốc, hash làm địa chỉ, bất biến, tem `K` = thời điểm hệ thống biết đến nó. Ba trục thời gian tách bạch ngay từ schema: ban hành / hiệu lực (cửa sổ, có thể tương lai hoặc hồi tố) / biết-đến. Trục ba là thứ audit hỏi ("lúc giải ngân, ngân hàng *có thể biết* gì?") và là trục mọi RAG thường bỏ quên.

**Node**: đơn vị cây pháp lý (Điều/Khoản/Điểm/Tiết, kể cả Phụ lục; tách tiêu-đề/thân vì toán tử thật nhắm được riêng "tiêu đề điểm d" hay "cuối Phụ lục 04"), nhận **birth-identity** — UUID cấp lúc sinh, không bao giờ tái sử dụng (quy ước CRDT: identifier đã chết không bao giờ tái sinh). Địa chỉ bề mặt ("khoản 2 Điều 8 TT 39/2016") sống trong **bảng alias có thời gian tính**, vì toán tử địa chỉ hóa bằng số thứ tự mà số thứ tự có thể trôi.

**Norm**: danh tính xuyên thay-thế-toàn-văn-bản (TT 39/2016 kế vị QĐ 1627/2001 với tư cách "quy chế cho vay") — một *cạnh được bảo trì*, không phải suy luận (FRBR Work/Expression; quy tắc form-fit-function của PLM: vụ công tắc GM $900M là hình phạt cho việc coi nhẹ nó). Bảo trì *bằng thủ tục*: khai sinh/kế vị/đổi-scope của Norm là một op đi qua đúng hàng đợi phê chuẩn, ba tiêu chí — đối tượng điều chỉnh, phạm vi chủ thể, kế vị được tuyên bố tường minh trong văn bản; ca khó có sẵn trong corpus: TT 06/2023 vừa sửa norm cho-vay vừa *khai sinh* norm cho-vay-điện-tử. Khi thay thế toàn phần, bảng tương chiếu điều-cũ↔điều-mới được lưu nhưng dán nhãn **non-binding** — ô 1-nhiều buộc dẫn xuất lại từ văn bản mới, để lỗi bảng không lan vào "luật" (thực hành correlation table của WCO).

**Operation**: `{type: amend|repeal|suspend|replace|insert|đính-chính, target: node-id | op-id, window: [t₁,t₂), text, scope-predicate?, extractor, confidence, ratified-by?}` — t₂ có thể là **sự kiện chưa định danh** thay vì ngày ("cho đến ngày có hiệu lực thi hành của văn bản QPPL mới" — chính TT10) — mọi t₂-theo-sự-kiện vào **pending-event registry**, re-evaluate mỗi lần nạp, và đóng cửa sổ là một op được phê chuẩn (phán đoán "văn bản X chính là sự kiện đang chờ" là ngữ nghĩa — máy đề xuất, người chốt; certificate chờ statement giải dùng chung registry — thiếu nó, TT10 nạp đúng nhưng không bao giờ đóng được); đính chính có hiệu lực hồi tố về đầu cửa sổ. Ba tính chất bắt buộc: (1) **suspend ≠ delete** — node bị ngưng vẫn sống với trạng thái treo, vì ngưng hiệu lực cho phép hồi sinh (TT 10/2023 treo khoản 8-9-10 Điều 8 mà TT 06/2023 vừa thêm — corpus demo có sẵn ca này); (2) op có thể target op khác (sửa cái sửa) — và **bãi bỏ một op chỉ đóng hiệu lực của nó từ đó trở đi**, cửa sổ đã qua bất khả xâm phạm: bãi bỏ op không phải xóa op, nếu không point-in-time query bị viết lại lịch sử; (3) op đã phê chuẩn là bất biến — sửa lỗi trích xuất bằng op mới đè lên, để chính lịch sử trích xuất cũng audit được.

**Edge**: citation có kiểu — `định-nghĩa | thẩm-quyền | ngoại-lệ | chủ-đề | frontier` (chủ-đề trỏ vào Norm theo mảng — "thực hiện theo quy định của NHNN về hoạt động cho vay…" không mang số hiệu nhưng blast-radius phải thấy; frontier trỏ ra ngoài kho: Basel, điều ước). Edge dẫn xuất theo phiên bản node — text đổi thì citation đổi. Kiểu edge không phải trang trí: nó là đầu vào của bộ phân loại rủi ro ở L2.

**Snapshot**: phiên bản node đã materialize, khóa `(node-id, valid-interval, scope-predicate, K)` — engine trả `V(t, s | K)` thì chiều s không được rơi khỏi khóa: hai version cùng interval khác scope song song tồn tại (grandfathering) — kèm con trỏ provenance về chuỗi op.

## 3. L2 — Cửa khẩu thứ nhất, nơi hệ thống thắng hay thua

Lỗ nguy hiểm nhất mà critic C1 tìm ra: nếu trích xuất sai mà không kiểm được, determinism của engine trở thành *bảo hành cho sự sai có thể tái lập* — hai lần recompute cùng ra một câu trả lời sai, khớp bit. Nên cửa khẩu này thiết kế như một **phòng biên tập critical edition**, không phải một pipeline:

- Extractor (rule-based cho khung + LLM cho ngữ nghĩa; ngôn ngữ sửa đổi tiếng Việt gần công thức — "sửa đổi, bổ sung", "bãi bỏ", "ngưng hiệu lực" — nên precision đạt được cao) chỉ *đề xuất* op.
- **Phân loại rủi ro trước khi phê chuẩn** (chuyển giao đắt nhất từ hồ sơ livepatching): op mà target có inbound citation *kiểu định-nghĩa* = "thay đổi layout" — sửa nó là sửa ngữ nghĩa của mọi node đang trỏ vào, bắt buộc người duyệt + máy móc chuyển tiếp; op chỉ sửa nội dung mệnh lệnh dưới các định nghĩa ổn định = "vá thân hàm", vào **batch-ratify**: người phê chuẩn cả lớp kèm invariant mẫu máy verify được từng op + spot-check — chữ ký người phủ 100% log, máy không bao giờ tự mở cổng (auto-ratify là câu một auditor SBV sẽ khoanh đỏ; còn ép per-op cho trăm op cơ học của một omnibus thoái hóa thành rubber-stamp — tệ hơn sampling trung thực vì nó rửa output máy thành "đã người duyệt"). Đồ thị citation có kiểu chính là bộ phân tích tĩnh làm việc phân loại này — vai của nó là xếp hàng đợi và định tuyến notice, không phải mở cổng qua mặt người.
- Mọi mệnh đề hệ thống phát ra sau này mang **nhãn tầng khẳng định**: biên-tập-viên-phê-chuẩn ≠ máy-đề-xuất-chưa-duyệt, hiển thị khác nhau (Shepard's/KeyCite tách cờ editorial khỏi cờ thuật toán — provenance-typing của tín hiệu).

## 4. L3 — Versioning engine

`V(t, s | K)` = fold các op đã phê chuẩn theo thứ tự `(hạng thẩm quyền, thời gian, chuyên ngành)` — chính các quy tắc ưu tiên cũng là statement trong kho với cửa sổ hiệu lực riêng (Luật BHVBQPPL tự nó từng được thay thế). Tie-break bằng dữ kiện canonical trước — ngày ban hành, thứ tự xuất hiện trong văn bản (hai op cùng ngày hiệu lực cùng hạng là chuyện thường: TT06 và TT10 cùng 01/09/2023) — rồi mới đến thứ tự tiếp nhận làm chốt chặn cuối: ta có một sequencer trung tâm tự nhiên, và bài học OT nói dùng nó thay vì xây đại số merge đối xứng (mọi thuật toán OT ngang hàng từng công bố đều bị phản chứng khi kiểm tra bằng máy).

- **Grandfathering là scope predicate, không phải phiên bản đặc biệt.** Điều khoản chuyển tiếp trích thành vị từ trên chủ thể; vì chủ thể thường không xác định lúc hỏi, **câu trả lời mặc định là piecewise**: "hợp đồng ký trước 01/09/2023 chưa gia hạn → quy định cũ; còn lại → quy định mới". Nhiều phiên bản sống song song vô hạn qua một lõi chung — mô hình Rust editions, không phải hot-patch.
- **Dual issuance cho corpus trong** (bắt buộc bằng quy chế): văn bản sửa đổi nội bộ phải ship kèm bản hợp nhất kết quả — op có thẩm quyền về *ý định và phạm vi*, bản hợp nhất về *nội dung*, như merge commit lưu cả cha lẫn kết quả.
- **Differential oracle cho corpus ngoài**: engine tự materialize rồi diff với văn bản hợp nhất không chính thức (văn bản hợp nhất nhà nước, LuatVietnam/TVPL). Lệch → hàng đợi phân xử: lỗi parser, lỗi precedence, hay lỗi của chính nhà hợp nhất. Oracle là chuông báo, không phải chân lý — các bản hợp nhất độc lập sai *tương quan* đúng ở các ca diễn giải khó (kết quả N-version của Knight & Leveson).

## 5. L5 — Đối tượng trả lời

Kiểu trả về của toàn hệ không phải `string`:

```
Answer {
  content:      piecewise theo (khoảng-t × lớp-chủ-thể)
  provenance:   node → chuỗi op → artifact gốc
                ("Điều 8 TT 39/2016, sửa bởi TT 06/2023,
                  khoản 8-10 ngưng hiệu lực bởi TT 10/2023")
  freshness:    "coverage: Công báo đến số N ngày D; registry nội bộ đến D′"
  ttl:          đặt theo động học sửa đổi ĐO ĐƯỢC của từng mảng
  audience:     employee | customer
}  |  Conflict(certificate | escalation)  |  Escalate(lý do)
```

Bốn quyết định ở đây: (1) LLM soạn từ view, rồi **verifier bằng code** đối chiếu verbatim từng trích dẫn với snapshot — model đề xuất, tầng hình thức định đoạt; (2) freshness là **chứng thực coverage tương đối với kênh liệt kê được** (số Công báo tuần tự cho phép dò gap), không phải lời hứa về thế giới; (3) TTL không bốc thuốc — đo tần suất và biên độ sửa đổi thật của từng mảng (tam giác actuarial áp vào lịch sử op của chính hệ), recheck rẻ bằng so fingerprint phiên bản node, không recompute; (4) với khách hàng, corpus đã được **lọc trong tầng hình thức** (tài liệu nội bộ không tồn tại đối với retrieval của họ), câu trả lời bảo thủ, và **escalation là một đầu ra hạng nhất đáng trọng** — ranh giới thông-tin/tư-vấn của thủ thư luật, không phải failure mode.

## 6. L6 — Ba tầng xung đột, ba lời hứa khác nhau

**Tầng 1 — tự động, hứa chắc**: quy tắc đã luật hóa áp thẳng — cấp trên thắng; sau thắng *chỉ khi cùng cơ quan ban hành* (Đ156 Luật BHVBQPPL). "Chuyên ngành thắng" không phải quy tắc phổ quát: nó là điều khoản tự khẳng định của từng luật, encode như statement có nguồn — ca Đ468 BLDS vs TT39 phải chờ NQ 01/2019 chính là bằng chứng loại xung đột đó thuộc tầng 2, không phải tầng 1. Đây là sản phẩm, không phải vi phạm tính trung lập.

**Tầng 2 — phần dư, hứa chứng chỉ**: fold không ra kết quả duy nhất → **conflict certificate** tối thiểu kiểu unsat-core (bộ node + lý do không so sánh được), tồn tại như hồ sơ hạng nhất cho đến khi có statement mới giải nó — mô hình Điều 468 BLDS vs lãi suất TT39 treo đến NQ 01/2019. Nhân viên thấy certificate; khách hàng được escalate. Nếu ngân hàng muốn "chốt một cách đọc an toàn", cách hợp thức duy nhất: ban hành **văn bản diễn giải nội bộ** — statement hạng thấp nhất, vào log, được cite như mọi statement khác (công văn giải đáp của NHNN cũng vào kho đúng tư cách này: diễn giải có nguồn, không phải quy phạm). Hệ thống không bao giờ tự phân xử vùng mà chỉ thẩm quyền mới phân xử được ("appoint an interpreter and you have built a court").

**Tầng 3 — mâu thuẫn không link (SEM), hứa chương trình chứ không hứa oracle**: quy trình nội bộ vẫn chỉ dẫn theo thông tư đã sửa — không chung địa chỉ, fold mù. Mười hai field xác nhận: *không ai tự động hóa được máy dò này; ai cũng mua phát hiện bằng xác chết*. Nên deliver dưới dạng bốn kênh chồng nhau: (a) khi op được phê chuẩn → **blast-radius** qua where-used (index bảo trì liên tục, không tính on-demand) → trigger notice cho *chủ có tên* của từng tài liệu bị ảnh hưởng, **phân tầng severity**: interruptive-bắt-ack là ngoại lệ hiếm, còn lại vào digest — blast-radius phẳng của một omnibus là bão ack → mù học được, đúng cái chết NOTAM; mô hình 50.59 của điện hạt nhân là graded screening chứ không phải ack phẳng: mọi thay đổi bị soi against nội quy *dù nó không cite*; (b) **invariant thực thi được** do compliance viết dần (trần lãi suất, tỷ lệ an toàn, định nghĩa chéo) chạy trên effective state sau mỗi lần nạp — merge-queue/CI: máy dò công nghiệp duy nhất từng có; (c) LLM đề xuất cặp nghi mâu thuẫn theo cụm chủ đề, offline, gán một trong bốn nhãn trước khi vào hàng đợi người xác nhận: *mâu-thuẫn / chặt-hơn-về-mình / chặt-hơn-về-đối-tác / khác-phạm-vi* — miễn trừ Liskov: nội quy siết nghĩa vụ của chính ngân hàng là tuân thủ, tự loại khỏi hàng đợi (thiếu nhãn này kênh (c) ngập false positive "chính sách nghiêm hơn thông tư" và chôn curator), nhưng siết *yêu cầu với khách hàng* là nghi vấn — siết precondition của đối tác có thể phạm nghĩa vụ luật định; (d) **kênh phản hồi người đọc** — nút "nghi đã cũ" trên mỗi câu trả lời, vì bài học NOTAM: không có kênh downvote thì văn bản chết trôi nổi mười năm.

## 7. L7 — Vệ sinh: chống lại định lý về sự mục nát

Fact B là định lý, không phải tai nạn: người phát hành không trả giá cho việc không dọn. Chỉ ba cơ chế từng hoạt động ở bất kỳ đâu — **expiry** (mọi văn bản nội bộ mang ngày review-by bắt buộc; quá hạn không tái xác nhận → gắn cờ, hạ hạng hiển thị — systematic review 5 năm của ISO, sunset của Texas), **pricing** (scorecard "nợ vệ sinh" theo phòng ban, công khai nội bộ — shame as a price, thứ duy nhất nhúc nhích được NOTAM; scorecard kiêm cảm biến văn-bản-bóng — phòng ban có tài liệu sống ngoài gazette nội bộ thì coverage attestation kênh trong hạ cấp tương ứng), **issuer-pays** (phòng đổi mẫu/định nghĩa phải chạy blast-radius và cập nhật mọi tài liệu phái sinh — luật monorepo). Và điều kiện tiên quyết học từ cú sập của Retained EU Law Act: **kiểm kê trước, sunset sau** — không thể định giá việc dọn một corpus chưa đếm được.

## 8. Ba điều thiết kế này từ chối làm

1. **Không hứa oracle cho SEM** — chỉ hứa chương trình phát hiện đa kênh với độ trễ và độ phủ đo được.
2. **Không tính vùng diễn giải kiến tạo** — chỗ nghĩa chỉ được *tạo ra* bởi thẩm quyền (tòa, NHNN, khối pháp chế) là chỗ trả về `Escalate`, không phải confidence thấp. Nhầm hai thứ này là "biến phán đoán pháp lý thành data-cleaning".
3. **Không chứng minh freshness với thế giới** — chỉ chứng thực coverage với kênh liệt kê được. Hệ luôn có thể nói "tôi đã quét gì, đến đâu", không bao giờ nói "không có gì tôi chưa biết".

## 9. Thứ tự xây và màn demo

Xây theo thứ tự phụ thuộc, và cũng là thứ tự giá trị: **L1→L2→L3 là nơi thắng cuộc** (parser, trích op, engine); ở L5 phần generation là hàng chợ, còn question compiler (câu hỏi mờ → `(topic, t, s | K)` kèm phát hiện câu-trả-lời-phụ-thuộc-s) thì không — lỗi demo nhìn thấy được mọc ở đó. Corpus demo: cụm TT 39/2016 + TT 06/2023 + TT 10/2023 + Điều 468 BLDS + NQ 01/2019 — đủ cả năm hiện tượng đề bài đòi, toàn ca thật — cộng bộ fixture synthetic (omnibus sửa 13 thông tư, insert điều mới làm trôi alias, bãi bỏ op, thay-cụm-từ, hiệu lực phân kỳ theo chủ đề) phủ kín đại số toán tử; chi tiết trong SPEC. Vạch cắt hai artifact: L0–L6 + benchmark là *cái build được cuối tuần này* — ban giám khảo chấm cái đó; structured authoring bắt buộc, dual issuance, issuer-pays là *học thuyết đề nghị SHB áp dụng*, điều kiện tiên quyết một chữ ký cấp C — phụ lục thuyết phục, không phải deliverable.

Màn benchmark ăn điểm (deliverable "so với RAG thường"): bộ câu hỏi đối kháng ba lớp — (i) đáp án đã đổi do sửa đổi, văn bản cũ khớp từ vựng với câu hỏi còn văn bản sửa thì không: naive RAG trích *tự tin, dẫn nguồn đúng, nguyên văn đúng — và sai*, vượt qua mọi kiểm tra groundedness, hệ này thì trả lời từ snapshot kèm phả hệ; (ii) câu hỏi "tại thời điểm T" và câu hỏi grandfathering ("hợp đồng ký 2021 thì sao?") → câu trả lời piecewise; (iii) một cặp mâu thuẫn thật → certificate thay vì im lặng chọn một bên. Kết màn: bấm nút "văn bản mới về" → op được đề xuất, phê chuẩn, snapshot đổi, trigger notice bắn cho chủ quy trình nội bộ — mười lăm giây cho thấy toàn bộ vòng đời.

Một câu tóm thiết kế, nếu ban giám khảo chỉ nghe một câu: *chúng tôi không xây search engine tốt hơn trên đống văn bản — chúng tôi xây một cỗ máy tính hiệu lực với ba trục thời gian, đặt retrieval lên trên trạng thái nó tính ra, và ở mọi chỗ máy không có thẩm quyền để quyết, nó phát chứng chỉ thay vì phát minh câu trả lời.*