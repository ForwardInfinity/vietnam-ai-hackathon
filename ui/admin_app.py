"""LawState — Curator workbench (F6, FR-9..FR-14). Build TRƯỚC chat UI (R-17):
throughput curator là đường găng. Máy đề xuất — NGƯỜI phê chuẩn — engine thực thi (D-03).

Chạy: streamlit run ui/admin_app.py  (production: /admin qua Caddy + basic-auth)
"""
from __future__ import annotations

import json
from datetime import date

import streamlit as st

try:  # chạy từ root (pytest/AppTest) hay từ ui/ (streamlit run) đều được
    from ui import api_client as api
except ImportError:  # pragma: no cover
    import api_client as api  # type: ignore

st.set_page_config(page_title="LawState — Curator", page_icon="🛡️", layout="wide")

ROLE = "curator"

# ---------------------------------------------------------------------------
# Sidebar: actor (INV-6 — mọi quyết định mang tên người) + điều hướng
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🛡️ Curator workbench")
    actor = st.text_input("Người thao tác (X-Actor)", value=st.session_state.get("actor", "curator.demo"),
                          help="INV-6: mọi op ratified phải truy ra người ký — không có auto-ratify.")
    st.session_state["actor"] = actor
    section = st.radio("Khu vực", [
        "📋 Hàng đợi per-op",
        "📦 Duyệt lô (batch)",
        "▶️ Replay",
        "🗂 Backlog",
        "⚔️ Conflicts",
        "📈 Demand log",
        "🔔 Notifications",
        "📥 Ingest văn bản",
        "🖋 Sổ ký (INV-6)",
    ])
    st.divider()
    try:
        h = api.get("/health", ROLE)
        ok = h.status_code == 200
        st.caption(("🟢" if ok else "🔴") + f" API `{api.API_URL}` · DB: {h.json().get('db', '?')}")
    except Exception as exc:
        st.caption(f"🔴 API không phản hồi: {type(exc).__name__}")


def _err(resp, prefix="Lỗi"):
    st.error(f"{prefix} ({resp.status_code}): {api.err_text(resp)}")


def _op_label(item: dict) -> str:
    op = item["op"]
    tgt = item["target"].get("doc_key") or "?"
    path = item["target"].get("path") or op.get("target_op") or op.get("target_norm") or "—"
    conf = f"{op['confidence']:.2f}" if op.get("confidence") is not None else "—"
    return f"[{op['kind']}] {tgt} · {path} · risk={op.get('risk_class') or '?'} · conf={conf}"


def _render_quote_vs_diff(item: dict):
    """FR-9: source_quote CẠNH diff (target hiện tại vs sau-áp)."""
    op = item["op"]
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("**📜 Nguyên văn căn cứ (`source_quote`)**")
        st.info(op.get("source_quote") or "—")
        meta = [
            f"nguồn: `{item.get('source_doc_key')}`",
            f"hiệu lực: {op.get('valid_from') or '?'} → {op.get('valid_to') or (op.get('valid_to_event') and 'sự kiện: ' + op['valid_to_event']) or 'nay'}",
            f"extractor: `{op.get('extractor')}`",
        ]
        st.caption(" · ".join(meta))
        if op.get("scope_predicate"):
            st.caption(f"scope: `{json.dumps(op['scope_predicate'], ensure_ascii=False)}`")
    with right:
        st.markdown("**🔀 Diff: hiện tại → sau-áp**")
        if item.get("diff"):
            st.code(item["diff"], language="diff")
        else:
            st.caption("Không có diff (op nhắm op/norm hoặc target chưa có version).")
        t = item["target"]
        if t.get("current_version") is not None:
            st.caption(f"target: `{t.get('doc_key')}` `{t.get('path')}` · v{t['current_version']} ({t.get('current_status')})")


# ===========================================================================
if section == "📋 Hàng đợi per-op":
    st.header("📋 Hàng đợi phê chuẩn per-op")
    st.caption("Sort: risk definitional trước → confidence tăng dần (R-17). "
               "Op cơ học đủ điều kiện được gắn nhãn *batch-eligible* — duyệt bên tab Duyệt lô.")
    r = api.get("/v1/admin/ops", ROLE, status="proposed")
    if r.status_code != 200:
        _err(r, "Không tải được queue")
        st.stop()
    items = r.json()["items"]
    if not items:
        st.success("Queue trống — không op nào chờ phê chuẩn.")
        st.stop()

    per_op = [i for i in items if i["queue"] == "per_op"]
    batch_e = [i for i in items if i["queue"] == "batch_eligible"]
    c1, c2 = st.columns(2)
    c1.metric("Chờ per-op", len(per_op))
    c2.metric("Batch-eligible (tab Duyệt lô)", len(batch_e))

    for idx, item in enumerate(per_op + batch_e):
        op = item["op"]
        tag = "🔴 per-op" if item["queue"] == "per_op" else "🟢 batch-eligible"
        with st.expander(f"{tag} — {_op_label(item)}", expanded=(idx == 0)):
            _render_quote_vs_diff(item)
            a1, a2, a3, _sp = st.columns([1, 1, 1, 3])
            if a1.button("✅ Approve", key=f"ap{op['id']}", type="primary",
                         disabled=not actor, help="Ghi ratified_by = X-Actor (INV-6)"):
                resp = api.post(f"/v1/admin/ops/{op['id']}/decision", ROLE, actor,
                                json_body={"action": "approve"})
                if resp.status_code == 200:
                    st.toast(f"Đã ratify — người ký: {actor}", icon="✅")
                    st.rerun()
                else:
                    _err(resp)
            if a2.button("✏️ Edit", key=f"ed{op['id']}"):
                st.session_state["edit_op"] = op["id"]
            if a3.button("🗑 Reject", key=f"rj{op['id']}", disabled=not actor):
                resp = api.post(f"/v1/admin/ops/{op['id']}/decision", ROLE, actor,
                                json_body={"action": "reject"})
                if resp.status_code == 200:
                    st.toast("Đã reject", icon="🗑")
                    st.rerun()
                else:
                    _err(resp)

            if st.session_state.get("edit_op") == op["id"]:
                st.markdown("---")
                st.markdown("**Sửa đề xuất (op còn `proposed` — curator materialize, D-21)**")
                with st.form(key=f"fm{op['id']}"):
                    new_text = st.text_area("new_text", value=op.get("new_text") or "", height=140)
                    cols = st.columns(3)
                    vf = cols[0].text_input("valid_from (YYYY-MM-DD)", value=op.get("valid_from") or "")
                    risk = cols[1].selectbox("risk_class", ["prescriptive", "definitional"],
                                             index=0 if op.get("risk_class") != "definitional" else 1)
                    conf = cols[2].number_input("confidence", 0.0, 1.0,
                                                float(op.get("confidence") or 0.5), 0.01)
                    if st.form_submit_button("Lưu sửa đổi"):
                        edits = {"new_text": new_text or None, "risk_class": risk, "confidence": conf}
                        if vf:
                            edits["valid_from"] = vf
                        resp = api.post(f"/v1/admin/ops/{op['id']}/decision", ROLE, actor,
                                        json_body={"action": "edit", "edits": edits})
                        if resp.status_code == 200:
                            st.session_state.pop("edit_op", None)
                            st.toast("Đã lưu — op vẫn proposed, cần Approve để ratify", icon="✏️")
                            st.rerun()
                        else:
                            _err(resp)

# ===========================================================================
elif section == "📦 Duyệt lô (batch)":
    st.header("📦 Batch-ratify với invariant template (D-19, R-16)")
    st.caption("Khai template → MÁY verify từng op → curator ký CẢ LỚP → spot-check ≥10%. "
               "Op thuộc hàng per-op không thể lọt vào lô (router R-15 chặn).")
    done = st.session_state.get("batch_done")
    if done:  # báo cáo lô vừa ký — render TRƯỚC (queue có thể đã rỗng sau khi ratify)
        st.success(f"Đã ratify {done['ratified_count']} op trong lô `{str(done['batch_id'])[:8]}…` "
                   f"— người ký: **{done['approved_by']}**")
        st.subheader(f"Spot-check ({int(done['spot_check_rate']*100)}% — soi tay tối thiểu, D-19)")
        for it in done["spot_check"]:
            with st.container(border=True):
                st.markdown(f"**{it.get('target_doc_key')} · {it.get('target_path')}** — op `{it['op_id'][-8:]}`")
                st.info(it.get("source_quote"))
                st.code(it.get("new_text") or "", language=None)
        if st.button("Đóng báo cáo lô"):
            st.session_state.pop("batch_done", None)
            st.rerun()
        st.divider()

    r = api.get("/v1/admin/ops", ROLE, status="proposed")
    if r.status_code != 200:
        _err(r)
        st.stop()
    eligible = [i for i in r.json()["items"] if i["queue"] == "batch_eligible"]
    if not eligible:
        st.info("Không có op batch-eligible trong queue.")
        st.stop()

    by_label = {_op_label(i): i for i in eligible}
    chosen = st.multiselect("Op vào lô", list(by_label), default=list(by_label))
    with st.expander("Xem source_quote + diff từng op trong lô", expanded=False):
        for lbl in chosen:
            st.markdown(f"**{lbl}**")
            _render_quote_vs_diff(by_label[lbl])
            st.markdown("---")

    st.subheader("1️⃣ Khai invariant template")
    pattern = st.selectbox("pattern", ["uniform_field_change", "phrase_replace", "mass_repeal"])
    tpl: dict = {"pattern": pattern}
    if pattern == "phrase_replace":
        tpl["from"] = st.text_input("from (cụm cũ)", "10 ngày làm việc")
        tpl["to"] = st.text_input("to (cụm mới)", "07 ngày làm việc")
    elif pattern == "uniform_field_change":
        tpl["field_regex"] = st.text_input("field_regex", r"\d+ ngày làm việc")
        c1, c2 = st.columns(2)
        tpl["from"] = c1.text_input("from (giá trị cũ)", "10")
        tpl["to"] = c2.text_input("to (giá trị mới)", "07")
    else:
        keys = st.text_input("target_doc_keys (phẩy)", "01/2020/TT-NHNN")
        tpl["target_doc_keys"] = [k.strip() for k in keys.split(",") if k.strip()]
    desc = st.text_input("Mô tả lô", "Đồng bộ thời hạn 10→07 ngày làm việc theo TT06")

    op_ids = [by_label[lbl]["op"]["id"] for lbl in chosen]
    st.subheader("2️⃣ Machine-verify từng op")
    if st.button("🔎 Verify (dry-run)", disabled=not op_ids):
        resp = api.post("/v1/admin/batches/verify", ROLE, actor,
                        json_body={"op_ids": op_ids, "invariant_template": tpl})
        if resp.status_code == 200:
            st.session_state["batch_verify"] = {"ids": op_ids, "tpl": tpl, "out": resp.json()}
        else:
            _err(resp)
    bv = st.session_state.get("batch_verify")
    if bv and bv["ids"] == op_ids and bv["tpl"] == tpl:
        out = bv["out"]
        st.dataframe([{"op": x["op_id"][-8:], "pass": "✅" if x["ok"] else "❌",
                       "weak": "⚠️ thiếu snapshot" if x["weak"] else "so khớp current_text",
                       "lý do": x["reason"]} for x in out["results"]],
                     use_container_width=True, hide_index=True)
        st.subheader("3️⃣ Ký cả lớp")
        if out["all_ok"]:
            if st.button(f"🖋 SIGN {len(op_ids)} op — người ký: {actor}", type="primary", disabled=not actor):
                resp = api.post("/v1/admin/batches", ROLE, actor,
                                json_body={"op_ids": op_ids, "invariant_template": tpl,
                                           "description": desc})
                if resp.status_code == 200:
                    st.session_state["batch_done"] = resp.json()
                    st.session_state.pop("batch_verify", None)
                    st.rerun()
                else:
                    _err(resp)
        else:
            st.error("Máy verify FAIL ≥1 op — không thể ký lô này (không op nào được ratify).")

# ===========================================================================
elif section == "▶️ Replay":
    st.header("▶️ Replay — fold toàn corpus thành snapshot mới (FR-11)")
    st.caption("Op ratified là INPUT duy nhất của engine tất định (D-03). "
               "Sau replay: run_id mới, BM25+embedding rebuild, câu trả lời ĐỔI.")
    if st.button("▶️ Chạy replay", type="primary", disabled=not actor):
        with st.spinner("Đang fold…"):
            resp = api.post("/v1/admin/replay", ROLE, actor)
        if resp.status_code == 200:
            st.session_state["replay_report"] = resp.json()
        elif resp.status_code == 501:
            st.warning(f"⏳ Engine chưa nối: {api.err_text(resp)}")
        else:
            _err(resp)
    rep = st.session_state.get("replay_report")
    if rep:
        st.success(f"Run mới: `{rep.get('run_id')}`")
        c1, c2, c3 = st.columns(3)
        c1.metric("Node đổi version", len(rep.get("changed_nodes", [])))
        c2.metric("Certificate mới", len(rep.get("certificates", [])))
        c3.metric("Guard violation", len(rep.get("guard_violations", [])))
        for name, rows in [("Changed nodes", rep.get("changed_nodes")),
                           ("Certificates", rep.get("certificates")),
                           ("Guard violations", rep.get("guard_violations"))]:
            if rows:
                with st.expander(name):
                    st.dataframe(rows, use_container_width=True)
    st.divider()
    st.markdown("**Run gần nhất theo /v1/ask (meta):**")
    try:
        for ev, data in api.ask_sse({"question": "ping run"}, "employee"):
            if ev == "meta":
                st.code(json.dumps(data, ensure_ascii=False, indent=2), language="json")
                break
    except Exception as exc:
        st.caption(f"(không lấy được meta: {type(exc).__name__})")

# ===========================================================================
elif section == "🗂 Backlog":
    st.header("🗂 Backlog dashboard (FR-12)")
    r = api.get("/v1/admin/backlog", ROLE)
    if r.status_code != 200:
        _err(r)
        st.stop()
    b = r.json()
    cols = st.columns(5)
    labels = [("consolidation_pending", "Consolidation chờ"), ("oracle_mismatch", "Oracle lệch"),
              ("unresolved_refs", "Ref chưa resolve"), ("pending_events_open", "Sự kiện treo mở"),
              ("coverage_channels", "Kênh coverage")]
    for col, (k, lbl) in zip(cols, labels):
        col.metric(lbl, b["counts"].get(k, 0))
    tabs = st.tabs(["Consolidation", "Unresolved refs", "Pending events", "Coverage", "Oracle diff"])
    with tabs[0]:
        st.caption("Node có op proposed đã ĐẾN HẠN hiệu lực mà chưa được phê chuẩn (view v_consolidation_pending).")
        st.dataframe(b["consolidation_pending"], use_container_width=True, hide_index=True)
    with tabs[1]:
        st.caption("Edge 3 đích NULL, confidence 0 (R-10) — chạm mandatory closure là Tier D.")
        st.dataframe(b["unresolved_refs"], use_container_width=True, hide_index=True)
    with tabs[2]:
        st.caption("D-11: nghĩa vụ đóng cửa sổ khi 'văn bản QPPL mới' xuất hiện — sweep đề xuất, NGƯỜI chốt.")
        st.dataframe(b["pending_events"], use_container_width=True, hide_index=True)
    with tabs[3]:
        st.caption("Coverage attestation theo kênh (D-32): hệ nói được 'đã quét gì, đến đâu'.")
        st.dataframe(b["coverage"], use_container_width=True, hide_index=True)
    with tabs[4]:
        st.dataframe(b["oracle_mismatch"], use_container_width=True, hide_index=True)
    for n in b.get("notes", []):
        st.caption("⏳ " + n)

# ===========================================================================
elif section == "⚔️ Conflicts":
    st.header("⚔️ Conflict kanban theo fork (FR-13, D-33..35)")
    r = api.get("/v1/admin/conflicts", ROLE)
    if r.status_code != 200:
        _err(r)
        st.stop()
    board = r.json()["board"]
    FORK_TAG = {"internal_internal": "🏠↔🏠 ticket phòng sở hữu",
                "internal_external": "🏠↔🏛 escalation compliance",
                "external_external": "🏛↔🏛 surface + doctrine",
                "advisory": "📎 advisory"}
    cols = st.columns(4)
    for col, status in zip(cols, ["open", "resolved", "dismissed", "accepted_risk"]):
        with col:
            st.subheader(f"{status} ({len(board.get(status, []))})")
            for c in board.get(status, []):
                with st.container(border=True):
                    st.markdown(f"**Tier {c['tier']}** · `{(c.get('label') or '?')}`")
                    st.caption(FORK_TAG.get(c.get("fork"), c.get("fork") or "chưa fork"))
                    st.write(c["reason"][:220] + ("…" if len(c["reason"]) > 220 else ""))
                    if c.get("ticket_ref"):
                        st.caption(f"🎫 {c['ticket_ref']}")
                    if c.get("resolved_by_op"):
                        st.caption(f"giải bởi op `{str(c['resolved_by_op'])[:8]}…`")
                    if status == "open":
                        with st.popover("Triage"):
                            new_status = st.selectbox("status", ["open", "resolved", "dismissed", "accepted_risk"],
                                                      key=f"cs{c['id']}")
                            new_fork = st.selectbox("fork", [None, "internal_internal", "internal_external",
                                                             "external_external", "advisory"], key=f"cf{c['id']}")
                            ticket = st.text_input("ticket_ref", key=f"ct{c['id']}")
                            if st.button("Cập nhật", key=f"cb{c['id']}", disabled=not actor):
                                body = {"status": new_status if new_status != status else None,
                                        "fork": new_fork, "ticket_ref": ticket or None}
                                resp = api.post(f"/v1/admin/conflicts/{c['id']}/triage", ROLE, actor,
                                                json_body=body)
                                if resp.status_code == 200:
                                    st.rerun()
                                else:
                                    _err(resp)
    with st.expander("➕ Mở certificate thủ công (kênh SEM — curator phát hiện bằng mắt)"):
        with st.form("new_conflict"):
            reason = st.text_area("Mô tả xung đột (unsat-core, lý do)")
            tier = st.selectbox("tier", [2, 3, 1])
            fork = st.selectbox("fork", ["internal_internal", "internal_external",
                                         "external_external", "advisory"])
            if st.form_submit_button("Mở certificate") and reason:
                resp = api.post("/v1/admin/conflicts", ROLE, actor,
                                json_body={"member_versions": [], "tier": tier,
                                           "reason": reason, "fork": fork})
                if resp.status_code == 200:
                    st.rerun()
                else:
                    _err(resp)

# ===========================================================================
elif section == "📈 Demand log":
    st.header("📈 Demand log — câu Tier D theo tần suất (FR-14)")
    st.caption("Đây là hàng đợi ưu tiên consolidate corpus: hệ TỪ CHỐI có địa chỉ, không im lặng.")
    r = api.get("/v1/admin/demand", ROLE)
    if r.status_code != 200:
        _err(r)
        st.stop()
    d = r.json()
    st.metric("Tổng câu Tier D", d["total_tier_d"])
    st.dataframe([{"Câu hỏi": i["question"], "Số lần": i["count"],
                   "Audience": ", ".join(i["audiences"]), "Lần cuối": i["last_asked"]}
                  for i in d["items"]], use_container_width=True, hide_index=True)

# ===========================================================================
elif section == "🔔 Notifications":
    st.header("🔔 Notification digest theo owner (FR-14, D-36)")
    st.caption("`interruptive` (op definitional) bắt ack — NGOẠI LỆ HIẾM; còn lại advisory digest.")
    unacked = st.toggle("Chỉ chưa ack", value=False)
    r = api.get("/v1/admin/notifications", ROLE, unacked_only=str(unacked).lower())
    if r.status_code != 200:
        _err(r)
        st.stop()
    d = r.json()
    c1, c2 = st.columns(2)
    c1.metric("Tổng notice", d["total"])
    c2.metric("Chưa ack", d["unacked"])
    for owner, rows in d["by_owner"].items():
        with st.expander(f"👤 {owner} ({len(rows)})", expanded=True):
            for n in rows:
                cols = st.columns([1, 3, 1])
                sev = "🚨 interruptive" if n["severity"] == "interruptive" else "📎 advisory"
                cols[0].markdown(sev)
                cols[1].markdown(f"doc **{n.get('affected_doc') or '?'}** · node `{str(n.get('affected_node') or '')[:8]}…` "
                                 f"· op `{str(n.get('op_id') or '')[:8]}…`")
                if n["acked"]:
                    cols[2].markdown("✅ đã ack")
                elif cols[2].button("Ack", key=f"ack{n['id']}", disabled=not actor):
                    resp = api.post(f"/v1/admin/notifications/{n['id']}/ack", ROLE, actor)
                    if resp.status_code == 200:
                        st.rerun()
                    else:
                        _err(resp)

# ===========================================================================
elif section == "📥 Ingest văn bản":
    st.header("📥 Ingest văn bản mới (R-3 bước 1 → pipeline F3)")
    st.caption("File vào log L0 bất biến (sha256, tem trục K) → parse cây → citation → ĐỀ XUẤT op. "
               "Không gì tự vào effective state — mọi op chờ phê chuẩn ở queue.")
    with st.form("ingest"):
        f = st.file_uploader("File văn bản (TXT/MD/HTML/DOCX/PDF)")
        c1, c2, c3 = st.columns(3)
        doc_key = c1.text_input("doc_key *", placeholder="12/2024/TT-NHNN")
        doc_type = c2.selectbox("doc_type *", ["thong_tu", "luat", "nghi_quyet", "nghi_dinh",
                                               "quyet_dinh", "cong_van", "noi_bo", "bieu_mau", "vbhn"])
        issuer = c3.text_input("issuer *", placeholder="NHNN | SHB.QLTD")
        title = st.text_input("title")
        c4, c5, c6 = st.columns(3)
        issued = c4.text_input("issued_date (YYYY-MM-DD)")
        effective = c5.text_input("effective_date (YYYY-MM-DD)")
        audience = c6.selectbox("audience", ["public", "internal", "restricted"], index=1)
        c7, c8, c9 = st.columns(3)
        owner = c7.text_input("owner (phòng ban)")
        channel = c8.text_input("channel", value="internal_registry")
        is_oracle = c9.checkbox("VBHN oracle (chỉ diff, không retrieval — D-22)")
        if st.form_submit_button("📥 Nạp", type="primary"):
            if not (f and doc_key and issuer):
                st.error("Thiếu file / doc_key / issuer.")
            else:
                data = {"doc_key": doc_key, "doc_type": doc_type, "issuer": issuer,
                        "audience": audience, "is_oracle": str(is_oracle).lower(),
                        "synthetic": "false", "channel": channel}
                for k, v in [("title", title), ("issued_date", issued),
                             ("effective_date", effective), ("owner", owner)]:
                    if v:
                        data[k] = v
                resp = api.post("/v1/admin/ingest", ROLE, actor, files={"file": (f.name, f.getvalue())},
                                data=data)
                if resp.status_code == 200:
                    out = resp.json()
                    st.success(f"Artifact `{out['artifact_id'][:12]}…` ({'MỚI' if out['created'] else 'đã có'}) "
                               f"— pipeline: **{out['pipeline']}** — op đề xuất: {out['proposed_ops']}")
                    if out.get("note"):
                        st.warning("⏳ " + out["note"])
                else:
                    _err(resp)

# ===========================================================================
elif section == "🖋 Sổ ký (INV-6)":
    st.header("🖋 Sổ ký — mọi op ratified truy ra người (INV-6)")
    st.caption("Không auto-ratify (D-03): per-op → `ratified_by`; theo lô → `ratify_batch.approved_by` "
               "+ machine-verify pass từng op. Op sửa sau ratify = op MỚI, op cũ superseded (D-20).")
    tab1, tab2, tab3 = st.tabs(["Đã ratify", "Lô đã ký", "Superseded / Rejected"])
    with tab1:
        r = api.get("/v1/admin/ops", ROLE, status="ratified")
        if r.status_code == 200:
            rows = [{"op": i["op"]["id"][-8:], "kind": i["op"]["kind"],
                     "target": f"{i['target'].get('doc_key') or ''} {i['target'].get('path') or ''}",
                     "✍ người ký": i["op"]["ratified_by"] or f"(lô) {i['batch_approved_by']}",
                     "đường": "per-op" if i["op"]["ratified_by"] else "batch",
                     "lúc": i["op"]["ratified_at"]}
                    for i in r.json()["items"]]
            st.dataframe(rows, use_container_width=True, hide_index=True)
            unsigned = [x for x in rows if not x["✍ người ký"]]
            st.metric("Op ratified KHÔNG truy ra người ký", len(unsigned),
                      help="Phải luôn = 0 (INV-6)")
        else:
            _err(r)
    with tab2:
        r = api.get("/v1/admin/batches", ROLE)
        if r.status_code == 200:
            for b in r.json()["batches"]:
                with st.container(border=True):
                    st.markdown(f"**Lô `{str(b['id'])[:8]}…`** — ✍ **{b['approved_by']}** · {b['approved_at']}")
                    st.caption(f"{b.get('description') or ''} · {b['ops_count']} op · "
                               f"spot-check {int(b['spot_check_rate']*100)}%: {len(b.get('spot_checked') or [])} op")
                    st.code(json.dumps(b["invariant_template"], ensure_ascii=False), language="json")
        else:
            _err(r)
    with tab3:
        for status in ("superseded", "rejected"):
            r = api.get("/v1/admin/ops", ROLE, status=status)
            if r.status_code == 200 and r.json()["items"]:
                st.subheader(status)
                st.dataframe([{"op": i["op"]["id"][-8:], "kind": i["op"]["kind"],
                               "superseded_by": (i["op"].get("superseded_by") or "")[-8:],
                               "actor": i["op"].get("ratified_by")}
                              for i in r.json()["items"]],
                             use_container_width=True, hide_index=True)
