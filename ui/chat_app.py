"""LawState — Chat UI (F6 nâng cấp shell F1, FR-1..FR-8).

- SSE stream (meta → token → citation → banner → tier → done) với fallback JSON.
- as-of control + tem "Theo trạng thái văn bản ngày … (run …)" (FR-1).
- Citation chip → panel: text version + cửa sổ hiệu lực + badge + TIMELINE SLIDER
  + graph 1-hop (pyvis, fallback bảng) + link văn bản gốc (FR-2).
- Banner TRÊN thân trả lời, đúng thứ tự code lắp (FR-3); tier badge + giải thích (FR-4).
- Tier C sources-only KHÁC BIỆT THỊ GIÁC — degradation là feature (FR-5); Tier D card (FR-6).
- Persona employee/customer: customer ẩn tier nội bộ, giữ citation + ngày, disclaimer (FR-7).
- Nút "nghi đã cũ" → feedback (FR-8).
"""
from __future__ import annotations

from datetime import date

import streamlit as st

try:  # chạy từ root (pytest/AppTest) hay từ ui/ (streamlit run) đều được
    from ui import api_client as api
    from ui import panels
except ImportError:  # pragma: no cover
    import api_client as api  # type: ignore
    import panels  # type: ignore

st.set_page_config(page_title="LawState — SHB", page_icon="⚖️", layout="wide")

TIER_BADGE = {
    "A": ("🟢 Tier A", "Đã kiểm chứng sạch: mọi trích dẫn khớp snapshot, judge pass, không cờ nào."),
    "B": ("🟡 Tier B", "Đã qua gate cứng, kèm banner (conflict/pending/cohort/consolidation hoặc judge chưa hiệu chuẩn)."),
    "C": ("🟠 Tier C", "Sources-only: chỉ trích dẫn ghim, KHÔNG văn tổng hợp — gate cứng chặn văn soạn (INV-7)."),
    "D": ("🔴 Tier D", "Từ chối + route chuyên gia: thiếu căn cứ đã compile hoặc ngoài coverage."),
}
CUSTOMER_TIER = {
    "A": "✅ Trả lời theo văn bản hiện hành",
    "B": "✅ Trả lời theo văn bản hiện hành (có lưu ý bên dưới)",
    "C": "📌 Trích dẫn nguyên văn từ văn bản (không diễn giải)",
    "D": "🙋 Câu hỏi được chuyển tới chuyên viên hỗ trợ",
}

# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚖️ LawState")
    st.caption("Máy tính hiệu lực pháp quy ba trục thời gian — retrieval trên trạng thái đã compile, "
               "verifier hai tầng, không đủ căn cứ thì từ chối thay vì bịa.")
    persona = st.radio("Persona (FR-7)", ["employee", "customer"],
                       format_func=lambda a: "👔 Nhân viên" if a == "employee" else "🙋 Khách hàng")
    as_of = st.date_input("Trả lời theo trạng thái văn bản ngày (as-of)", value=date.today(),
                          help="FR-1: câu hỏi point-in-time — luật tại ngày t")
    with st.expander("Nâng cao (trục K)"):
        use_k = st.checkbox("Giới hạn 'biết-đến' (as_known)")
        as_known = st.date_input("Chỉ dùng văn bản đã nạp trước ngày", value=date.today(),
                                 disabled=not use_k)
    st.divider()
    st.caption(f"API: `{api.API_URL}`")

st.markdown("### Hỏi đáp pháp quy ngân hàng")
if persona == "customer":
    st.caption("ℹ️ Thông tin tham khảo theo văn bản công khai, **không phải tư vấn pháp lý**. "
               "Trường hợp cần kết luận áp dụng, câu hỏi sẽ được chuyển tới chuyên viên.")
else:
    st.caption("Mọi câu trả lời ghim vào phiên bản điều-khoản-điểm hiệu lực tại as-of; "
               "banner do code lắp từ cờ substrate — model không bỏ sót hay bịa được.")


# ---------------------------------------------------------------------------
# Citation panel (FR-2): dialog timeline slider + graph 1-hop + link gốc
# (logic panel dùng chung ở ui/panels.py — Timeline explorer cũng xài)
# ---------------------------------------------------------------------------

_render_citation_panel = panels.render_citation_panel


if hasattr(st, "dialog"):
    @st.dialog("📎 Căn cứ — phiên bản, timeline, graph", width="large")
    def _citation_dialog(basis: dict, role: str):
        _render_citation_panel(basis, role)
else:  # streamlit cũ — fallback inline
    def _citation_dialog(basis: dict, role: str):
        with st.container(border=True):
            _render_citation_panel(basis, role)


# ---------------------------------------------------------------------------
# Render Answer (4 mục cố định) — banner TRÊN thân (FR-3)
# ---------------------------------------------------------------------------

def render_answer(ans: dict, msg_idx: int):
    is_customer = persona == "customer" or ans.get("audience") == "customer"
    tier = ans.get("tier", "D")

    # Tem trạng thái + tier
    if is_customer:
        st.markdown(f"**{CUSTOMER_TIER.get(tier, '')}**")
        st.caption(f"Theo trạng thái văn bản ngày **{ans.get('as_of', '?')}**")
    else:
        badge, explain = TIER_BADGE.get(tier, TIER_BADGE["D"])
        st.markdown(f"**{badge}** — {explain}")
        run_id = ans.get("run_id")
        st.caption(f"Theo trạng thái văn bản ngày **{ans.get('as_of', '?')}** "
                   f"(run: `{str(run_id)[:8] + '…' if run_id else 'chưa có snapshot'}`)")

    # FR-3: banner trên thân, đúng thứ tự server lắp
    for b in ans.get("banners", []):
        st.warning(f"🚩 {b.get('text_vi', b.get('kind', ''))}")

    # ---- Trả lời ----
    st.markdown("#### Trả lời")
    if tier == "D":
        with st.container(border=True):
            if is_customer:
                st.markdown("🙋 **Câu hỏi của bạn cần chuyên viên hỗ trợ.**")
                st.write("Chúng tôi không đưa ra câu trả lời khi chưa đủ căn cứ văn bản. "
                         "Câu hỏi đã được ghi nhận và chuyển tiếp.")
            else:
                st.markdown("🔴 **Từ chối trả lời — route chuyên gia (FR-6)**")
                st.write(ans.get("refusal_reason") or "Thiếu căn cứ đã compile.")
                st.caption("Câu hỏi đã vào demand log — curator thấy tần suất trong admin console.")
    elif tier == "C":
        # FR-5: sources-only — KHÁC BIỆT THỊ GIÁC, không văn tổng hợp
        st.markdown(
            "<div style='background:#8a4b00;color:#fff;padding:8px 14px;border-radius:8px;"
            "font-weight:700'>🟠 CHẾ ĐỘ NGUỒN-GHIM (sources-only) — văn soạn không qua được "
            "kiểm chứng cứng nên hệ CHỈ đưa trích dẫn nguyên văn. Degradation là feature, "
            "không phải lời xin lỗi.</div>",
            unsafe_allow_html=True,
        )
        for basis in ans.get("bases", []):
            with st.container(border=True):
                st.markdown(f"**{basis.get('ref', '')} {basis.get('citation_vi', '')}**")
                if basis.get("quote"):
                    st.markdown(f"> {basis['quote']}")
                st.caption(f"hiệu lực {basis.get('valid_from') or '?'} → {basis.get('valid_to') or 'nay'}")
    elif ans.get("answer"):
        for blk in ans["answer"]:
            bits = []
            if blk.get("interval_from") or blk.get("interval_to"):
                bits.append(f"🗓 {blk.get('interval_from') or '…'} → {blk.get('interval_to') or 'nay'}")
            if blk.get("cohort"):
                bits.append(f"👥 {blk['cohort']}")
            if bits:
                st.caption(" · ".join(bits))
            st.markdown(blk.get("text_vi", ""))
    else:
        st.write("—")

    # ---- Căn cứ (giữ nguyên cho customer — FR-7) ----
    st.markdown("#### Căn cứ")
    bases = ans.get("bases", [])
    if bases:
        for j, basis in enumerate(bases):
            cols = st.columns([5, 1])
            with cols[0]:
                with st.expander(f"{basis.get('ref', '')} {basis.get('citation_vi', '')}"
                                 f" — hiệu lực {basis.get('valid_from') or '?'} → {basis.get('valid_to') or 'nay'}"):
                    if basis.get("quote"):
                        st.markdown(f"> {basis['quote']}")
                    if basis.get("provenance_vi"):
                        st.caption(f"Phả hệ: {basis['provenance_vi']}")
                    st.caption(f"Trạng thái: {basis.get('status') or '?'}")
            if cols[1].button("📎 chi tiết", key=f"cit{msg_idx}_{j}",
                              help="Panel: text version + cửa sổ hiệu lực + timeline slider + graph"):
                _citation_dialog(basis, persona)
    else:
        st.write("Không có — chưa có căn cứ đã compile." if tier == "D" else "Không có.")

    # ---- Xung đột ----
    st.markdown("#### Xung đột")
    conflicts = ans.get("conflicts", [])
    if conflicts:
        if is_customer:  # R-36: customer thấy escalate, không thấy certificate nội bộ
            st.info("Một phần nội dung liên quan đang được bộ phận chuyên môn rà soát; "
                    "câu trả lời có thể thay đổi sau kết luận chính thức.")
        else:
            for c in conflicts:
                st.warning(f"⚔️ [Tier {c.get('tier')}] {c.get('reason', '')}")
    else:
        st.write("Không phát hiện xung đột trong phạm vi căn cứ đã dùng.")

    # ---- Thay đổi sắp hiệu lực ----
    st.markdown("#### Thay đổi sắp hiệu lực")
    if ans.get("upcoming_changes"):
        for u in ans["upcoming_changes"]:
            st.info(f"📅 Từ **{u.get('effective_from')}**: {u.get('description_vi', '')}")
    else:
        st.write("Không có thay đổi sắp hiệu lực liên quan trong căn cứ đã dùng.")

    # Coverage + feedback
    cov = ans.get("coverage") or []
    if cov and not is_customer:
        st.caption("🛰 Coverage: " + "; ".join(
            f"{c['channel']} đến {c.get('last_seq') or '?'}" for c in cov))
    if st.button("🕰 Nghi đã cũ — báo curator", key=f"fb{msg_idx}",
                 help="FR-8: kênh SEM (d) — phản hồi người đọc"):
        resp = api.post("/v1/feedback", persona,
                        json_body={"qa_id": ans.get("qa_id"), "kind": "nghi_da_cu",
                                   "note": f"UI feedback msg#{msg_idx}"})
        if resp.status_code == 200:
            st.toast("Đã ghi nhận — cảm ơn! Curator sẽ rà lại độ mới của căn cứ.", icon="🕰")
        else:
            st.toast(f"Lỗi gửi feedback: {resp.status_code}", icon="⚠️")


# ---------------------------------------------------------------------------
# Chat loop với SSE
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and isinstance(msg.get("answer"), dict):
            render_answer(msg["answer"], i)
        else:
            st.markdown(msg["content"])

if question := st.chat_input("Ví dụ: Điều kiện vay vốn phục vụ nhu cầu đời sống hiện nay?"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        payload = {"question": question, "as_of": as_of.isoformat(), "audience": persona}
        if use_k:
            payload["as_known"] = as_known.isoformat() + "T23:59:59+07:00"
        final_answer = None
        try:
            status = st.status("Đang truy trạng thái hiệu lực…", expanded=False)
            stream_box = st.empty()
            streamed = ""
            for ev, data in api.ask_sse(payload, persona):
                if ev == "meta":
                    rid = data.get("run_id")
                    status.update(label=f"run: {str(rid)[:8] + '…' if rid else 'chưa có snapshot'} · "
                                        f"as-of {data.get('as_of')}")
                elif ev == "token":
                    streamed += data.get("text", "")
                    stream_box.markdown(streamed + "▌")
                elif ev == "done":
                    final_answer = data.get("answer")
            status.update(label="Hoàn tất", state="complete")
            stream_box.empty()
        except Exception:
            # Fallback JSON (SSE bị chặn bởi proxy nào đó) — contract F1 vẫn sống
            try:
                resp = api.post("/v1/ask", persona, json_body=payload)
                resp.raise_for_status()
                final_answer = resp.json()
            except Exception as exc2:
                err = f"Không gọi được API ({type(exc2).__name__}). Kiểm tra trang Build status."
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
        if final_answer:
            idx = len(st.session_state.messages)
            render_answer(final_answer, idx)
            st.session_state.messages.append({"role": "assistant", "answer": final_answer, "content": ""})
