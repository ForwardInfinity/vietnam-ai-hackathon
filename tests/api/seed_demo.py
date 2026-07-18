"""Seed demo/test cho bề mặt F6 — mini-corpus TT39/TT06/TT10 (synthetic=true).

KHÔNG phải logic ingest thật (F3) — đây là fixture dữ liệu để test contract API,
chụp screenshot UI và demo cục bộ. UUID cố định để test ổn định.

Chạy tay:  uv run python -m tests.api.seed_demo "postgresql://lawstate:lawstate@localhost:55432/lawstate" [--reset]
Story khớp docs/00 §2:
  - TT39 Đ8k2 v1 (2017) → v2 (TT06, hiệu lực 01/09/2023, op ratified per-op có người ký)
  - TT39 Đ8k8 do TT06 CHÈN, bị TT10 NGƯNG đúng ngày lẽ ra hiệu lực → version active KHÔNG BAO GIỜ tồn tại
  - pending_event mở "văn bản QPPL mới có hiệu lực" (D-11)
  - conflict tier-2 Đ468 BLDS vs TT39 (open)
  - queue: 1 op definitional (per-op) + 3 op cơ học "10→07 ngày làm việc" (batch-eligible)
  - QT-TD-01 nội bộ (internal) chứa marker 'LSNB-2026-MAT-7d3f' — INV-12 pentest soi marker này
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone

import psycopg

INTERNAL_MARKER = "LSNB-2026-MAT-7d3f"

RUN_ID = "11111111-1111-4111-8111-111111111111"

# Nodes
N_D8K2 = "aaaaaaaa-0000-4000-8000-000000000001"   # TT39 dieu:8/khoan:2 (rule)
N_D2K5 = "aaaaaaaa-0000-4000-8000-000000000002"   # TT39 dieu:2/khoan:5 (definition)
N_D8K8 = "aaaaaaaa-0000-4000-8000-000000000003"   # TT39 dieu:8/khoan:8 (insert bởi TT06, treo bởi TT10)
N_TT06_AMD = "aaaaaaaa-0000-4000-8000-000000000004"  # TT06 dieu:1/khoan:3 (role amending)
N_QT3 = "aaaaaaaa-0000-4000-8000-000000000005"    # QT-TD-01 dieu:3 (internal)
N_QT4 = "aaaaaaaa-0000-4000-8000-000000000006"    # QT-TD-01 dieu:4 (internal)
N_QT5 = "aaaaaaaa-0000-4000-8000-000000000007"    # QT-TD-01 dieu:5 (internal)

# Ops
OP_AMEND_D8K2 = "bbbbbbbb-0000-4000-8000-000000000001"  # TT06 amend d8k2 — ratified per-op
OP_INSERT_D8K8 = "bbbbbbbb-0000-4000-8000-000000000002" # TT06 insert k8 — ratified per-op
OP_SUSPEND_D8K8 = "bbbbbbbb-0000-4000-8000-000000000003"# TT10 suspend k8 — ratified, valid_to_event
OP_DEF_PROPOSED = "bbbbbbbb-0000-4000-8000-000000000004"# đề xuất amend ĐỊNH NGHĨA d2k5 — per-op queue
OP_BATCH_1 = "bbbbbbbb-0000-4000-8000-000000000005"     # 3 op cơ học 10→07 ngày làm việc
OP_BATCH_2 = "bbbbbbbb-0000-4000-8000-000000000006"
OP_BATCH_3 = "bbbbbbbb-0000-4000-8000-000000000007"
OP_NODATE = "bbbbbbbb-0000-4000-8000-000000000008"      # đề xuất thiếu valid_from → per-op

NORM_CHOVAY = "cccccccc-0000-4000-8000-000000000001"
CONFLICT_468 = "dddddddd-0000-4000-8000-000000000001"
PEV_TT10 = "eeeeeeee-0000-4000-8000-000000000001"

D8K2_V1 = ("Khách hàng vay vốn phục vụ nhu cầu đời sống phải cung cấp tài liệu chứng minh "
           "mục đích sử dụng vốn; tổ chức tín dụng thẩm định và quyết định cho vay "
           "trong thời hạn 10 ngày làm việc kể từ ngày nhận đủ hồ sơ.")
D8K2_V2 = ("Khách hàng vay vốn phục vụ nhu cầu đời sống phải cung cấp thông tin về "
           "phương án sử dụng vốn khả thi; việc thẩm định thực hiện theo quy định nội bộ "
           "của tổ chức tín dụng, tối đa 07 ngày làm việc kể từ ngày nhận đủ hồ sơ.")
D8K8_TEXT = ("Trường hợp cho vay bằng phương tiện điện tử, tổ chức tín dụng phải nhận biết "
             "khách hàng bằng eKYC và lưu trữ nhật ký giao dịch tối thiểu 10 năm.")
QT_BODY = ("Bộ phận thẩm định hoàn tất báo cáo trong thời hạn 10 ngày làm việc; "
           "trình cấp phê duyệt theo hạn mức. Mã tra cứu nội bộ: " + INTERNAL_MARKER + ".")
QT_BODY_NEW = QT_BODY.replace("10 ngày làm việc", "07 ngày làm việc")

EVENT_PREDICATE = "văn bản quy phạm pháp luật mới quy định về các vấn đề này có hiệu lực"


def seed(conn: psycopg.Connection) -> None:
    now = datetime.now(timezone.utc)
    # --- artifacts (L0) ------------------------------------------------------
    artifacts = [
        # (id, doc_key, doc_type, issuer, title, issued, effective, audience, owner, channel, text)
        ("sha-tt39", "39/2016/TT-NHNN", "thong_tu", "NHNN",
         "Thông tư quy định về hoạt động cho vay của TCTD", "2016-12-30", "2017-03-15",
         "public", None, "congbao",
         "Điều 2. Giải thích từ ngữ …\nĐiều 8. Điều kiện vay vốn …\n" + D8K2_V1),
        ("sha-tt06", "06/2023/TT-NHNN", "thong_tu", "NHNN",
         "Thông tư sửa đổi, bổ sung một số điều của TT 39/2016/TT-NHNN", "2023-06-28", "2023-09-01",
         "public", None, "congbao",
         "Điều 1. Sửa đổi, bổ sung một số điều của Thông tư 39/2016/TT-NHNN …"),
        ("sha-tt10", "10/2023/TT-NHNN", "thong_tu", "NHNN",
         "Thông tư ngưng hiệu lực thi hành một số nội dung của TT 39/2016/TT-NHNN", "2023-08-23", "2023-09-01",
         "public", None, "congbao",
         "Điều 1. Ngưng hiệu lực thi hành khoản 8, khoản 9, khoản 10 Điều 8 …"),
        ("sha-qt01", "QT-TD-01", "noi_bo", "SHB.QLTD",
         "Quy trình thẩm định tín dụng bán lẻ", "2022-05-10", "2022-06-01",
         "internal", "SHB.QLTD", "internal_registry",
         "Điều 3. Thời hạn thẩm định …\n" + QT_BODY),
        ("sha-qt02", "QT-TD-02", "noi_bo", "SHB.QLTD",
         "Văn bản sửa đổi QT-TD-01 đồng bộ TT 06/2023", "2023-09-15", "2023-10-01",
         "internal", "SHB.QLTD", "internal_registry",
         "Điều 1. Thay cụm từ \u201c10 ngày làm việc\u201d bằng \u201c07 ngày làm việc\u201d tại các Điều 3, 4, 5 QT-TD-01."),
    ]
    for a in artifacts:
        conn.execute(
            """INSERT INTO artifact (id, doc_key, doc_type, issuer, title, issued_date,
                                     effective_date, audience, owner, channel, synthetic, text)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s) ON CONFLICT (id) DO NOTHING""",
            a[:10] + (a[10],),
        )

    # --- nodes + alias -------------------------------------------------------
    # page_anchor.heading/body = text gốc cho engine F4 fold (engine/README — default_base_text);
    # node do INSERT sinh (k8) để body None: base = new_text của op insert.
    nodes = [
        (N_D8K2, "sha-tt39", "dieu:8/khoan:2", "rule", "Điều 8 khoản 2", D8K2_V1),
        (N_D2K5, "sha-tt39", "dieu:2/khoan:5", "definition", "Điều 2 khoản 5 (định nghĩa)",
         "Cho vay phục vụ nhu cầu đời sống là việc TCTD cho vay để thanh toán các chi phí "
         "cho mục đích tiêu dùng, sinh hoạt."),
        (N_D8K8, "sha-tt39", "dieu:8/khoan:8", "rule", "Điều 8 khoản 8 (bổ sung bởi TT06)", None),
        (N_TT06_AMD, "sha-tt06", "dieu:1/khoan:3", "amending", "Điều 1 khoản 3 (điều khoản sửa đổi)",
         "Bổ sung khoản 8 vào Điều 8: \u201c" + D8K8_TEXT + "\u201d"),
        (N_QT3, "sha-qt01", "dieu:3", "rule", "Điều 3 QT-TD-01", QT_BODY),
        (N_QT4, "sha-qt01", "dieu:4", "rule", "Điều 4 QT-TD-01", QT_BODY),
        (N_QT5, "sha-qt01", "dieu:5", "rule", "Điều 5 QT-TD-01", QT_BODY),
    ]
    for nid, art, path, role, label, base_body in nodes:
        anchor = {"heading": label}
        if base_body is not None:
            anchor["body"] = base_body
        conn.execute(
            """INSERT INTO node (id, artifact_id, path, label, role, page_anchor)
               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
            (nid, art, path, label, role, json.dumps(anchor, ensure_ascii=False)),
        )
        doc_key = {"sha-tt39": "39/2016/TT-NHNN", "sha-tt06": "06/2023/TT-NHNN",
                   "sha-qt01": "QT-TD-01", "sha-qt02": "QT-TD-02"}[art]
        conn.execute(
            """INSERT INTO alias (doc_key, path, node_id, valid_from)
               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (doc_key, path, nid, "2017-03-15" if art == "sha-tt39" else "2022-06-01"),
        )

    # --- norm (D-09) ---------------------------------------------------------
    conn.execute(
        """INSERT INTO norm (id, topic, artifact_id, valid_from, correlation)
           VALUES (%s, 'quy chế cho vay của TCTD đối với khách hàng', 'sha-tt39', '2017-03-15',
                   %s) ON CONFLICT DO NOTHING""",
        (NORM_CHOVAY, json.dumps({"ke_vi": "QĐ 1627/2001/QĐ-NHNN", "non_binding": True})),
    )

    # --- ops (L2) ------------------------------------------------------------
    ops = [
        # id, kind, src_art, quote, seq, target_node, part, new_text, vf, vt, vte, risk, extr, conf, status, rby, batch
        (OP_AMEND_D8K2, "amend", "sha-tt06",
         "Sửa đổi, bổ sung khoản 2 Điều 8 như sau: …", 1, N_D8K2, "body", D8K2_V2,
         "2023-09-01", None, None, "prescriptive", "llm:gemini-2.5-flash", 0.97,
         "ratified", "lan.nguyen@shb", None),
        (OP_INSERT_D8K8, "insert", "sha-tt06",
         "Bổ sung khoản 8 vào Điều 8 như sau: …", 2, N_D8K8, "body", D8K8_TEXT,
         "2023-09-01", None, None, "prescriptive", "llm:gemini-2.5-flash", 0.95,
         "ratified", "lan.nguyen@shb", None),
        (OP_SUSPEND_D8K8, "suspend", "sha-tt10",
         "Ngưng hiệu lực thi hành khoản 8 Điều 8 Thông tư số 39/2016/TT-NHNN (đã được bổ sung "
         "theo khoản 3 Điều 1 Thông tư 06/2023/TT-NHNN) từ ngày 01/9/2023 cho đến ngày "
         "văn bản quy phạm pháp luật mới quy định về các vấn đề này có hiệu lực.",
         1, N_D8K8, "body", None, "2023-09-01", None, EVENT_PREDICATE,
         "prescriptive", "rule", 0.99, "ratified", "minh.tran@shb", None),
        (OP_DEF_PROPOSED, "amend", "sha-tt06",
         "Sửa đổi khoản 5 Điều 2 (giải thích từ ngữ) như sau: …", 3, N_D2K5, "body",
         "Cho vay phục vụ nhu cầu đời sống là việc TCTD cho vay để thanh toán các chi phí "
         "cho mục đích tiêu dùng, sinh hoạt của cá nhân, bao gồm cả vay qua phương tiện điện tử.",
         "2023-09-01", None, None, "definitional", "llm:gemini-2.5-flash", 0.62,
         "proposed", None, None),
        (OP_BATCH_1, "amend", "sha-qt02",
         "Thay cụm từ \u201c10 ngày làm việc\u201d bằng \u201c07 ngày làm việc\u201d tại Điều 3.",
         1, N_QT3, "body", QT_BODY_NEW, "2023-10-01", None, None,
         "prescriptive", "rule", 0.96, "proposed", None, None),
        (OP_BATCH_2, "amend", "sha-qt02",
         "Thay cụm từ \u201c10 ngày làm việc\u201d bằng \u201c07 ngày làm việc\u201d tại Điều 4.",
         2, N_QT4, "body", QT_BODY_NEW, "2023-10-01", None, None,
         "prescriptive", "rule", 0.96, "proposed", None, None),
        (OP_BATCH_3, "amend", "sha-qt02",
         "Thay cụm từ \u201c10 ngày làm việc\u201d bằng \u201c07 ngày làm việc\u201d tại Điều 5.",
         3, N_QT5, "body", QT_BODY_NEW, "2023-10-01", None, None,
         "prescriptive", "rule", 0.95, "proposed", None, None),
        (OP_NODATE, "repeal", "sha-tt10",
         "Bãi bỏ quy định chuyển tiếp tại văn bản nội bộ tương ứng kể từ ngày văn bản mới có hiệu lực.",
         2, N_QT5, "body", None, None, None, None,
         "prescriptive", "llm:gemini-2.5-flash", 0.41, "proposed", None, None),
    ]
    for o in ops:
        conn.execute(
            """INSERT INTO op (id, kind, source_artifact, source_quote, seq, target_node,
                               target_part, new_text, valid_from, valid_to, valid_to_event,
                               risk_class, extractor, confidence, status, ratified_by, ratify_batch,
                               ratified_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       CASE WHEN %s IN ('ratified','superseded') THEN now() END)
               ON CONFLICT (id) DO NOTHING""",
            (*o, o[14]),
        )

    # --- replay_run + node_version (L3) — INSERT tự do, coi như output một run F4 mẫu
    conn.execute(
        """INSERT INTO replay_run (run_id, k_cutoff, corpus_hash, started, finished, ops_count)
           VALUES (%s, %s, 'seed-demo-hash', %s, %s, 3) ON CONFLICT DO NOTHING""",
        (RUN_ID, now, now, now),
    )
    versions = [
        # node, ver, heading, body, status, vf, vt, provenance[], retrievable
        (N_D8K2, 1, "Điều 8 khoản 2", D8K2_V1, "active", "2017-03-15", "2023-09-01", [], True),
        (N_D8K2, 2, "Điều 8 khoản 2 (sđ TT06)", D8K2_V2, "active", "2023-09-01", None,
         [OP_AMEND_D8K2], True),
        (N_D2K5, 1, "Điều 2 khoản 5", "Cho vay phục vụ nhu cầu đời sống là việc TCTD cho vay "
         "để thanh toán các chi phí cho mục đích tiêu dùng, sinh hoạt.", "active", "2017-03-15",
         None, [], True),
        # k8: version active KHÔNG BAO GIỜ tồn tại — chỉ có suspended (D-24)
        (N_D8K8, 1, "Điều 8 khoản 8", D8K8_TEXT, "suspended", "2023-09-01", None,
         [OP_INSERT_D8K8, OP_SUSPEND_D8K8], True),
        # node amending: retrievable=false (INV-8) — chứa nguyên văn text bị treo (bẫy contamination)
        (N_TT06_AMD, 1, "Điều 1 khoản 3 TT06", "Bổ sung khoản 8 vào Điều 8: \u201c" + D8K8_TEXT + "\u201d",
         "active", "2023-09-01", None, [], False),
        (N_QT3, 1, "Điều 3 QT-TD-01", QT_BODY, "active", "2022-06-01", None, [], True),
        (N_QT4, 1, "Điều 4 QT-TD-01", QT_BODY, "active", "2022-06-01", None, [], True),
        (N_QT5, 1, "Điều 5 QT-TD-01", QT_BODY, "active", "2022-06-01", None, [], True),
    ]
    for v in versions:
        conn.execute(
            """INSERT INTO node_version (node_id, version, heading, body, status, valid_from,
                                         valid_to, provenance, run_id, retrievable)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s) ON CONFLICT DO NOTHING""",
            (*v[:7], v[7], RUN_ID, v[8]),
        )

    # --- edges (D-13) --------------------------------------------------------
    edges = [
        (N_D8K2, 2, N_D2K5, None, None, "dinh_nghia", "khoản 5 Điều 2 Thông tư này", 1.0),
        (N_D8K2, 2, None, None, None, "chuyen_tiep",
         "quy định chuyển tiếp tại văn bản hướng dẫn của Tổng Giám đốc", 0.0),  # unresolved → backlog
        (N_QT3, 1, N_D8K2, None, None, "tham_quyen", "khoản 2 Điều 8 TT 39/2016/TT-NHNN", 1.0),
        (N_QT3, 1, None, NORM_CHOVAY, None, "chu_de", "quy định của NHNN về cho vay", 1.0),
        (N_D8K8, 1, None, None, "Basel III LCR", "frontier", "chuẩn mực Basel về thanh khoản", 0.8),
    ]
    for e in edges:
        conn.execute(
            """INSERT INTO edge (src_node, src_version, dst_node, dst_norm, frontier_ref,
                                 kind, raw_citation, confidence)
               SELECT %s,%s,%s,%s,%s,%s,%s,%s
               WHERE NOT EXISTS (SELECT 1 FROM edge WHERE src_node=%s AND kind=%s AND raw_citation=%s)""",
            (*e, e[0], e[5], e[6]),
        )

    # --- pending_event (D-11) + conflict tier-2 + notification + coverage ----
    conn.execute(
        """INSERT INTO pending_event (id, kind, ref, predicate, status)
           VALUES (%s, 'open_suspension', %s, %s, 'open') ON CONFLICT (id) DO NOTHING""",
        (PEV_TT10, OP_SUSPEND_D8K8, EVENT_PREDICATE),
    )
    conn.execute(
        """INSERT INTO conflict (id, member_versions, tier, label, fork, doctrine, reason, status, detected_by)
           VALUES (%s, %s, 2, 'mau_thuan', 'external_external', %s, %s, 'open', 'seed')
           ON CONFLICT (id) DO NOTHING""",
        (CONFLICT_468,
         json.dumps([{"node_id": N_D8K2, "version": 2}]),
         json.dumps({"rank_a": "luat", "rank_b": "thong_tu", "same_issuer": False,
                     "art156": "khong_phan_dinh"}),
         "Trần lãi suất 20%/năm (Đ468 BLDS 2015) vs cơ chế lãi suất thỏa thuận (Đ13 TT39) — "
         "khác cơ quan ban hành, Đ156 không phân định; chờ statement giải (NQ 01/2019/NQ-HĐTP)."),
    )
    for op_id, doc, owner, sev in [
        (OP_AMEND_D8K2, "QT-TD-01", "SHB.QLTD", "interruptive"),
        (OP_SUSPEND_D8K8, "QT-TD-01", "SHB.QLTD", "advisory"),
    ]:
        conn.execute(
            """INSERT INTO notification (op_id, affected_node, affected_doc, owner, severity)
               SELECT %s, %s, %s, %s, %s
               WHERE NOT EXISTS (SELECT 1 FROM notification WHERE op_id=%s AND affected_doc=%s AND severity=%s)""",
            (op_id, N_QT3, doc, owner, sev, op_id, doc, sev),
        )
    for ch, seq in [("congbao", "69/2023"), ("sbv", "2023-08-31"), ("internal_registry", "2023-10-01")]:
        conn.execute(
            """INSERT INTO coverage (channel, last_seq, last_checked) VALUES (%s,%s,now())
               ON CONFLICT (channel) DO UPDATE SET last_seq = EXCLUDED.last_seq, last_checked = now()""",
            (ch, seq),
        )

    # --- answer_log Tier D (demand log) --------------------------------------
    demand_qs = [
        ("Hạn mức LTV cho vay mua nhà dự án hình thành trong tương lai?", "internal"),
        ("Hạn mức LTV cho vay mua nhà dự án hình thành trong tương lai?", "internal"),
        ("Điều kiện cấp bảo lãnh cho nhà thầu nước ngoài?", "public"),
    ]
    for q, aud in demand_qs:
        conn.execute(
            """INSERT INTO answer_log (question, audience, as_of, tier, claims, retrieved, banners, run_id)
               SELECT %s, %s, current_date, 'D', '[]', '[]', '[]', %s
               WHERE NOT EXISTS (SELECT 1 FROM answer_log WHERE question = %s AND audience = %s)""",
            (q, aud, RUN_ID, q, aud),
        )
    # câu trùng lần 2 cho tần suất — chèn thẳng (điều kiện trên chặn mất bản ghi lặp)
    conn.execute(
        """INSERT INTO answer_log (question, audience, as_of, tier, claims, retrieved, banners, run_id)
           SELECT %s, 'internal', current_date, 'D', '[]', '[]', '[]', %s
           WHERE (SELECT count(*) FROM answer_log WHERE question = %s) < 2""",
        (demand_qs[0][0], RUN_ID, demand_qs[0][0]),
    )
    conn.commit()


def reset(conn: psycopg.Connection) -> None:
    from pathlib import Path

    init_sql = (Path(__file__).resolve().parents[2] / "db" / "init.sql").read_text(encoding="utf-8")
    conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.execute(init_sql)
    conn.commit()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "postgresql://lawstate:lawstate@localhost:55432/lawstate"
    with psycopg.connect(url, autocommit=False) as conn:
        if "--reset" in sys.argv:
            conn.autocommit = True
            reset(conn)
            conn.autocommit = False
        seed(conn)
    print("Seed xong:", url)
