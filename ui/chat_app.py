"""LawState — Chat UI (Streamlit). Khung F1: chat + as-of control + render 4 mục
cố định (Trả lời / Căn cứ / Xung đột / Thay đổi sắp hiệu lực) + tier badge.
Logic answering thật thuộc F5; trang Build status: pages/1_Build_status.py."""
import os
from datetime import date

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

TIER_BADGE = {
    "A": ("🟢 Tier A", "Đã kiểm chứng sạch: mọi trích dẫn khớp snapshot, judge pass, không cờ nào."),
    "B": ("🟡 Tier B", "Đã kiểm chứng cứng, kèm banner (conflict/pending/cohort/consolidation hoặc judge chưa hiệu chuẩn)."),
    "C": ("🟠 Tier C", "Sources-only: chỉ trích dẫn ghim, không văn tổng hợp — văn soạn không qua được gate cứng."),
    "D": ("🔴 Tier D", "Từ chối trả lời + route chuyên gia — thiếu căn cứ đã compile hoặc ngoài coverage."),
}

st.set_page_config(page_title="LawState — SHB", page_icon="⚖️", layout="wide")

with st.sidebar:
    st.title("⚖️ LawState")
    st.caption("Máy tính hiệu lực pháp quy — ba trục thời gian, retrieval trên trạng thái đã compile, verifier hai tầng.")
    audience = st.radio("Persona", ["employee", "customer"], format_func=lambda a: "Nhân viên" if a == "employee" else "Khách hàng")
    as_of = st.date_input("Trả lời theo trạng thái văn bản ngày (as-of)", value=date.today())
    st.divider()
    st.caption(f"API: `{API_URL}`")

st.markdown("### Hỏi đáp pháp quy ngân hàng")
st.caption("Mọi câu trả lời ghim vào phiên bản điều-khoản-điểm hiệu lực tại ngày as-of; không đủ căn cứ → hệ từ chối thay vì bịa.")


def render_answer(ans: dict) -> None:
    badge, explain = TIER_BADGE.get(ans.get("tier", "D"), TIER_BADGE["D"])
    st.markdown(f"**{badge}** — {explain}")
    run_id = ans.get("run_id")
    st.caption(f"Theo trạng thái văn bản ngày **{ans.get('as_of', '?')}** (run: `{run_id or 'chưa có snapshot'}`)")

    for b in ans.get("banners", []):
        st.warning(b.get("text_vi", b.get("kind", "")))

    st.markdown("#### Trả lời")
    if ans.get("tier") == "D":
        st.error(ans.get("refusal_reason") or "Từ chối trả lời.")
        st.info("Câu hỏi được chuyển tới chuyên gia pháp chế (demand log).")
    elif ans.get("answer"):
        for blk in ans["answer"]:
            scope_bits = []
            if blk.get("interval_from") or blk.get("interval_to"):
                scope_bits.append(f"hiệu lực {blk.get('interval_from') or '…'} → {blk.get('interval_to') or 'nay'}")
            if blk.get("cohort"):
                scope_bits.append(f"áp dụng: {blk['cohort']}")
            if scope_bits:
                st.caption(" · ".join(scope_bits))
            st.markdown(blk.get("text_vi", ""))
    else:
        st.write("—")

    st.markdown("#### Căn cứ")
    if ans.get("bases"):
        for basis in ans["bases"]:
            with st.expander(f"{basis.get('ref', '')} {basis.get('citation_vi', '')}"):
                if basis.get("quote"):
                    st.markdown(f"> {basis['quote']}")
                meta = [
                    f"cửa sổ: {basis.get('valid_from') or '?'} → {basis.get('valid_to') or 'nay'}",
                    f"trạng thái: {basis.get('status') or '?'}",
                ]
                if basis.get("provenance_vi"):
                    meta.append(f"phả hệ: {basis['provenance_vi']}")
                st.caption(" · ".join(meta))
    else:
        st.write("Không có — chưa có căn cứ đã compile.")

    st.markdown("#### Xung đột")
    if ans.get("conflicts"):
        for c in ans["conflicts"]:
            st.warning(f"[Tier {c.get('tier')}] {c.get('reason', '')}")
    else:
        st.write("Không phát hiện xung đột trong phạm vi căn cứ đã dùng.")

    st.markdown("#### Thay đổi sắp hiệu lực")
    if ans.get("upcoming_changes"):
        for u in ans["upcoming_changes"]:
            st.info(f"Từ **{u.get('effective_from')}**: {u.get('description_vi', '')}")
    else:
        st.write("Không có thay đổi sắp hiệu lực liên quan trong căn cứ đã dùng.")

    cov = ans.get("coverage") or []
    if cov:
        st.caption("Coverage: " + "; ".join(f"{c['channel']} đến {c.get('last_seq') or '?'}" for c in cov))
    else:
        st.caption("Coverage attestation: rỗng — chưa quét kênh văn bản nào.")


if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and isinstance(msg.get("answer"), dict):
            render_answer(msg["answer"])
        else:
            st.markdown(msg["content"])

if question := st.chat_input("Ví dụ: Điều kiện vay vốn phục vụ nhu cầu đời sống hiện nay?"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            resp = httpx.post(
                f"{API_URL}/v1/ask",
                json={"question": question, "as_of": as_of.isoformat(), "audience": audience},
                timeout=60,
            )
            resp.raise_for_status()
            ans = resp.json()
            render_answer(ans)
            st.session_state.messages.append({"role": "assistant", "answer": ans, "content": ""})
        except Exception as exc:  # lỗi hạ tầng hiển thị trung thực, không giả vờ có câu trả lời
            err = f"Không gọi được API ({type(exc).__name__}). Kiểm tra trang Build status."
            st.error(err)
            st.session_state.messages.append({"role": "assistant", "content": err})
