# TRAPS — Bản đồ bẫy của corpus

> Tài liệu QA: mỗi dòng = một bẫy ĐÃ GIEO (hoặc có sẵn trong văn bản thật), vị trí chính xác,
> số bẫy theo danh sách 02-DOMAIN-SPEC §7, và golden item (04 §2.2) sẽ chấm nó.
> "Thật" = bẫy có sẵn trong văn bản pháp quy thật; "Gieo" = fixture synthetic cố tình cài.

## 1. Bẫy trong văn bản THẬT

| Văn bản | Vị trí | Bẫy | §7 | Golden |
|---|---|---|---|---|
| 06/2023/TT-NHNN | k2 Đ1 (thay toàn bộ Đ8 TT39: 6 khoản → 10 khoản) | replace-cấp-cha tái cấu trúc con → con birth-id mới, tương chiếu non-binding | 15 | CUR-01, SUS-* |
| 06/2023/TT-NHNN | Đ2 = "Bãi bỏ khoản 5 Điều 7 của Thông tư số 39/2016/TT-NHNN." | op nằm TRỌN trong TIÊU ĐỀ, điều một dòng | 11 | SEM-01 (k5 Đ7 là node stale của QT-TD-01) |
| 06/2023/TT-NHNN | Đ1 k1–k11 (11 khoản quote) | contamination: text mới (k8–10 Đ8…) sống nguyên văn trong node amending đang-hiệu-lực | 14 | CTM-01, CTM-02 |
| 06/2023/TT-NHNN | Đ4 k2 | grandfather: ký trước 01/09/2023 tiếp tục theo thỏa thuận (+ sửa đổi sau phải theo mới) | — | GF-01, GF-02 |
| 06/2023/TT-NHNN × 10/2023/TT-NHNN | hiệu lực cùng ngày 01/09/2023, cùng hạng | 2 op cùng valid_from → tie-break canonical (issued_date 28/06 < 23/08), không phụ thuộc thứ tự nạp | 7 | test_determinism_permutation |
| 10/2023/TT-NHNN | Đ1 | `ngưng hiệu lực` ≠ `bãi bỏ`; đích là node CHƯA KỊP có hiệu lực (TT06 chưa đến 01/09) → operative interval k8–10 = ∅ | 3, 4 | SUS-01/02/03 |
| 10/2023/TT-NHNN | Đ1, cụm "cho đến ngày có hiệu lực thi hành của văn bản quy phạm pháp luật mới quy định về các vấn đề này" | valid_to theo SỰ KIỆN chưa định danh → pending_event | 5 | SUS-01 (flag open_suspension), test_pending_sweep |
| 10/2023/TT-NHNN | Đ1: "khoản 8, khoản 9 và khoản 10 Điều 8" | enumeration → PHẢI tách 3 op | — | exit test extraction |
| 12/2024/TT-NHNN | Đ4 k2 = "Bãi bỏ khoản 8, điểm b khoản 9 Điều 1 Thông tư số 06/2023/TT-NHNN." | **op-nhắm-op THẬT** (đích là 2 điều khoản sửa đổi của TT06); cửa sổ 09/2023→07/2024 bất khả xâm phạm | 6 | history_integrity gate |
| 12/2024/TT-NHNN | Đ1 k6: "điểm b(iii) khoản 2… Điều 22 … đã được sửa đổi, bổ sung bởi điểm c, d khoản 6 Điều 1 Thông tư số 06/2023/TT-NHNN" | target cấp TIẾT + chain-cite qua op trước | — | CUR-02 |
| 12/2024/TT-NHNN | Đ2: "Điều 32g … đã được sửa đổi, bổ sung bởi khoản 11 Điều 1 TT06" | repeal node do op khác SINH RA | — | timeline Đ32g |
| 26/2022/TT-NHNN | k1 Đ1 (điểm a k4 Đ20 TT22: lộ trình tiền gửi KBNN 50%→60%→80%→100% theo NĂM trong new_text) | các mốc thời gian nằm TRONG text — không phải op-date; window nguyên vẹn khi op bị TT08/2026 bãi bỏ | — | **PIT-01** (as_of 2024-03: 60%), **PIT-02**, **OPO-01** |
| 26/2022/TT-NHNN | k2 Đ1 = thay khoản 2 Điều 24 TT22 (chính nó là khoản sửa đổi Đ23 TT41) | **amend-nhắm-op THẬT** + quote LỒNG quote ('' bọc “”) | 6 | timeline Đ23 TT41 |
| 26/2022/TT-NHNN | Đ3: hiệu lực 31/12/2022 = ngày ban hành | same-day effectivity (không có 45 ngày) | 4 | — |
| 22/2019/TT-NHNN | k2 Đ24 (Hiệu lực thi hành) sửa Đ23 TT41 | op NẤP trong điều "Hiệu lực thi hành" | — (D-18) | exit test extraction |
| 22/2019/TT-NHNN | k3 Đ24: danh sách gạch-đầu-dòng 5 văn bản hết hiệu lực (TT36/2014…Đ4 TT13/2019) | mass repeal dạng dash-list, có repeal MỘT-điều-của-văn-bản-khác | — | — |
| 22/2019/TT-NHNN | Đ3 k16… tiết (i)…(xiii); Đ7 k1b (i)(ii)(iii) | tiết dày đặc; điểm đ; công thức LDR vỡ dòng (k1 Đ20 mất dòng "1.") | 18 | R-4 parser exit |
| 39/2016/TT-NHNN | Đ33 k2 a–h: 8 văn bản hết hiệu lực (QĐ 1627/2001…) | norm succession (QĐ1627 → TT39) + repeal ngoài kho | — | norm 'hoạt động cho vay' |
| 39/2016/TT-NHNN | Đ26 k1: "quy định của NHNN về các giới hạn, tỷ lệ bảo đảm an toàn…" | cite theo MẢNG không số hiệu → Norm (chu_de), nuôi blast-radius | — (D-09) | — |
| 91/2015/QH13 | Đ468 k1: "…không được vượt quá 20%/năm…, **trừ trường hợp luật khác có liên quan quy định khác**" | ngoại lệ mở → conflict tier-2 với cơ chế lãi TCTD, treo đến NQ01/2019 | — | **CFL-01, CFL-02** |
| 01/2019/NQ-HĐTP | Đ7 k2 | statement GIẢI certificate (không áp trần BLDS cho HĐTD) — đóng pending_event, không phải quy phạm sửa đổi | — | CFL-01 (resolved), CFL-02 (as_of 2018: certificate mở) |
| 32/2024/QH15 | Đ209 k2: "Khoản 3 Điều 200 và khoản 15 Điều 210 … có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025." | hiệu lực PHÂN KỲ THẬT trong 1 văn bản | 10 | (đối chứng thật cho PEN-01) |
| 32/2024/QH15 | Đ209 k3: thay 47/2010 "trừ quy định tại các khoản 1, 2, 3, 4, 8, 9, 12 và 14 Điều 210" | norm succession CÓ NGOẠI LỆ + Đ210 k2 grandfather thật (mốc 30/06/2025 cho HĐ không thời hạn) | — | GF-* đối chứng |
| 47/2010/QH12 | Đ3 k2 | "chuyên ngành thắng" là điều khoản TỰ KHẲNG ĐỊNH của luật, không phải quy tắc phổ quát → encode statement (D-15) | — (§6.1) | CFL-01 lý lẽ |
| 52/2025/TT-NHNN | toàn bộ (ban hành 25/12/2025, sau ngày cắt danh mục 04) | văn bản PHÁT HIỆN THÊM qua VBHN — thiếu nó oracle diff lệch | — | test_oracle_diff |
| 4033/QĐ-NHNN | Đ1: đính chính "ngày làm việc" → "ngày" tại Đ1 TT52 | **dinh_chinh THẬT**, hồi tố về đầu cửa sổ (25/12/2025); VBHN-06 đã phản ánh bản đính chính | — (D-12) | DCH đối chứng thật |
| VBHN 21 + 06 | footnote "[14][15][16]…" (k8–10 ngưng hiệu lực), "[5] Cho vay là…" | provenance ngoặc để cross-validation 02 §5.5; VBHN là oracle — KHÔNG retrieval | 16 | test_oracle_diff |
| tt-06 text | "Điều 32c. Dư nự cho vay", "thiêt lập", "phưong tiện" | artifact transcription — đối chiếu Công báo trước khi tin | 18 | fuzzy-match verifier ≥0.9 |
| tt-22 text | header căn cứ vỡ dòng 2 cột ("…ngày 16 tháng 6 năm" / "2010;") | header 2 cột vỡ dòng — R-3 gộp | 18 | R-4 |

## 2. Bẫy GIEO trong fixture synthetic

| Văn bản | Vị trí | Bẫy | §7 | Golden |
|---|---|---|---|---|
| 08/2026/TT-NHNN | Đ2: "Bãi bỏ khoản 1 Điều 1 Thông tư số 26/2022/TT-NHNN; điểm a khoản 4 Điều 20 Thông tư số 22/2019/TT-NHNN tiếp tục thực hiện theo quy định tại Thông tư số 22/2019/TT-NHNN." | **repeal-nhắm-op** hiệu lực 01/01/2026: đóng op TT26 TỪ ĐÓ TRỞ ĐI; cửa sổ 31/12/2022→01/01/2026 nguyên vẹn — viết-lại-lịch-sử = FAIL; từ 01/01/2026 điểm a k4 Đ20 TT22 hồi về text gốc 2019, revert có CĂN CỨ VĂN BẢN tường minh (vế sau cùng câu là TUYÊN BỐ/dẫn chiếu — KHÔNG sinh op riêng, chỉ sinh edge pinpoint) | 6 | **OPO-01, PIT-01, PIT-02** (history_integrity, test_window_inviolability) |
| 08/2026/TT-NHNN | Đ1: sửa điểm b k4 Đ20 TT22 | amend điểm thường — đối chứng cùng-điều-khác-điểm với op-nhắm-op | — | PIT-02 phụ |
| 08/2026/TT-NHNN | Đ4: hiệu lực CÙNG NGÀY ban hành 01/01/2026 + câu "ban hành theo trình tự, thủ tục rút gọn" | same-day hợp lệ qua trình tự rút gọn (Đ151 Luật BHVBQPPL; mirror TT26 thật); ngày 01/01 khớp mốc lộ trình TT26; TT28/2026 Đ3 cũng có câu rút gọn (cách ban hành 20 ngày < 45) | 4 | — |
| 28/2026/TT-NHNN | k1 Đ1: "Bổ sung Điều 7a vào sau Điều 7" TT22 | alias drift Điều 7a (INV-11, test_alias_drift) | — (D-07) | timeline alias |
| 28/2026/TT-NHNN | TRONG quote Đ7a: "…quy định tại Điều 6 **Thông tư này**" / "Điều 7 Thông tư này" | binding "Thông tư này" TRONG quote → TT22 (ĐÍCH), không phải TT28; NGOÀI quote (Đ3 TT28) → TT28 | 8 | exit test extraction |
| 28/2026/TT-NHNN | k2 Đ1: thay cụm từ "NHNN chi nhánh tỉnh, thành phố trực thuộc Trung ương" → "NHNN chi nhánh Khu vực" TẠI k3 Đ7 và k2 Đ23 | phrase-replace đa điều → curator materialize 2 op (D-21); cụm CŨNG xuất hiện ở Đ24-k2-quote và Đ25 TT22 — KHÔNG được tự lan | — (D-21) | exit test extraction |
| 28/2026/TT-NHNN | trong quote Đ7a k1: "10 (mười) ngày làm việc" | con số sẽ bị DC-01/2026 đính chính → 05 | — | **DCH-01** |
| 32/2026/TT-NHNN | header "Số: 32 /2026/TT- NHNN" | số hiệu chứa KHOẢNG TRẮNG LỖI ngay bản gốc — vá trước tokenize, không thì BM25 mù | 2 | retrieval smoke |
| 32/2026/TT-NHNN | Đ6 k2: "Thông tư này thay thế Thông tư số 15/2020/TT-NHNN…" | norm succession toàn văn bản (văn bản cũ ngoài kho — giống QĐ1627); Đ6 k3 tương chiếu dẫn chiếu cũ→mới NON-BINDING (D-08) | 15 | norm đại-lý-thanh-toán |
| 32/2026/TT-NHNN | Đ6 k4: "Các quy định trước đây trái với Thông tư này hết hiệu lực thi hành." | blanket derogation — KHÔNG mutate, seed conflict screening (D-14) | — | — |
| 32/2026/TT-NHNN | Đ7: ký trước 01/07/2026 **VÀ** không sửa đổi từ 01/07/2026 | grandfather 2 TẦNG đúng DSL D-25 → 2 version song song khác scope | — (D-25) | **GF-03**, test_scope_split |
| 32/2026/TT-NHNN | Đ3 k2: "…quy định của NHNN về hoạt động cho vay của TCTD…" | cite theo MẢNG → Norm (không gate closure, nuôi blast-radius) | — (D-09) | GF-03 văn cảnh |
| 32/2026/TT-NHNN | Đ4 k1: điểm a,b,c,d,**đ** | bảng chữ cái tiếng Việt có đ | 18 | R-4 |
| 11/2026/TT-NHNN | Chương I–V, mỗi chương sửa 1 TT (TT39, TT22, TT41, TT26, TT12) | omnibus namespace theo CHƯƠNG; k1 Đ1 cite "Điều 9" TRẦN → context-stack = Đ9 TT39 (carry-từ-tiêu-đề-văn-bản KHÔNG đủ) | 9 | exit test extraction |
| 11/2026/TT-NHNN | k2 Đ7: "Các quy định về Phiếu lý lịch tư pháp tại Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026." | hiệu lực PHÂN KỲ THEO CHỦ ĐỀ (≠ 01/03/2026); map chủ đề→op là NGỮ NGHĨA (per-op review D-19) | 10 | **PEN-01, PEN-02** |
| 11/2026/TT-NHNN | k2 Đ1: "Sửa đổi tên Điều 14" TT39 | op CHỈ sửa TIÊU ĐỀ (target_part=heading) | 11 | exit test extraction |
| 11/2026/TT-NHNN | k1 Đ3: "Bổ sung khoản 3 vào Phụ lục 3 … Thông tư số 41/2016/TT-NHNN" | op nhắm PHỤ LỤC (node hạng nhất, content blob D-49) | 11 | exit test extraction |
| 11/2026/TT-NHNN | k1 Đ2, TRONG quote k5 Đ20 TT22 mới: "…tỷ lệ an toàn vốn tối thiểu quy định tại **Điều 9 Thông tư này**…" | binding trong quote → Đ9 TT22; Đ9 TT22 NGOÀI trích đoạn corpus → mandatory edge unresolved → Tier D closure_incomplete | 8 + cắt alias | **CLO-02** |
| 11/2026/TT-NHNN | Đ6: bãi bỏ TT97/2019, TT98/2020, k3 Đ3 TT99/2021 (đều fiction ngoài kho) | mass-repeal điều riêng; số 9x = quy ước "không tồn tại" (khớp ABS-02 dùng TT 99/2025) | — | **PEN-02** văn cảnh |
| 11/2026/TT-NHNN | Đ4 sửa Đ2 TT26 (điều KHÔNG-amending của một thông tư sửa đổi) | đối chứng: amend node thường trong amending-doc ≠ op-nhắm-op | — | phân biệt trong extraction |
| DC-01/2026 | toàn văn: đính chính "10 (mười)" → "05 (năm)" tại k1 Đ7a TT22 (bổ sung bởi k1 Đ1 TT28) | dinh_chinh HỒI TỐ về ĐẦU cửa sổ 25/01/2026 (≠ ngày công văn 10/02/2026); công văn KHÔNG có Điều (counts=0) | — (D-12) | **DCH-01** (as_of 2026-02-01 → trả 05), test_dinh_chinh_retroactive |
| QT-TD-01/SHB | k2 Đ3 ("Mục 3.2" theo 04 §1.2): "05 (năm) điều kiện… theo khoản 5 Điều 7 TT39" | STALE CỐ TÌNH: k5 Đ7 bị TT06 Đ2 bãi bỏ 01/09/2023 (+ k3 Đ7 được TT12 nới); doc ban hành 03/2023 → stale tự nhiên, không lộ liễu | — | **SEM-01** (blast-radius → notice owner "Khối KHCN — Phòng CSTD") |
| QT-TD-01/SHB | căn cứ 2: "các quy định của NHNN về hoạt động cho vay…" | cite theo mảng → Norm | — | SEM-01 văn cảnh |
| MB-HD-01/SHB | Đ4 k1 (dẫn chiếu động) + k2 (chuyển tiếp có mốc TT06) | biểu mẫu nhận staleness propagation (D-36); form là doc hạng nhất | — | forms staleness |
| CS-LS-01/SHB | k2 Đ3: SHB tự buộc cung cấp bảng tính lãi TRƯỚC ≥ 03 ngày làm việc | siết nghĩa vụ CỦA SHB → `chat_hon_ve_minh` → Liskov-exempt, TỰ LOẠI, KHÔNG conflict | 13 | **CFL-04** |
| CS-LS-01/SHB | k1 Đ4: MỌI khách (kể cả khoản giá trị nhỏ) phải nộp phương án sử dụng vốn khả thi | siết yêu cầu VỚI KHÁCH, trái miễn trừ k3 Đ7 TT39 (bản-sau-TT12) → `chat_hon_ve_doi_tac` → CANDIDATE conflict, fork internal_external | 13 | **CFL-03** |
| GT-468-01/SHB | Đ2 (cách hiểu) + Đ3 (tự tuyên bố không phải quy phạm) | diễn giải nội bộ = statement hạng thấp nhất, được cite — cách hợp thức "chốt cách đọc" trong vùng certificate | — (§6.3) | CFL-01 chuỗi cite |

## 3. Ghi chú mapping golden → fixture (kiểm tra chéo verification #3)

| Golden | Fixture + vị trí | Có trong TRAPS |
|---|---|---|
| GF-03 | 32/2026 Đ7 (2 predicate) | ✓ |
| OPO-01, PIT-01, PIT-02 | 08/2026 Đ2 × 26/2022 k1 Đ1 × 22/2019 Đ20 | ✓ |
| PEN-01, PEN-02 | 11/2026 k2 Đ7 + k1 Đ1 | ✓ |
| DCH-01 | DC-01/2026 × 28/2026 k1 Đ1 | ✓ |
| CFL-03, CFL-04 | CS-LS-01 Đ4 k1 / Đ3 k2 | ✓ |
| SEM-01 | QT-TD-01 k2 Đ3 | ✓ |
| CTM-01, CTM-02 | 06/2023 Đ1 k1–k11 (amending_nodes trong manifest) | ✓ |
| CLO-02 | 11/2026 k1 Đ2 (Điều 9 TT22 bị cắt alias) | ✓ |
| SUS-01/02/03 | 10/2023 Đ1 (thật) | ✓ |
| GF-01, GF-02 | 06/2023 Đ4 k2 (thật) | ✓ |
| CFL-01, CFL-02 | 91/2015 Đ468 × 47/2010 Đ91 × 01/2019 Đ7 (thật) | ✓ |
| CUR-01/02/03 | 39/2016 (+06+12+52) — chuỗi amend thật | ✓ |
| ABS-02 | quy ước số 9x/không tồn tại (11/2026 Đ6 dùng 97–99) | ✓ |
